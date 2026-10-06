"""Géorisques : inondation, argiles, sismicité, radon, Seveso, catastrophes naturelles."""

from collections.abc import Awaitable, Callable
from typing import Any

from app.core.geo import haversine_m
from app.core.http import HttpClient
from app.services.insights import risk_recommendations
from app.services.providers.base import (
    AuditContext,
    ProviderData,
    as_rows,
    gather_parts,
    to_float,
)
from app.services.street import Street

_BASE_URL = "https://georisques.gouv.fr/api/v1"
_SOURCE = "georisques"
_POINT_RADIUS_M = 100
_SEVESO_RADIUS_M = 2000
_SEVESO_PAGE_SIZE = 100
_CATNAT_PAGE_SIZE = 100
_PLANS_PAGE_SIZE = 20
# Rayon de recherche des anciens sites industriels, cavités et mouvements de terrain.
_NEARBY_RADIUS_M = 500
_NEAREST_SITES = 3
# Points évalués le long d'une voie : assez pour voir une rue traverser une zone, sans
# multiplier les appels.
_STREET_SAMPLES = 5


class GeorisquesProvider:
    name = "georisques"

    def __init__(self, http: HttpClient) -> None:
        self._http = http

    async def fetch(self, ctx: AuditContext) -> ProviderData:
        latlon = f"{ctx.lon},{ctx.lat}"
        data, missing = await gather_parts(
            {
                "risques": self._risks(latlon),
                # L'atlas des zones inondables répond à l'échelle de la commune : l'évaluer en
                # plusieurs points de la voie n'apporterait rien.
                "inondation": self._flood(latlon),
                "argiles": self._clay_along(ctx.street) if ctx.street else self._clay(latlon),
                "sismicite": self._seismic(ctx.citycode),
                "radon": self._radon(ctx.citycode),
                "seveso": self._seveso(ctx, latlon),
                "catastrophes_naturelles": self._catnat(latlon),
                "plans_prevention": self._prevention_plans(ctx.citycode),
                "tri": self._flood_priority_areas(latlon),
                "anciens_sites_industriels": self._former_industrial_sites(ctx, latlon),
                "cavites": self._cavities(ctx, latlon),
                "mouvements_terrain": self._ground_movements(latlon),
            }
        )
        data["recommandations"] = risk_recommendations(data)
        return ProviderData(data=data, missing=missing)

    async def _get(self, path: str, params: dict[str, str | int | float]) -> Any:
        return await self._http.get_json(_SOURCE, f"{_BASE_URL}/{path}", params=params)

    async def _risks(self, latlon: str) -> list[str]:
        payload = await self._get("gaspar/risques", {"latlon": latlon, "rayon": _POINT_RADIUS_M})
        labels = {
            str(detail.get("libelle_risque_long"))
            for row in as_rows(payload, "data")
            for detail in row.get("risques_detail") or []
            if detail.get("libelle_risque_long")
        }
        return sorted(labels)

    async def _flood(self, latlon: str) -> dict[str, Any]:
        payload = await self._get("gaspar/azi", {"latlon": latlon, "rayon": _POINT_RADIUS_M})
        zones = sorted({str(row.get("libelle_azi")) for row in as_rows(payload, "data")})
        return {"concerne": bool(zones), "atlas_zones_inondables": zones}

    async def _clay(self, latlon: str) -> dict[str, Any]:
        # Corps vide = point hors zone cartographiée (ex. Paris intra-muros).
        payload = await self._get("rga", {"latlon": latlon})
        if not isinstance(payload, dict):
            return {"code": None, "exposition": None}
        return {"code": payload.get("codeExposition"), "exposition": payload.get("exposition")}

    async def _clay_along(self, street: Street) -> dict[str, Any]:
        """Exposition la plus forte rencontrée le long de la voie."""
        results = [r for r in await self._along(street, self._clay) if r["code"] is not None]
        if not results:
            return {"code": None, "exposition": None}
        worst = max(results, key=lambda result: str(result["code"]))
        return {**worst, "variable": len({str(result["code"]) for result in results}) > 1}

    async def _along(
        self, street: Street, probe: Callable[[str], Awaitable[dict[str, Any]]]
    ) -> list[dict[str, Any]]:
        points = street.sample(_STREET_SAMPLES)
        results, _ = await gather_parts(
            {str(index): probe(f"{lon},{lat}") for index, (lon, lat) in enumerate(points)}
        )
        return list(results.values())

    async def _seismic(self, citycode: str) -> dict[str, Any] | None:
        payload = await self._get("zonage_sismique", {"code_insee": citycode})
        rows = as_rows(payload, "data")
        if not rows:
            return None
        return {"code": rows[0].get("code_zone"), "zone": rows[0].get("zone_sismicite")}

    async def _radon(self, citycode: str) -> dict[str, Any] | None:
        payload = await self._get("radon", {"code_insee": citycode})
        rows = as_rows(payload, "data")
        if not rows:
            return None
        return {"classe_potentiel": rows[0].get("classe_potentiel")}

    async def _seveso(self, ctx: AuditContext, latlon: str) -> dict[str, Any]:
        payload = await self._get(
            "installations_classees",
            {"latlon": latlon, "rayon": _SEVESO_RADIUS_M, "page_size": _SEVESO_PAGE_SIZE},
        )
        sites = [
            site for row in as_rows(payload, "data") if (site := _seveso_site(row, ctx)) is not None
        ]
        sites.sort(key=lambda site: site["distance_m"] if site["distance_m"] is not None else 1e9)
        return {
            "rayon_m": _SEVESO_RADIUS_M,
            "sites": sites,
            "installations_classees_total": payload.get("results"),
            # L'API ne filtre pas par statut : au-delà d'une page, la liste est incomplète.
            "liste_tronquee": int(payload.get("total_pages") or 0) > 1,
        }

    async def _catnat(self, latlon: str) -> dict[str, Any]:
        payload = await self._get(
            "gaspar/catnat",
            {"latlon": latlon, "rayon": _POINT_RADIUS_M, "page_size": _CATNAT_PAGE_SIZE},
        )
        by_kind: dict[str, dict[str, Any]] = {}
        for row in as_rows(payload, "data"):
            kind = str(row.get("libelle_risque_jo") or "Autre")
            entry = by_kind.setdefault(kind, {"type": kind, "nb_arretes": 0, "dernier": None})
            entry["nb_arretes"] += 1
            year = _year(row.get("date_debut_evt"))
            if year is not None and (entry["dernier"] is None or year > entry["dernier"]):
                entry["dernier"] = year
        kinds = sorted(by_kind.values(), key=lambda entry: -entry["nb_arretes"])
        return {"nb_arretes": payload.get("results"), "par_type": kinds}

    async def _prevention_plans(self, citycode: str) -> list[dict[str, Any]]:
        """Plans de prévention des risques naturels en vigueur ou prescrits sur la commune."""
        payload = await self._get(
            "gaspar/pprn", {"codeInsee": citycode, "pageSize": _PLANS_PAGE_SIZE}
        )
        return [
            {
                "nom": str(plan.get("libPpr") or "").strip(),
                "type": plan.get("modeleProcedure"),
                "en_revision": bool(plan.get("etatRevision")),
            }
            for plan in as_rows(payload, "content")
        ]

    async def _flood_priority_areas(self, latlon: str) -> list[str]:
        """Territoires à risque important d'inondation (directive européenne) couvrant le point."""
        payload = await self._get("gaspar/tri", {"latlon": latlon, "rayon": _POINT_RADIUS_M})
        return sorted(
            {str(row["libelle_tri"]) for row in as_rows(payload, "data") if row.get("libelle_tri")}
        )

    async def _former_industrial_sites(self, ctx: AuditContext, latlon: str) -> dict[str, Any]:
        """Anciens sites industriels et activités de service (inventaire CASIAS)."""
        payload = await self._get(
            "ssp/casias",
            {"latlon": latlon, "rayon": _NEARBY_RADIUS_M, "page_size": _SEVESO_PAGE_SIZE},
        )
        sites: list[dict[str, Any]] = []
        for row in as_rows(payload, "data"):
            distance = _distance(ctx, (row.get("geom") or {}).get("coordinates"))
            if distance is not None:
                sites.append(
                    {
                        "adresse": row.get("adresse"),
                        "statut": row.get("statut"),
                        "distance_m": distance,
                    }
                )
        sites.sort(key=lambda site: site["distance_m"])
        return {
            "rayon_m": _NEARBY_RADIUS_M,
            "nb_sites": payload.get("results"),
            "plus_proches": sites[:_NEAREST_SITES],
        }

    async def _cavities(self, ctx: AuditContext, latlon: str) -> dict[str, Any]:
        payload = await self._get(
            "cavites", {"latlon": latlon, "rayon": _NEARBY_RADIUS_M, "page_size": _SEVESO_PAGE_SIZE}
        )
        cavities: list[dict[str, Any]] = []
        for row in as_rows(payload, "data"):
            distance = _distance(ctx, [row.get("longitude"), row.get("latitude")])
            if distance is not None:
                cavities.append(
                    {"type": row.get("type"), "nom": row.get("nom"), "distance_m": distance}
                )
        cavities.sort(key=lambda cavity: cavity["distance_m"])
        return {
            "rayon_m": _NEARBY_RADIUS_M,
            "nb_cavites": payload.get("results"),
            "plus_proche": cavities[0] if cavities else None,
        }

    async def _ground_movements(self, latlon: str) -> dict[str, Any]:
        payload = await self._get(
            "mvt", {"latlon": latlon, "rayon": _NEARBY_RADIUS_M, "page_size": 1}
        )
        as_rows(payload, "data")
        return {"rayon_m": _NEARBY_RADIUS_M, "nb_evenements": payload.get("results")}


def _year(date: Any) -> int | None:
    """Année d'une date « JJ/MM/AAAA »."""
    text = str(date or "")
    return int(text[-4:]) if text[-4:].isdigit() else None


def _distance(ctx: AuditContext, coordinates: Any) -> int | None:
    """Distance en mètres du point audité à une position [lon, lat]."""
    if not isinstance(coordinates, list) or len(coordinates) < 2:  # noqa: PLR2004
        return None
    lon, lat = to_float(coordinates[0]), to_float(coordinates[1])
    if lon is None or lat is None:
        return None
    return round(haversine_m(ctx.lat, ctx.lon, lat, lon))


def _seveso_site(row: dict[str, Any], ctx: AuditContext) -> dict[str, Any] | None:
    status = row.get("statutSeveso")
    if not isinstance(status, str) or not status.startswith("Seveso"):
        return None
    lat, lon = to_float(row.get("latitude")), to_float(row.get("longitude"))
    distance = round(haversine_m(ctx.lat, ctx.lon, lat, lon)) if lat and lon else None
    return {
        "nom": row.get("raisonSociale"),
        "statut": status,
        "commune": row.get("commune"),
        "distance_m": distance,
    }
