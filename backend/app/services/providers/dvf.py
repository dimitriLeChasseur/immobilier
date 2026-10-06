"""DVF : ventes de logements dans un rayon de 300 m.

`api.cquest.org/dvf` n'étant plus en service, la source est l'API de l'application
officielle DVF (Etalab), interrogée par section cadastrale : on récupère d'abord les
sections qui recoupent le rayon (API Carto), puis leurs mutations en parallèle.
"""

import json
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from statistics import median, quantiles
from typing import Any

from app.core.errors import NoDataError
from app.core.geo import circle_polygon, haversine_m
from app.core.http import HttpClient
from app.services.providers.base import (
    AuditContext,
    ProviderData,
    as_rows,
    gather_parts,
    to_float,
)

_FEUILLE_URL = "https://apicarto.ign.fr/api/cadastre/feuille"
_MUTATIONS_URL = "https://app.dvf.etalab.gouv.fr/api/mutations3"
_RADIUS_M = 300
_MAX_SECTIONS = 12
_LON_LAT = 2
_RECENT_SALES = 10
_HOUSING = {"Appartement": "appartement", "Maison": "maison"}
_IGNORED_LOCALS = {"Dépendance", "None", ""}
_MIN_SURFACE_M2 = 9.0
_MIN_SALES_FOR_QUARTILES = 4
# Bornes de vraisemblance du prix au m² (écarte ventes en bloc et erreurs de saisie).
_MIN_PRICE_M2, _MAX_PRICE_M2 = 300.0, 60_000.0


@dataclass(frozen=True, slots=True)
class Sale:
    date: str
    price: float
    surface_m2: float
    kind: str
    distance_m: int
    rooms: int | None = None

    @property
    def price_m2(self) -> float:
        return self.price / self.surface_m2


class DvfProvider:
    name = "dvf"

    def __init__(self, http: HttpClient) -> None:
        self._http = http

    async def fetch(self, ctx: AuditContext) -> ProviderData:
        sections = await self._sections(ctx)
        if not sections:
            raise NoDataError
        by_section, missing = await gather_parts(
            {
                f"{commune}/{section}": self._mutations(commune, section)
                for commune, section in sections
            }
        )
        rows = [row for section_rows in by_section.values() for row in section_rows]
        sales = build_sales(rows, ctx.lat, ctx.lon, _RADIUS_M)
        if not sales:
            raise NoDataError
        summary = summarize(sales)
        summary["rayon_m"] = _RADIUS_M
        summary["sections_interrogees"] = len(by_section)
        return ProviderData(data=summary, missing=missing)

    async def _sections(self, ctx: AuditContext) -> list[tuple[str, str]]:
        polygon = json.dumps(circle_polygon(ctx.lat, ctx.lon, _RADIUS_M), separators=(",", ":"))
        payload = await self._http.get_json("apicarto", _FEUILLE_URL, params={"geom": polygon})
        distances: dict[tuple[str, str], float] = {}
        for feature in as_rows(payload, "features"):
            section = _section_key(feature.get("properties") or {})
            if section is not None:
                distance = _distance_to_feature(feature, ctx.lat, ctx.lon)
                distances[section] = min(distance, distances.get(section, distance))
        # Au-delà du plafond, ce sont les sections les plus éloignées qui sont écartées.
        return sorted(distances, key=lambda section: (distances[section], section))[:_MAX_SECTIONS]

    async def _mutations(self, commune: str, section: str) -> list[dict[str, Any]]:
        payload = await self._http.get_json("dvf", f"{_MUTATIONS_URL}/{commune}/{section}")
        return as_rows(payload, "mutations")


def _positions(coordinates: Any) -> Iterator[tuple[float, float]]:
    """Sommets (lon, lat) d'une géométrie GeoJSON, quel que soit son niveau d'imbrication."""
    if not isinstance(coordinates, list):
        return
    if len(coordinates) >= _LON_LAT and all(isinstance(c, int | float) for c in coordinates[:2]):
        yield float(coordinates[0]), float(coordinates[1])
        return
    for item in coordinates:
        yield from _positions(item)


def _distance_to_feature(feature: dict[str, Any], lat: float, lon: float) -> float:
    """Distance du point à l'emprise de la feuille (0 si le point est dedans)."""
    points = list(_positions((feature.get("geometry") or {}).get("coordinates")))
    if not points:
        return 0.0
    lons, lats = [p[0] for p in points], [p[1] for p in points]
    nearest_lon = min(max(lon, min(lons)), max(lons))
    nearest_lat = min(max(lat, min(lats)), max(lats))
    return haversine_m(lat, lon, nearest_lat, nearest_lon)


