"""API Carto IGN : parcelle cadastrale et zonage d'urbanisme (PLU)."""

import json
from typing import Any

from app.core.errors import NoDataError, SourceError
from app.core.http import HttpClient
from app.services.providers.base import AuditContext, ProviderData, as_rows, gather_parts

_BASE_URL = "https://apicarto.ign.fr/api"
_BAN_LOOKUP_URL = "https://plateforme.adresse.data.gouv.fr/lookup"
_PARCEL_ID_LENGTHS = (14, 15)

# Points de la voie transmis à l'API pour retrouver les zones qu'elle traverse.
_STREET_SAMPLES = 12


def point_geojson(ctx: AuditContext) -> str:
    return json.dumps({"type": "Point", "coordinates": [ctx.lon, ctx.lat]})


def feature_properties(payload: Any) -> list[dict[str, Any]]:
    return [feature.get("properties") or {} for feature in as_rows(payload, "features")]


class CadastreProvider:
    name = "cadastre"

    def __init__(self, http: HttpClient) -> None:
        self._http = http

    async def fetch(self, ctx: AuditContext) -> ProviderData:
        if ctx.street is not None:
            # Une voie n'a pas de parcelle : le centre de la rue tombe sur le domaine public.
            raise NoDataError
        payload = await self._http.get_json(
            "apicarto_parcelle",
            f"{_BASE_URL}/cadastre/parcelle",
            params={"geom": point_geojson(ctx)},
        )
        parcels = feature_properties(payload)
        origin = "point"
        if not parcels:
            # En ville, le point d'une adresse est souvent posé sur la voie : on se rabat sur
            # les parcelles que la Base Adresse Nationale rattache à cette adresse.
            parcels, origin = await self._declared_parcels(ctx), "adresse"
        if not parcels:
            raise NoDataError
        parcel = parcels[0]
        return ProviderData(
            data={
                "identifiant": parcel.get("idu"),
                "section": parcel.get("section"),
                "numero": parcel.get("numero"),
                "contenance_m2": parcel.get("contenance"),
                "commune": parcel.get("nom_com"),
                # « point » : parcelle sous le point audité ; « adresse » : parcelle déclarée
                # pour cette adresse dans la Base Adresse Nationale.
                "origine": origin,
            }
        )

    async def _declared_parcels(self, ctx: AuditContext) -> list[dict[str, Any]]:
        if not ctx.address_id:
            return []
        try:
            address = await self._http.get_json("ban_lookup", f"{_BAN_LOOKUP_URL}/{ctx.address_id}")
        except SourceError:
            return []
        declared = address.get("parcelles") if isinstance(address, dict) else None
        reference = (
            parse_parcel_id(declared[0]) if isinstance(declared, list) and declared else None
        )
        if reference is None:
            return []
        section, number = reference
        payload = await self._http.get_json(
            "apicarto_parcelle",
            f"{_BASE_URL}/cadastre/parcelle",
            params={"code_insee": ctx.citycode, "section": section, "numero": number},
        )
        return feature_properties(payload)


def parse_parcel_id(value: Any) -> tuple[str, str] | None:
    """(section, numéro) d'un identifiant de parcelle tel que le publie la BAN.

    L'identifiant se termine toujours par la section (2 caractères) et le numéro (4 chiffres) ;
    ce qui précède (département, commune, préfixe) varie de 8 à 9 caractères selon la source.
    """
    if not isinstance(value, str) or len(value) not in _PARCEL_ID_LENGTHS:
        return None
    section, number = value[-6:-4].strip(), value[-4:]
    return (section.rjust(2, "0"), number) if section and number.isdigit() else None


class UrbanismeProvider:
    name = "urbanisme"

    def __init__(self, http: HttpClient) -> None:
        self._http = http

    async def fetch(self, ctx: AuditContext) -> ProviderData:
        # En mode « rue », toutes les zones traversées par la voie sont listées.
        geom = (
            json.dumps(ctx.street.multipoint(_STREET_SAMPLES), separators=(",", ":"))
            if ctx.street is not None
            else point_geojson(ctx)
        )
        parts, missing = await gather_parts(
            {
                "zones": self._layer("zone-urba", geom),
                # Servitudes d'utilité publique (abords de monument historique, plan de
                # prévention…) et prescriptions : au point audité, ou le long de la voie.
                "servitudes": self._layer("assiette-sup-s", geom),
                "prescriptions": self._layer("prescription-surf", geom),
            }
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
            for zone in parts.get("zones", [])
        ]
        # Une même zone peut ressortir plusieurs fois (une par point de la voie).
        zones = list({(zone["libelle"], zone["document"]): zone for zone in zones}.values())
        servitudes = _easements(parts.get("servitudes", []))
        prescriptions = _labels(parts.get("prescriptions", []))
        if not zones and not servitudes and not prescriptions:
            # Commune sans document d'urbanisme publié sur le Géoportail de l'urbanisme.
            raise NoDataError
        return ProviderData(
            data={"zones": zones, "servitudes": servitudes, "prescriptions": prescriptions},
            missing=missing,
        )

    async def _layer(self, layer: str, geom: str) -> list[dict[str, Any]]:
        payload = await self._http.get_json(
            "apicarto_gpu", f"{_BASE_URL}/gpu/{layer}", params={"geom": geom}
        )
        return feature_properties(payload)


# Catégories de servitudes les plus fréquentes ; les autres sont affichées par leur code.
_EASEMENT_KINDS = {
    "ac1": "Abords de monument historique",
    "ac2": "Site classé ou inscrit",
    "ac4": "Site patrimonial remarquable",
    "pm1": "Plan de prévention des risques naturels",
    "pm3": "Plan de prévention des risques technologiques",
    "i4": "Ligne électrique",
    "t1": "Voie ferrée",
    "t5": "Dégagement aéronautique",
    "el7": "Alignement de voirie",
    "as1": "Protection d'un captage d'eau",
}


def _easements(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Servitudes d'utilité publique couvrant le point, sans doublon."""
    found: dict[tuple[str, str], dict[str, Any]] = {}
    for feature in features:
        code = str(feature.get("suptype") or "").lower()
        detail = str(feature.get("typeass") or feature.get("nomass") or "").strip()
        if code:
            found[(code, detail)] = {
                "code": code.upper(),
                "categorie": _EASEMENT_KINDS.get(code, f"Servitude {code.upper()}"),
                "detail": detail or None,
            }
    return sorted(found.values(), key=lambda item: (item["code"], item["detail"] or ""))


def _labels(features: list[dict[str, Any]]) -> list[str]:
    return sorted({str(f["libelle"]).strip() for f in features if f.get("libelle")})
