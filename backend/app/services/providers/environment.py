"""Environnement du bien : qualité de l'air et ensoleillement."""

import re
from datetime import UTC, date, datetime
from typing import Any

from app.core.errors import NoDataError, SourceError
from app.core.geo import destination
from app.core.http import HttpClient
from app.services.insights import atmo_label, relief_summary
from app.services.providers.apicarto import feature_properties
from app.services.providers.base import AuditContext, ProviderData, to_float
from app.services.solar import AZIMUTH_LABELS, AZIMUTHS_DEG, horizon_profile, sunlight_scores

_ATMO_WFS_URL = "https://data.atmo-france.org/geoserver/ind/ows"
_GEO_COMMUNE_URL = "https://geo.api.gouv.fr/communes"
# Code de zone : commune INSEE (5 caractères) ou SIREN d'intercommunalité (9 chiffres).
_ZONE_CODE = re.compile(r"[0-9AB]{5}|\d{9}", re.ASCII)
_ATMO_MIN, _ATMO_MAX = 1, 6
# clé du rapport -> colonne du flux
_ATMO_SUB_INDICES = {
    "pm2_5": "code_pm25",
    "pm10": "code_pm10",
    "no2": "code_no2",
    "o3": "code_o3",
    "so2": "code_so2",
}
_ATMO_POLLUTANT_LABELS = {
    "pm2_5": "particules fines PM2.5",
    "pm10": "particules PM10",
    "no2": "dioxyde d'azote",
    "o3": "ozone",
    "so2": "dioxyde de soufre",
}
_ALTI_URL = "https://data.geopf.fr/altimetrie/1.0/calcul/alti/rest/elevation.json"
_RING_DISTANCES_M: tuple[float, ...] = (50.0, 150.0, 400.0, 1000.0, 2500.0)
# Valeur renvoyée par le service IGN hors emprise du modèle de terrain.
_NO_DATA_ALTITUDE = -9000.0


class AirQualityProvider:
    """Indice ATMO du jour (1 « bon » à 6 « extrêmement mauvais »), publié par Atmo France.

    Donnée ouverte des associations agréées de surveillance de la qualité de l'air (AASQA),
    sous licence ODbL : usage commercial permis, attribution obligatoire. Selon les régions,
    l'indice est calculé à la commune ou à l'intercommunalité : on cherche du plus précis
    au plus large.
    """

    name = "qualite_air"

    def __init__(self, http: HttpClient) -> None:
        self._http = http

    async def fetch(self, ctx: AuditContext) -> ProviderData:
        today = datetime.now(UTC).date()
        codes = ctx.commune_codes
        rows = await self._indices(codes, today)
        if not rows:
            epci = await self._epci_code(codes[-1])
            if epci is None:
                raise NoDataError
            codes = [epci]
            rows = await self._indices(codes, today)
        forecast = select_forecast(rows, codes)
        if not forecast:
            raise NoDataError
        current = forecast[0]
        tomorrow = forecast[1] if len(forecast) > 1 else None
        level = int(current["code_qual"])
        return ProviderData(
            data={
                "indice": level,
                "qualificatif": atmo_label(level),
                "date": str(current.get("date_ech"))[:10],
                "zone": {
                    "code": current.get("code_zone"),
                    "nom": current.get("lib_zone"),
                    "type": str(current.get("type_zone") or "").lower(),
                },
                "sous_indices": {
                    key: _valid_level(current.get(source_key))
                    for key, source_key in _ATMO_SUB_INDICES.items()
                },
                "polluants_dominants": _dominant_pollutants(current, level),
                "demain": (
                    {
                        "indice": int(tomorrow["code_qual"]),
                        "qualificatif": atmo_label(int(tomorrow["code_qual"])),
                    }
                    if tomorrow
                    else None
                ),
                "producteur": current.get("source"),
                "origine": "Atmo France (indice ATMO, licence ODbL)",
            }
        )

    async def _indices(self, codes: list[str], since: date) -> list[dict[str, Any]]:
        quoted = ", ".join(f"'{code}'" for code in codes if _ZONE_CODE.fullmatch(code))
        if not quoted:
            return []
        payload = await self._http.get_json(
            "atmo_france",
            _ATMO_WFS_URL,
            params={
                "service": "WFS",
                "version": "2.0.0",
                "request": "GetFeature",
                "typeNames": "ind:ind_atmo_2021",
                "outputFormat": "application/json",
                "count": 20,
                "CQL_FILTER": f"code_zone IN ({quoted}) AND date_ech >= '{since.isoformat()}'",
            },
        )
        return feature_properties(payload)

    async def _epci_code(self, commune_code: str) -> str | None:
        """Intercommunalité de la commune ; son absence ne doit pas faire échouer le bloc."""
        try:
            payload = await self._http.get_json(
                "geo_api", f"{_GEO_COMMUNE_URL}/{commune_code}", params={"fields": "codeEpci"}
            )
        except SourceError:
            return None
        code = payload.get("codeEpci") if isinstance(payload, dict) else None
        return code if isinstance(code, str) else None


