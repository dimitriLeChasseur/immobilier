"""API Carto IGN : parcelle cadastrale et zonage d'urbanisme (PLU)."""

import json
from typing import Any

from app.core.errors import NoDataError
from app.core.http import HttpClient
from app.services.providers.base import AuditContext, ProviderData, as_rows

_BASE_URL = "https://apicarto.ign.fr/api"
_SOURCE = "apicarto"


def point_geojson(ctx: AuditContext) -> str:
    return json.dumps({"type": "Point", "coordinates": [ctx.lon, ctx.lat]})


def feature_properties(payload: Any) -> list[dict[str, Any]]:
    return [feature.get("properties") or {} for feature in as_rows(payload, "features")]


class CadastreProvider:
    name = "cadastre"

    def __init__(self, http: HttpClient) -> None:
        self._http = http

    async def fetch(self, ctx: AuditContext) -> ProviderData:
        payload = await self._http.get_json(
            _SOURCE, f"{_BASE_URL}/cadastre/parcelle", params={"geom": point_geojson(ctx)}
        )
        parcels = feature_properties(payload)
        if not parcels:
            # Le point tombe sur le domaine public (voirie) : aucune parcelle.
            raise NoDataError
        parcel = parcels[0]
        return ProviderData(
            data={
                "identifiant": parcel.get("idu"),
                "section": parcel.get("section"),
                "numero": parcel.get("numero"),
                "contenance_m2": parcel.get("contenance"),
                "commune": parcel.get("nom_com"),
            }
        )


class UrbanismeProvider:
    name = "urbanisme"

    def __init__(self, http: HttpClient) -> None:
        self._http = http

    async def fetch(self, ctx: AuditContext) -> ProviderData:
        payload = await self._http.get_json(
            _SOURCE, f"{_BASE_URL}/gpu/zone-urba", params={"geom": point_geojson(ctx)}
        )
        zones = [
            {
                "libelle": zone.get("libelle"),
                "libelle_long": zone.get("libelong"),
                "type_zone": zone.get("typezone"),
                "document": zone.get("idurba"),
                "date_validation": zone.get("datvalid"),
                "reglement": zone.get("nomfic"),
            }
            for zone in feature_properties(payload)
        ]
        if not zones:
            # Commune sans document d'urbanisme publié sur le Géoportail de l'urbanisme.
            raise NoDataError
        return ProviderData(data={"zones": zones})
