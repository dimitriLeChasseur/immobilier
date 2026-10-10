"""Résolution serveur de la localisation (BAN, repli sur geo.api.gouv.fr)."""

import re
from typing import Any, NamedTuple, Protocol

from app.core.errors import SourceError
from app.core.geo import haversine_m
from app.core.http import HttpClient
from app.schemas.audit import Location
from app.services.providers.base import as_rows

_BAN_REVERSE_URL = "https://api-adresse.data.gouv.fr/reverse/"
_GEO_COMMUNES_URL = "https://geo.api.gouv.fr/communes"
_BAN_LOOKUP_URL = "https://plateforme.adresse.data.gouv.fr/lookup"
# Identifiant BAN d'un numéro : commune, voie, numéro, suffixe éventuel.
_HOUSE_NUMBER_ID = re.compile(r"^[0-9][0-9AB][0-9]{3}_[0-9a-z]{4,12}_[0-9]{5}(_[0-9a-z]{1,12})?$")
# Écart toléré entre le point demandé et la position du numéro dans la BAN. La recherche et
# la fiche du numéro donnent le même point à moins d'un mètre près : une marge courte suffit,
# et elle borne ce qu'un droit payé ouvre autour de l'adresse.
_SAME_PLACE_M = 15
_LEADING_DIGITS = re.compile(r"\d+")


def _region_from_context(context: Any) -> str | None:
    """Région d'un contexte BAN « 49, Maine-et-Loire, Pays de la Loire »."""
    if not isinstance(context, str) or "," not in context:
        return None
    return context.rsplit(",", 1)[1].strip() or None


def _address_label(address: dict[str, Any]) -> str | None:
    """« 10 Rue du Canal 49100 Angers » d'après la fiche BAN d'un numéro, None si incomplète."""
    street = (address.get("voie") or {}).get("nomVoie")
    city = (address.get("commune") or {}).get("nom")
    number = address.get("numero")
    if not isinstance(street, str) or not isinstance(city, str) or not isinstance(number, int):
        return None
    suffix = address.get("suffixe") if isinstance(address.get("suffixe"), str) else ""
    postcode = address.get("codePostal") if isinstance(address.get("codePostal"), str) else ""
    return " ".join(part for part in (f"{number}{suffix}", street, postcode, city) if part)


class _Chosen(NamedTuple):
    """Adresse choisie par l'utilisateur, confirmée par la BAN."""

    id: str
    label: str | None
    street: str | None
    number: int | None


def _street_and_number(properties: dict[str, Any]) -> tuple[str | None, int | None]:
    """Voie et numéro d'un résultat BAN : « street » pour un numéro, « name » pour une voie."""
    street = properties.get("street")
    if not isinstance(street, str) and properties.get("type") == "street":
        street = properties.get("name")
    # « 12 bis » : seul le numéro compte pour situer l'adresse dans un tronçon de voie.
    digits = _LEADING_DIGITS.match(str(properties.get("housenumber") or ""))
    return (street if isinstance(street, str) else None), (int(digits[0]) if digits else None)


class Geocoder(Protocol):
    async def reverse(self, lat: float, lon: float, ban_id: str) -> Location | None:
        """Localisation correspondant aux coordonnées, None si hors couverture."""
        ...


class BanGeocoder:
    """Géocodage inverse BAN ; si la BAN est indisponible, repli sur la commune."""

    def __init__(
        self,
        http: HttpClient,
        reverse_url: str = _BAN_REVERSE_URL,
        lookup_url: str = _BAN_LOOKUP_URL,
    ) -> None:
        self._http = http
        self._reverse_url = reverse_url
        self._lookup_url = lookup_url.rstrip("/")

    async def reverse(self, lat: float, lon: float, ban_id: str) -> Location | None:
        try:
            return await self._from_ban(lat, lon, ban_id)
        except SourceError:
            return await self._from_commune(lat, lon, ban_id)

    async def _from_ban(self, lat: float, lon: float, ban_id: str) -> Location | None:
        payload = await self._http.get_json(
            "ban", self._reverse_url, params={"lat": lat, "lon": lon, "limit": 1}
        )
        features = as_rows(payload, "features")
        if not features:
            return await self._from_commune(lat, lon, ban_id)
        properties: dict[str, Any] = features[0].get("properties") or {}
        citycode, address_id = properties.get("citycode"), properties.get("id")
        if not isinstance(citycode, str):
            raise SourceError("invalid_response", "citycode", transient=False)
        # L'adresse choisie par l'utilisateur prime sur la plus proche du point, si la BAN
        # confirme qu'elle se trouve bien là : deux adresses peuvent partager un même point.
        label = str(properties.get("label") or citycode)
        street, number = _street_and_number(properties)
        chosen = await self._chosen_address(ban_id, lat, lon)
        if chosen is not None:
            # L'en-tête du rapport nomme l'adresse choisie, pas sa voisine la plus proche.
            address_id, label = chosen.id, chosen.label or label
            street, number = chosen.street or street, chosen.number or number
        return Location(
            lat=lat,
            lon=lon,
            label=label,
            citycode=citycode,
            postcode=properties.get("postcode"),
            city=properties.get("city"),
            region=_region_from_context(properties.get("context")),
            ban_id=ban_id,
            adresse_id=address_id if isinstance(address_id, str) and address_id else None,
            voie=street,
            numero=number,
        )

    async def _chosen_address(self, ban_id: str, lat: float, lon: float) -> _Chosen | None:
        """Adresse désignée par `ban_id` si c'est un numéro situé au point demandé, None sinon.

        L'identifiant vient du navigateur : il n'est retenu qu'après vérification, car il
        fonde le droit d'accès payé et la fiche du bâtiment.
        """
        if not _HOUSE_NUMBER_ID.match(ban_id):
            return None
        try:
            payload = await self._http.get_json("ban_lookup", f"{self._lookup_url}/{ban_id}")
        except SourceError:
            return None
        if not isinstance(payload, dict) or payload.get("type") != "numero":
            return None
        coordinates = (payload.get("position") or {}).get("coordinates")
        if not isinstance(coordinates, list) or len(coordinates) < 2:  # noqa: PLR2004
            return None
        try:
            distance = haversine_m(lat, lon, float(coordinates[1]), float(coordinates[0]))
        except (TypeError, ValueError):
            return None
        if distance > _SAME_PLACE_M:
            return None
        street, number = (payload.get("voie") or {}).get("nomVoie"), payload.get("numero")
        return _Chosen(
            ban_id,
            _address_label(payload),
            street if isinstance(street, str) else None,
            number if isinstance(number, int) else None,
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
