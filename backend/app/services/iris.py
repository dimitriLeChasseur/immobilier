"""Quartier IRIS d'un point, d'après le découpage publié par l'IGN.

Deux sources de l'audit en ont besoin (occupation des logements, profil du quartier) : la
réponse est partagée, pour n'interroger l'IGN qu'une fois par adresse.
"""

import asyncio
from collections import OrderedDict
from dataclasses import dataclass

from app.core.http import HttpClient
from app.services.providers.apicarto import feature_properties

_WFS_URL = "https://data.geopf.fr/wfs/ows"
_MEMO_SIZE = 256


@dataclass(frozen=True, slots=True)
class Iris:
    code: str
    name: str | None


class IrisLocator:
    def __init__(self, http: HttpClient) -> None:
        self._http = http
        # Recherches en cours ou récentes, par point : deux demandes simultanées pour la même
        # adresse attendent la même réponse.
        self._lookups: OrderedDict[tuple[float, float], asyncio.Task[Iris | None]] = OrderedDict()

    async def locate(self, lat: float, lon: float) -> Iris | None:
        """IRIS contenant le point, None hors découpage. Lève SourceError si l'IGN échoue."""
        key = (lat, lon)
        lookup = self._lookups.get(key)
        if lookup is None:
            lookup = asyncio.ensure_future(self._fetch(lat, lon))
            self._lookups[key] = lookup
            while len(self._lookups) > _MEMO_SIZE:
                self._lookups.popitem(last=False)
        try:
            # shield : l'abandon d'un demandeur (délai dépassé) n'annule pas la recherche
            # dont l'autre source attend encore le résultat.
            return await asyncio.shield(lookup)
        except BaseException:
            # Un échec n'est pas mémorisé : la prochaine demande réinterroge l'IGN.
            if self._lookups.get(key) is lookup and (lookup.done() or lookup.cancelled()):
                self._lookups.pop(key, None)
            raise

    async def _fetch(self, lat: float, lon: float) -> Iris | None:
        payload = await self._http.get_json(
            "ign_wfs",
            _WFS_URL,
            params={
                "SERVICE": "WFS",
                "VERSION": "2.0.0",
                "REQUEST": "GetFeature",
                "TYPENAMES": "STATISTICALUNITS.IRISGE:iris_ge",
                "OUTPUTFORMAT": "application/json",
                "PROPERTYNAME": "code_iris,nom_iris",
                "CQL_FILTER": f"INTERSECTS(geometrie,SRID=4326;POINT({lon} {lat}))",
            },
        )
        zones = feature_properties(payload)
        if not zones or not isinstance(zones[0].get("code_iris"), str):
            return None
        name = zones[0].get("nom_iris")
        return Iris(zones[0]["code_iris"], name if isinstance(name, str) else None)
