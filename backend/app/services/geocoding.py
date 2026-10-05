"""Résolution serveur de la localisation (BAN, repli sur geo.api.gouv.fr)."""

from typing import Any, Protocol

from app.core.errors import SourceError
from app.core.http import HttpClient
from app.schemas.audit import Location
from app.services.providers.base import as_rows

_BAN_REVERSE_URL = "https://api-adresse.data.gouv.fr/reverse/"
_GEO_COMMUNES_URL = "https://geo.api.gouv.fr/communes"


def _region_from_context(context: Any) -> str | None:
    """Région d'un contexte BAN « 49, Maine-et-Loire, Pays de la Loire »."""
    if not isinstance(context, str) or "," not in context:
        return None
    return context.rsplit(",", 1)[1].strip() or None


class Geocoder(Protocol):
    async def reverse(self, lat: float, lon: float, ban_id: str) -> Location | None:
        """Localisation correspondant aux coordonnées, None si hors couverture."""
        ...


class BanGeocoder:
    """Géocodage inverse BAN ; si la BAN est indisponible, repli sur la commune."""

    def __init__(self, http: HttpClient) -> None:
        self._http = http

    async def reverse(self, lat: float, lon: float, ban_id: str) -> Location | None:
        try:
            return await self._from_ban(lat, lon, ban_id)
        except SourceError:
            return await self._from_commune(lat, lon, ban_id)

    async def _from_ban(self, lat: float, lon: float, ban_id: str) -> Location | None:
        payload = await self._http.get_json(
            "ban", _BAN_REVERSE_URL, params={"lat": lat, "lon": lon, "limit": 1}
        )
        features = as_rows(payload, "features")
        if not features:
            return await self._from_commune(lat, lon, ban_id)
        properties: dict[str, Any] = features[0].get("properties") or {}
        citycode = properties.get("citycode")
        if not isinstance(citycode, str):
            raise SourceError("invalid_response", "citycode", transient=False)
        return Location(
            lat=lat,
            lon=lon,
            label=str(properties.get("label") or citycode),
            citycode=citycode,
            postcode=properties.get("postcode"),
            city=properties.get("city"),
            region=_region_from_context(properties.get("context")),
            ban_id=ban_id,
        )

    async def _from_commune(self, lat: float, lon: float, ban_id: str) -> Location | None:
        payload = await self._http.get_json(
            "geo_api",
            _GEO_COMMUNES_URL,
            params={"lat": lat, "lon": lon, "fields": "code,nom,codesPostaux,region"},
        )
        if not isinstance(payload, list) or not payload:
            return None
        commune: dict[str, Any] = payload[0]
        postcodes = commune.get("codesPostaux") or []
        return Location(
            lat=lat,
            lon=lon,
            label=str(commune["nom"]),
            citycode=str(commune["code"]),
            postcode=postcodes[0] if len(postcodes) == 1 else None,
            city=str(commune["nom"]),
            region=(commune.get("region") or {}).get("nom"),
            ban_id=ban_id,
        )
