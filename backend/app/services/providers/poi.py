"""OpenStreetMap : transports, commerces et services accessibles à pied.

Les points d'intérêt viennent du référentiel local (scripts/ingest_osm_poi.py). Les serveurs
publics Overpass, souvent saturés, ne servent que de secours pour un secteur non ingéré.

Les temps de marche sont estimés à partir de la distance à vol d'oiseau ; un calcul
d'isochrones réel (OpenRouteService) nécessite une clé d'API.
"""

import logging
from typing import Any

from app.core.errors import RepositoryError, SourceError
from app.core.geo import haversine_m, walking_minutes
from app.core.http import HttpClient
from app.repositories.reference import ReferenceRepository
from app.services.providers.base import AuditContext, ProviderData, as_rows, to_float

logger = logging.getLogger(__name__)

# Instances publiques interrogées tour à tour : chacune est régulièrement saturée (504).
OVERPASS_ENDPOINTS: tuple[str, ...] = (
    "https://overpass-api.de/api/interpreter",
    "https://z.overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
)
# Délai par instance : trois essais doivent tenir dans le garde-fou global de la source.
_ENDPOINT_TIMEOUT_S = 5.0
_ORS_MATRIX_URL = "https://api.openrouteservice.org/v2/matrix/foot-walking"
# Valeurs du champ `methode_temps` du rapport.
ESTIMATED = "vol_d_oiseau"
ROUTED = "itineraire_pieton"
_RADIUS_M = 500
_MAX_ELEMENTS = 400
# Délai accordé au serveur Overpass, inférieur au délai client par instance.
_SERVER_TIMEOUT_S = 4

# catégorie -> clé OSM -> valeurs retenues
_CATEGORIES: dict[str, dict[str, frozenset[str]]] = {
    "transports": {
        "railway": frozenset({"station", "tram_stop"}),
        "highway": frozenset({"bus_stop"}),
    },
    "commerces": {"shop": frozenset({"supermarket", "bakery", "convenience"})},
    "sante": {"amenity": frozenset({"pharmacy", "doctors"})},
    "education": {"amenity": frozenset({"school", "kindergarten"})},
    "espaces_verts": {"leisure": frozenset({"park"})},
}


def build_query(lat: float, lon: float) -> str:
    around = f"(around:{_RADIUS_M},{lat},{lon})"
    selectors: dict[str, set[str]] = {}
    for tags in _CATEGORIES.values():
        for key, values in tags.items():
            selectors.setdefault(key, set()).update(values)
    clauses = "".join(
        f'nwr{around}[{key}~"^({"|".join(sorted(values))})$"];'
        for key, values in sorted(selectors.items())
    )
    return f"[out:json][timeout:{_SERVER_TIMEOUT_S}];({clauses});out center tags {_MAX_ELEMENTS};"


def classify(tags: dict[str, Any]) -> tuple[str, str] | None:
    """(catégorie, type) d'un élément OSM, None s'il ne nous intéresse pas."""
    for category, keys in _CATEGORIES.items():
        for key, values in keys.items():
            value = tags.get(key)
            if value in values:
                return category, str(value)
    return None


