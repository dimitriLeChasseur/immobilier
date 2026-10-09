"""Marché locatif : loyers d'annonce par commune (data.gouv)."""

from collections.abc import Mapping
from typing import Any

from app.core.errors import NoDataError, RepositoryError, SourceError
from app.core.http import HttpClient
from app.repositories.reference import ReferenceRepository
from app.services.providers.base import (
    AuditContext,
    ProviderData,
    as_rows,
    gather_parts,
    to_float,
)

_TABULAR_URL = "https://tabular-api.data.gouv.fr/api/resources"


class RentsProvider:
    """« Carte des loyers » (ANIL / ministère) : loyer d'annonce prédit par commune."""

    name = "loyers"

    def __init__(
        self,
        http: HttpClient,
        *,
        resource_id: str,
        millesime: int,
        typology_resources: Mapping[str, str] | None = None,
        repository: ReferenceRepository | None = None,
    ) -> None:
        self._http = http
        self._repository = repository
        self._url = f"{_TABULAR_URL}/{resource_id}/data/"
        self._millesime = millesime
        self._typologies = dict(typology_resources or {})

    async def fetch(self, ctx: AuditContext) -> ProviderData:
        local = await self._local(ctx)
        if local is not None:
            return ProviderData(data=local)
        # Référentiel non ingéré ou commune absente : repli sur l'API tabulaire de data.gouv.
        row = await self._row(self._url, ctx)
        if row is None:
            raise NoDataError
        data = self._format(row)
        # Complément : son absence ne retire pas le loyer principal.
        typologies, missing = await self._by_typology(ctx)
        data["par_typologie"] = typologies
        return ProviderData(data=data, missing=missing)

    async def _local(self, ctx: AuditContext) -> dict[str, Any] | None:
        """Loyers lus dans le référentiel local, None s'il ne connaît pas cette commune."""
        if self._repository is None:
            return None
        try:
            for code in ctx.commune_codes:
                rents = await self._repository.commune_rents(code)
                if "appartement" in rents:
                    return _from_reference(rents)
        except RepositoryError:
            return None
        return None

    async def _row(self, url: str, ctx: AuditContext) -> dict[str, Any] | None:
        for code in ctx.commune_codes:
            payload = await self._http.get_json(
                "data_gouv_tabular", url, params={"INSEE_C__exact": code, "page_size": 1}
            )
            rows = as_rows(payload, "data")
            if rows:
                return rows[0]
        return None

    async def _by_typology(self, ctx: AuditContext) -> tuple[dict[str, Any], tuple[str, ...]]:
        """Loyer par taille de logement ; une typologie sans réponse est simplement absente."""
        if not self._typologies:
            return {}, ()
        try:
            rows, missing = await gather_parts(
                {
                    name: self._row(f"{_TABULAR_URL}/{resource_id}/data/", ctx)
                    for name, resource_id in self._typologies.items()
                }
            )
        except SourceError:
            return {}, tuple(self._typologies)
        typologies = {
            name: {
                "loyer_m2_charges_comprises": round(predicted, 2),
                "nb_observations": row.get("nbobs_com"),
            }
            for name, row in rows.items()
            if row is not None and (predicted := to_float(row.get("loypredm2"))) is not None
        }
        return typologies, missing

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


def _rounded(value: Any) -> float | None:
    number = to_float(value)
    return round(number, 2) if number is not None else None


def _from_reference(rents: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Même forme que la réponse de l'API tabulaire, à partir du référentiel local."""
    flat = rents["appartement"]
    return {
        "type_bien": "appartement",
        "loyer_m2_charges_comprises": _rounded(flat["loyer_m2"]),
        "intervalle_prediction": [_rounded(flat["borne_basse"]), _rounded(flat["borne_haute"])],
        "nb_observations": flat["nb_observations"],
        "niveau_prediction": flat["niveau_prediction"],
        "millesime": flat["millesime"],
        "par_typologie": {
            kind: {
                "loyer_m2_charges_comprises": _rounded(row["loyer_m2"]),
                "nb_observations": row["nb_observations"],
                "niveau_prediction": row["niveau_prediction"],
            }
            for kind, row in rents.items()
            if kind != "appartement"
        },
    }
