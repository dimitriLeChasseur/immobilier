"""Profil du quartier : revenus, quartier prioritaire, évolution de la population."""

from typing import Any

from app.core.errors import NoDataError, RepositoryError, SourceError
from app.repositories.reference import ReferenceRepository
from app.services.iris import IrisLocator
from app.services.providers.base import AuditContext, ProviderData, gather_parts

# Au-delà, un quartier prioritaire n'est plus « voisin » de l'adresse.
_QPV_RADIUS_M = 500

# Repères nationaux de la même édition (INSEE, Filosofi 2021, France métropolitaine) : sans
# eux, un niveau de vie médian ne se lit pas.
NATIONAL_INCOME_BENCHMARKS: dict[int, dict[str, float]] = {
    2021: {"revenu_median": 23160, "taux_pauvrete_pct": 14.5},
}


def change_pct(current: Any, previous: Any) -> float | None:
    if not isinstance(current, int) or not isinstance(previous, int) or previous <= 0:
        return None
    return round(100 * (current - previous) / previous, 1)


class NeighbourhoodProvider:
    name = "quartier"

    def __init__(self, repository: ReferenceRepository, iris: IrisLocator) -> None:
        self._repository = repository
        self._iris = iris

    async def fetch(self, ctx: AuditContext) -> ProviderData:
        data, missing = await gather_parts(
            {
                "revenus": self._income(ctx),
                "quartier_prioritaire": self._priority_district(ctx),
                "population": self._population(ctx),
            }
        )
        # La recherche des revenus rend aussi l'identité du quartier, même sans chiffres.
        data.update(data.pop("revenus", None) or {"iris": None, "revenus": None})
        found = (
            data["revenus"] is not None
            or data.get("population") is not None
            or data.get("quartier_prioritaire") is not None
        )
        if not found and not missing:
            raise NoDataError
        return ProviderData(data=data, missing=missing)

    async def _income(self, ctx: AuditContext) -> dict[str, Any]:
        """Quartier IRIS et ses revenus, ceux de la commune à défaut.

        L'INSEE ne diffuse les revenus que pour les quartiers des communes les plus peuplées :
        ailleurs, ceux de la commune (ou de l'arrondissement) prennent le relais, et le champ
        « echelle » le dit. None si aucun des deux n'est publié.
        """
        iris = await self._iris.locate(ctx.lat, ctx.lon)
        identity = {"code": iris.code, "nom": iris.name} if iris is not None else None
        try:
            row = await self._repository.iris_income(iris.code) if iris is not None else None
            scale = "iris"
            if row is None or row["revenu_median"] is None:
                row, scale = await self._repository.commune_income(ctx.commune_codes), "commune"
        except RepositoryError as exc:
            raise SourceError("http_error", str(exc)) from exc
        if row is None:
            return {"iris": identity, "revenus": None}
        return {
            "iris": identity,
            "revenus": {
                "annee": row["annee"],
                "echelle": scale,
                # Vrai quand le chiffre communal est celui de l'arrondissement.
                "arrondissement": scale == "commune" and row["code_insee"] != ctx.commune_codes[-1],
                "revenu_median": row["revenu_median"],
                "revenu_q1": row["revenu_q1"],
                "revenu_q3": row["revenu_q3"],
                "taux_pauvrete_pct": row["taux_pauvrete_pct"],
                "reference_nationale": NATIONAL_INCOME_BENCHMARKS.get(row["annee"]),
            },
        }

    async def _priority_district(self, ctx: AuditContext) -> dict[str, Any] | None:
        """Quartier prioritaire de la politique de la ville, à l'adresse ou à proximité.

        Sans nom, l'objet signifie « aucun quartier prioritaire à moins de 500 m ». None si
        les périmètres ne sont pas chargés : on ne conclut pas à l'absence sans donnée.
        """
        try:
            row = await self._repository.priority_district(ctx.lat, ctx.lon, _QPV_RADIUS_M)
            if row is None and not await self._repository.priority_districts_loaded():
                return None
        except RepositoryError as exc:
            raise SourceError("http_error", str(exc)) from exc
        if row is None:
            return {"dans_un_quartier": False, "rayon_m": _QPV_RADIUS_M}
        return {
            "dans_un_quartier": row["distance_m"] == 0,
            "code": row["code_qp"],
            "nom": row["nom"],
            "commune": row["commune"],
            "distance_m": row["distance_m"],
            "rayon_m": _QPV_RADIUS_M,
        }

    async def _population(self, ctx: AuditContext) -> dict[str, Any] | None:
        try:
            row = await self._repository.population(ctx.commune_codes)
        except RepositoryError as exc:
            raise SourceError("http_error", str(exc)) from exc
        if row is None:
            return None
        return {
            "annee": row["annee"],
            "habitants": row["population"],
            "evolution_6_ans_pct": change_pct(row["population"], row["population_6"]),
            "evolution_11_ans_pct": change_pct(row["population"], row["population_11"]),
            # Vrai quand le chiffre est celui de l'arrondissement, pas de la commune entière.
            "arrondissement": row["code_insee"] != ctx.commune_codes[-1],
        }