class PoiProvider:
    name = "proximite"

    def __init__(
        self,
        http: HttpClient,
        *,
        repository: ReferenceRepository | None = None,
        ors_api_key: str | None = None,
    ) -> None:
        self._http = http
        self._repository = repository
        # Sans clé, les temps de marche restent estimés à vol d'oiseau (détour de 30 %).
        self._ors_api_key = ors_api_key or None
        # Rang de la dernière instance Overpass ayant répondu : évite de réessayer à chaque
        # audit un serveur que l'on sait en panne.
        self._preferred_endpoint = 0

    async def fetch(self, ctx: AuditContext) -> ProviderData:
        categories: dict[str, list[dict[str, Any]]] = {name: [] for name in _CATEGORIES}
        pois = await self._local_pois(ctx)
        if pois is None:
            pois = await self._overpass_pois(ctx)
        for poi in pois:
            categories[poi.pop("categorie")].append(poi)
        summaries = {name: _summary(pois) for name, pois in categories.items()}
        method = await self._refine_walking_times(ctx, summaries)
        for summary in summaries.values():
            if summary["plus_proche"] is not None:
                summary["plus_proche"].pop("position")
        return ProviderData(
            data={"rayon_m": _RADIUS_M, "methode_temps": method, "categories": summaries}
        )

    async def _local_pois(self, ctx: AuditContext) -> list[dict[str, Any]] | None:
        """Points du référentiel local ; None s'il ne couvre pas ce secteur ou ne répond pas."""
        if self._repository is None:
            return None
        try:
            rows = await self._repository.pois_nearby(ctx.lat, ctx.lon, _RADIUS_M, _MAX_ELEMENTS)
        except RepositoryError:
            logger.warning("Référentiel des points d'intérêt indisponible : essai d'Overpass")
            return None
        if rows is None:
            return None
        # Une liste vide est une réponse : secteur ingéré, aucun équipement à portée.
        return [
            {
                "categorie": row["categorie"],
                "type": row["type"],
                "nom": row["nom"],
                "distance_m": round(row["distance_m"]),
                "marche_min": walking_minutes(row["distance_m"]),
                "position": [row["lon"], row["lat"]],
            }
            for row in rows
            if row["categorie"] in _CATEGORIES
        ]

    async def _overpass_pois(self, ctx: AuditContext) -> list[dict[str, Any]]:
        payload = await self._query_overpass(build_query(ctx.lat, ctx.lon))
        pois = (_to_poi(element, ctx) for element in as_rows(payload, "elements"))
        return [poi for poi in pois if poi is not None]

    async def _query_overpass(self, query: str) -> Any:
        """Interroge les instances l'une après l'autre jusqu'à la première réponse.

        On commence par celle qui a répondu la dernière fois ; un échec (504, délai dépassé,
        instance suspendue) fait passer immédiatement à la suivante.
        """
        count = len(OVERPASS_ENDPOINTS)
        last_error: SourceError | None = None
        for offset in range(count):
            index = (self._preferred_endpoint + offset) % count
            url = OVERPASS_ENDPOINTS[index]
            try:
                payload = await self._http.post_form_json(
                    f"overpass_{index + 1}",
                    url,
                    data={"data": query},
                    timeout_s=_ENDPOINT_TIMEOUT_S,
                )
            except SourceError as exc:
                logger.warning("Overpass %s en échec (%s), essai de l'instance suivante", url, exc)
                last_error = exc
                continue
            self._preferred_endpoint = index
            return payload
        raise last_error or SourceError("http_error", "overpass")

    async def _refine_walking_times(
        self, ctx: AuditContext, summaries: dict[str, dict[str, Any]]
    ) -> str:
        """Remplace les temps estimés par ceux d'un itinéraire piéton quand c'est possible."""
        nearest = [s["plus_proche"] for s in summaries.values() if s["plus_proche"] is not None]
        if self._ors_api_key is None or not nearest:
            return ESTIMATED
        try:
            payload = await self._http.post_json(
                "openrouteservice",
                _ORS_MATRIX_URL,
                payload={
                    "locations": [[ctx.lon, ctx.lat], *(poi["position"] for poi in nearest)],
                    "sources": [0],
                    "destinations": list(range(1, len(nearest) + 1)),
                    "metrics": ["duration"],
                },
                headers={"Authorization": self._ors_api_key},
            )
            durations = payload["durations"][0]
        except (SourceError, KeyError, IndexError, TypeError):
            # Dégradation silencieuse : l'estimation reste affichée et signalée comme telle.
            logger.warning("OpenRouteService indisponible : temps de marche estimés")
            return ESTIMATED
        if len(durations) != len(nearest) or any(d is None for d in durations):
            return ESTIMATED
        for poi, seconds in zip(nearest, durations, strict=True):
            poi["marche_min"] = max(1, round(float(seconds) / 60))
        return ROUTED


def _to_poi(element: dict[str, Any], ctx: AuditContext) -> dict[str, Any] | None:
    tags = element.get("tags") or {}
    kind = classify(tags)
    position = element.get("center") or element
    lat, lon = to_float(position.get("lat")), to_float(position.get("lon"))
    if kind is None or lat is None or lon is None:
        return None
    distance = haversine_m(ctx.lat, ctx.lon, lat, lon)
    return {
        "categorie": kind[0],
        "type": kind[1],
        "nom": tags.get("name"),
        "distance_m": round(distance),
        "marche_min": walking_minutes(distance),
        # [lon, lat], usage interne pour le calcul d'itinéraire.
        "position": [lon, lat],
    }


def _summary(pois: list[dict[str, Any]]) -> dict[str, Any]:
    pois.sort(key=lambda poi: poi["distance_m"])
    return {"nb": len(pois), "plus_proche": pois[0] if pois else None}