def _section_key(properties: dict[str, Any]) -> tuple[str, str] | None:
    """(code commune DVF, préfixe+section) à partir d'une feuille cadastrale."""
    department, section = properties.get("code_dep"), properties.get("section")
    arrondissement, commune = properties.get("code_arr"), properties.get("code_com")
    if not (isinstance(department, str) and isinstance(section, str) and isinstance(commune, str)):
        return None
    # Paris, Lyon, Marseille : DVF est indexé par arrondissement.
    local_code = (
        arrondissement if isinstance(arrondissement, str) and arrondissement != "000" else commune
    )
    prefix = str(properties.get("com_abs") or "000")
    return f"{department}{local_code}", f"{prefix}{section.rjust(2, '0')}"


def build_sales(rows: list[dict[str, Any]], lat: float, lon: float, radius_m: float) -> list[Sale]:
    """Regroupe les lignes DVF par mutation et ne garde que les ventes de logements du rayon."""
    grouped: dict[str, dict[tuple[Any, ...], dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        mutation_id = row.get("id_mutation")
        if isinstance(mutation_id, str):
            # Une même ligne peut être répétée (plusieurs natures de culture, sections voisines).
            grouped[mutation_id][_row_identity(row)] = row
    sales = [
        sale
        for lots in grouped.values()
        if (sale := _sale_from_lots(list(lots.values()), lat, lon, radius_m)) is not None
    ]
    sales.sort(key=lambda sale: sale.date, reverse=True)
    return sales


def _row_identity(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("id_parcelle"),
        row.get("lot1_numero"),
        row.get("type_local"),
        row.get("surface_reelle_bati"),
        row.get("nombre_pieces_principales"),
    )


def _sale_from_lots(
    lots: list[dict[str, Any]], lat: float, lon: float, radius_m: float
) -> Sale | None:
    first = lots[0]
    built = [lot for lot in lots if str(lot.get("type_local")) not in _IGNORED_LOCALS]
    # On écarte les mutations mêlant logements et locaux d'activité : prix non ventilable.
    if first.get("nature_mutation") != "Vente" or not built:
        return None
    if any(lot.get("type_local") not in _HOUSING for lot in built):
        return None
    price = to_float(first.get("valeur_fonciere"))
    surface = sum(to_float(lot.get("surface_reelle_bati")) or 0.0 for lot in built)
    lot_lat, lot_lon = to_float(first.get("latitude")), to_float(first.get("longitude"))
    if price is None or surface < _MIN_SURFACE_M2 or lot_lat is None or lot_lon is None:
        return None
    distance = haversine_m(lat, lon, lot_lat, lot_lon)
    if distance > radius_m or not _MIN_PRICE_M2 <= price / surface <= _MAX_PRICE_M2:
        return None
    kinds = {_HOUSING[str(lot["type_local"])] for lot in built}
    rooms = sum(to_float(lot.get("nombre_pieces_principales")) or 0.0 for lot in built)
    return Sale(
        date=str(first.get("date_mutation")),
        price=price,
        surface_m2=surface,
        kind=kinds.pop() if len(kinds) == 1 else "mixte",
        distance_m=round(distance),
        rooms=round(rooms) if rooms else None,
    )


def _median_price(sales: list[Sale]) -> int:
    return round(median(sale.price_m2 for sale in sales))


def _spread(sales: list[Sale]) -> dict[str, int]:
    """Étendue des prix au m² : extrêmes et quartiles (moitié centrale des ventes)."""
    prices = sorted(sale.price_m2 for sale in sales)
    if len(prices) >= _MIN_SALES_FOR_QUARTILES:
        first, _, third = quantiles(prices, n=4)
    else:
        first, third = prices[0], prices[-1]
    return {
        "min": round(prices[0]),
        "q1": round(first),
        "q3": round(third),
        "max": round(prices[-1]),
    }


def summarize(sales: list[Sale]) -> dict[str, Any]:
    """Indicateurs de prix au m² : global, par type de bien et par année."""
    by_kind: dict[str, list[Sale]] = defaultdict(list)
    by_year: dict[str, list[Sale]] = defaultdict(list)
    for sale in sales:
        by_kind[sale.kind].append(sale)
        by_year[sale.date[:4]].append(sale)
    return {
        "nb_ventes": len(sales),
        "prix_m2_median": _median_price(sales),
        "dispersion": _spread(sales),
        "par_type": {
            kind: {"nb_ventes": len(items), "prix_m2_median": _median_price(items)}
            for kind, items in sorted(by_kind.items())
        },
        "historique": [
            {"annee": int(year), "nb_ventes": len(items), "prix_m2_median": _median_price(items)}
            for year, items in sorted(by_year.items())
            if year.isdigit()
        ],
        "dernieres_ventes": [
            {
                "date": sale.date,
                "prix": round(sale.price),
                "surface_m2": round(sale.surface_m2),
                "prix_m2": round(sale.price_m2),
                "type": sale.kind,
                "pieces": sale.rooms,
                "distance_m": sale.distance_m,
            }
            for sale in sales[:_RECENT_SALES]
        ],
    }
