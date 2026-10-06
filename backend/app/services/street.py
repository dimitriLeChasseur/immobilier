"""Mode « rue » : résolution d'une voie BAN et de ses numéros.

Quand l'utilisateur choisit une voie plutôt qu'une adresse, l'audit porte sur la rue
entière : ses numéros en donnent le tracé, sur lequel les sources agrègent leurs résultats.
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Protocol

from app.core.errors import SourceError
from app.core.geo import haversine_m
from app.core.http import HttpClient

_LOOKUP_URL = "https://plateforme.adresse.data.gouv.fr/lookup"
# Identifiant de voie BAN : code commune, puis code de voie (FANTOIR ou identifiant BAL).
_STREET_ID = re.compile(r"^[0-9][0-9AB][0-9]{3}_[0-9a-z]{4,12}$")
_FANTOIR = re.compile(r"^[0-9a-z][0-9]{3}$")
_MIN_NUMBERS = 2
# Le point demandé doit appartenir à la voie : au-delà, l'identifiant ne lui correspond pas.
_MAX_OFFSET_M = 1500
_M_PER_DEG = 111_320.0
_NAME_NOISE = re.compile(r"[^A-Z0-9]+")


@dataclass(frozen=True, slots=True)
class Street:
    id: str
    name: str
    # (lon, lat) des numéros, dans l'ordre de la numérotation.
    points: tuple[tuple[float, float], ...]

    @property
    def fantoir(self) -> str | None:
        """Code de voie tel que le publie DVF, quand l'identifiant BAN en dérive."""
        code = self.id.split("_", 1)[1]
        return code.upper() if _FANTOIR.match(code) else None

    @property
    def length_m(self) -> int:
        """Ordre de grandeur de la longueur : plus grande dimension de l'emprise."""
        lons, lats = [p[0] for p in self.points], [p[1] for p in self.points]
        return round(haversine_m(min(lats), min(lons), max(lats), max(lons)))

    def sample(self, count: int) -> list[tuple[float, float]]:
        """`count` points régulièrement répartis le long de la numérotation."""
        if len(self.points) <= count:
            return list(self.points)
        step = (len(self.points) - 1) / (count - 1)
        return [self.points[round(index * step)] for index in range(count)]

    def envelope(self, margin_m: float) -> dict[str, Any]:
        """Rectangle GeoJSON englobant la voie, élargi d'une marge."""
        lons, lats = [p[0] for p in self.points], [p[1] for p in self.points]
        pad = margin_m / _M_PER_DEG
        west, east = min(lons) - pad * 1.5, max(lons) + pad * 1.5
        south, north = min(lats) - pad, max(lats) + pad
        ring = [[west, south], [east, south], [east, north], [west, north], [west, south]]
        return {"type": "Polygon", "coordinates": [ring]}

    def multipoint(self, count: int) -> dict[str, Any]:
        return {"type": "MultiPoint", "coordinates": [list(point) for point in self.sample(count)]}


def normalize_street_name(name: Any) -> str:
    """Nom de voie comparable entre la BAN (« Rue Saint-Aubin ») et DVF (« RUE SAINT AUBIN »)."""
    if not isinstance(name, str):
        return ""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().upper()
    return _NAME_NOISE.sub(" ", plain).strip()


def is_street_id(ban_id: str) -> bool:
    return bool(_STREET_ID.match(ban_id))


def parse_street(payload: Any, lat: float, lon: float) -> Street | None:
    """Voie décrite par la réponse BAN, None si ce n'est pas une voie exploitable ici."""
    if not isinstance(payload, dict) or payload.get("type") != "voie":
        return None
    street_id, name = payload.get("idVoie"), payload.get("nomVoie")
    if not isinstance(street_id, str) or not isinstance(name, str):
        return None
    numbers = [n for n in payload.get("numeros") or [] if isinstance(n, dict)]
    numbers.sort(key=lambda n: (_as_int(n.get("numero")), str(n.get("suffixe") or "")))
    points = tuple(point for number in numbers if (point := _position(number)) is not None)
    if len(points) < _MIN_NUMBERS:
        return None
    if min(haversine_m(lat, lon, p[1], p[0]) for p in points) > _MAX_OFFSET_M:
        return None
    return Street(id=street_id, name=name, points=points)


def _as_int(value: Any) -> int:
    return value if isinstance(value, int) else 0


def _position(number: dict[str, Any]) -> tuple[float, float] | None:
    coordinates = (number.get("position") or {}).get("coordinates")
    if (
        isinstance(coordinates, list)
        and len(coordinates) >= 2  # noqa: PLR2004
        and all(isinstance(c, int | float) for c in coordinates[:2])
    ):
        return float(coordinates[0]), float(coordinates[1])
    return None


class StreetResolver(Protocol):
    async def resolve(self, ban_id: str, lat: float, lon: float) -> Street | None: ...


class BanStreetResolver:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    async def resolve(self, ban_id: str, lat: float, lon: float) -> Street | None:
        """Voie désignée par `ban_id` si elle passe bien par le point demandé.

        L'identifiant vient du navigateur : il ne sert qu'à choisir le périmètre de
        l'analyse, et seulement s'il est cohérent avec les coordonnées. En cas d'échec,
        l'audit se rabat sur l'analyse au point.
        """
        if not is_street_id(ban_id):
            return None
        try:
            payload = await self._http.get_json("ban_lookup", f"{_LOOKUP_URL}/{ban_id}")
        except SourceError:
            return None
        return parse_street(payload, lat, lon)