def _valid_level(value: Any) -> int | None:
    """Indice entre 1 et 6 ; 0 (absent) et 7 (événement) ne sont pas des niveaux."""
    level = to_float(value)
    if level is None or not _ATMO_MIN <= level <= _ATMO_MAX:
        return None
    return int(level)


def select_forecast(rows: list[dict[str, Any]], codes: list[str]) -> list[dict[str, Any]]:
    """Indices de la zone la plus précise disponible, du jour le plus proche au plus lointain."""
    usable = [row for row in rows if _valid_level(row.get("code_qual")) is not None]
    for code in codes:
        zone_rows = [row for row in usable if row.get("code_zone") == code]
        if zone_rows:
            return sorted(zone_rows, key=lambda row: str(row.get("date_ech")))
    return []


def _dominant_pollutants(row: dict[str, Any], level: int) -> list[str]:
    """Polluants dont le sous-indice atteint l'indice global : ce sont eux qui le déterminent."""
    return [
        _ATMO_POLLUTANT_LABELS[key]
        for key, source_key in _ATMO_SUB_INDICES.items()
        if _valid_level(row.get(source_key)) == level
    ]


class SunlightProvider:
    """Score d'ensoleillement à partir du relief environnant (IGN RGE Alti).

    Seul le relief est pris en compte : les bâtiments voisins ne sont pas modélisés.
    """

    name = "ensoleillement"

    def __init__(self, http: HttpClient) -> None:
        self._http = http

    async def fetch(self, ctx: AuditContext) -> ProviderData:
        points = [(ctx.lat, ctx.lon)] + [
            destination(ctx.lat, ctx.lon, azimuth, distance)
            for azimuth in AZIMUTHS_DEG
            for distance in _RING_DISTANCES_M
        ]
        altitudes = await self._altitudes(points)
        origin, ring = altitudes[0], altitudes[1:]
        width = len(_RING_DISTANCES_M)
        # Un point hors emprise (mer, étranger) ne masque rien : on le ramène à l'origine.
        rings = [
            [
                altitude if altitude > _NO_DATA_ALTITUDE else origin
                for altitude in ring[i : i + width]
            ]
            for i in range(0, len(ring), width)
        ]
        profile = horizon_profile(origin, rings, _RING_DISTANCES_M)
        mask = dict(zip(AZIMUTH_LABELS, profile, strict=True))
        return ProviderData(
            data={
                "altitude_m": round(origin, 1),
                "score": sunlight_scores(ctx.lat, profile),
                "masque_relief_deg": mask,
                "synthese": relief_summary(mask),
                "methode": "relief seul (RGE Alti), hors bâtiments voisins",
            }
        )

    async def _altitudes(self, points: list[tuple[float, float]]) -> list[float]:
        payload: Any = await self._http.get_json(
            "ign_alti",
            _ALTI_URL,
            params={
                "lat": "|".join(str(lat) for lat, _ in points),
                "lon": "|".join(str(lon) for _, lon in points),
                "resource": "ign_rge_alti_wld",
                "zonly": "true",
            },
        )
        elevations = payload.get("elevations") if isinstance(payload, dict) else None
        if not isinstance(elevations, list) or len(elevations) != len(points):
            raise SourceError("invalid_response", "elevations", transient=False)
        altitudes = [float(value) for value in elevations]
        if altitudes[0] <= _NO_DATA_ALTITUDE:
            raise SourceError("invalid_response", "origin outside coverage", transient=False)
        return altitudes
