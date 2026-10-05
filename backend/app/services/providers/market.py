"""Marché locatif : loyers d'annonce par commune (data.gouv)."""

from typing import Any

from app.core.errors import NoDataError
from app.core.http import HttpClient
from app.services.providers.base import AuditContext, ProviderData, as_rows, to_float

_TABULAR_URL = "https://tabular-api.data.gouv.fr/api/resources"


class RentsProvider:
    """« Carte des loyers » (ANIL / ministère) : loyer d'annonce prédit par commune."""

    name = "loyers"

    def __init__(self, http: HttpClient, *, resource_id: str, millesime: int) -> None:
        self._http = http
        self._url = f"{_TABULAR_URL}/{resource_id}/data/"
        self._millesime = millesime

    async def fetch(self, ctx: AuditContext) -> ProviderData:
        for code in ctx.commune_codes:
            payload = await self._http.get_json(
                "data_gouv_tabular", self._url, params={"INSEE_C__exact": code, "page_size": 1}
            )
            rows = as_rows(payload, "data")
            if rows:
                return ProviderData(data=self._format(rows[0]))
        raise NoDataError

    def _format(self, row: dict[str, Any]) -> dict[str, Any]:
        predicted = to_float(row.get("loypredm2"))
        low, high = to_float(row.get("lwr.IPm2")), to_float(row.get("upr.IPm2"))
        return {
            "type_bien": "appartement",
            "loyer_m2_charges_comprises": round(predicted, 2) if predicted is not None else None,
            "intervalle_prediction": [
                round(low, 2) if low is not None else None,
                round(high, 2) if high is not None else None,
            ],
            "nb_observations": row.get("nbobs_com"),
            "niveau_prediction": row.get("TYPPRED"),
            "millesime": self._millesime,
        }
