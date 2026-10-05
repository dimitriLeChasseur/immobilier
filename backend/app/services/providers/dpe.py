"""ADEME : diagnostics de performance énergétique des logements voisins."""

from collections import Counter
from typing import Any

from app.core.errors import NoDataError
from app.core.http import HttpClient
from app.services.insights import energy_assessment
from app.services.providers.base import AuditContext, ProviderData, as_rows, to_float

_URL = "https://data.ademe.fr/data-fair/api/v1/datasets/dpe03existant/lines"
_RADIUS_M = 150
_SAMPLE_SIZE = 100
_NEAREST = 5
_FIELDS = "etiquette_dpe,etiquette_ges,date_etablissement_dpe"


class DpeProvider:
    name = "dpe"

    def __init__(self, http: HttpClient) -> None:
        self._http = http

    async def fetch(self, ctx: AuditContext) -> ProviderData:
        payload = await self._http.get_json(
            "ademe",
            _URL,
            params={
                "geo_distance": f"{ctx.lon},{ctx.lat},{_RADIUS_M}",
                "size": _SAMPLE_SIZE,
                "select": _FIELDS,
            },
        )
        rows = as_rows(payload, "results")
        if not rows:
            raise NoDataError
        energy = Counter(str(row["etiquette_dpe"]) for row in rows if row.get("etiquette_dpe"))
        climate = Counter(str(row["etiquette_ges"]) for row in rows if row.get("etiquette_ges"))
        return ProviderData(
            data={
                "rayon_m": _RADIUS_M,
                "nb_dpe_total": payload.get("total"),
                "nb_dpe_analyses": len(rows),
                "repartition_dpe": dict(sorted(energy.items())),
                "repartition_ges": dict(sorted(climate.items())),
                "etiquette_dominante": energy.most_common(1)[0][0] if energy else None,
                "analyse": energy_assessment(energy),
                "plus_proches": [_nearest(row) for row in rows[:_NEAREST]],
            }
        )


def _nearest(row: dict[str, Any]) -> dict[str, Any]:
    distance = to_float(row.get("_geo_distance"))
    return {
        "etiquette_dpe": row.get("etiquette_dpe"),
        "etiquette_ges": row.get("etiquette_ges"),
        "date": row.get("date_etablissement_dpe"),
        "distance_m": round(distance) if distance is not None else None,
    }
