"""Sources adossées aux référentiels statiques de la base locale."""

from typing import Any

from app.core.errors import NoDataError, RepositoryError, SourceError
from app.core.geo import departement_code
from app.repositories.reference import ReferenceRepository
from app.services.providers.base import AuditContext, ProviderData

_SCHOOL_RADIUS_M = 1500
_SCHOOL_LIMIT = 15
_PERMIT_RADIUS_M = 150
_PERMIT_MAX_AGE_DAYS = 5 * 365
_PERMIT_LIMIT = 25
# Un projet d'au moins ce nombre de niveaux à proximité est signalé comme vis-à-vis potentiel.
_OVERLOOK_MIN_LEVELS = 3
_OVERLOOK_RADIUS_M = 60


def _ips_by_kind(
    rows: list[dict[str, Any]], benchmarks: dict[str, dict[str, float]]
) -> dict[str, dict[str, Any]]:
    by_kind: dict[str, list[float]] = {}
    for row in rows:
        if row.get("ips") is not None:
            by_kind.setdefault(str(row["type_etablissement"]), []).append(float(row["ips"]))
    return {
        kind: {
            "nb": len(scores),
            "ips_moyen": round(sum(scores) / len(scores), 1),
            "moyenne_departement": benchmarks.get(kind, {}).get("departement"),
            "moyenne_nationale": benchmarks.get(kind, {}).get("national"),
        }
        for kind, scores in sorted(by_kind.items())
    }


def _unavailable(exc: RepositoryError) -> SourceError:
    return SourceError("http_error", str(exc))


class CrimeProvider:
    name = "delinquance"

    def __init__(self, repository: ReferenceRepository) -> None:
        self._repository = repository

    async def fetch(self, ctx: AuditContext) -> ProviderData:
        try:
            rows = await self._repository.crime_indicators(ctx.commune_codes)
        except RepositoryError as exc:
            raise _unavailable(exc) from exc
        if not rows:
            raise NoDataError
        year = int(rows[0]["annee"])
        await self._add_benchmarks(ctx, rows, year)
        return ProviderData(data={"annee": year, "indicateurs": rows})

    async def _add_benchmarks(
        self, ctx: AuditContext, rows: list[dict[str, Any]], year: int
    ) -> None:
        """Ajoute à chaque indicateur ses repères : département, France, année précédente.

        Les repères sont un complément : s'ils manquent, les chiffres de la commune restent.
        """
        try:
            benchmarks = await self._repository.crime_benchmarks(
                year, departement_code(ctx.citycode)
            )
            previous = await self._repository.crime_rates(ctx.commune_codes, year - 1)
        except RepositoryError:
            return
        for row in rows:
            name = row["indicateur"]
            row["reperes"] = {
                "departement": benchmarks.get(name, {}).get("departement"),
                "national": benchmarks.get(name, {}).get("national"),
                "annee_precedente": previous.get(name),
            }


class PropertyTaxProvider:
    name = "taxe_fonciere"

    def __init__(self, repository: ReferenceRepository) -> None:
        self._repository = repository

    async def fetch(self, ctx: AuditContext) -> ProviderData:
        try:
            row = await self._repository.property_tax(ctx.commune_codes)
        except RepositoryError as exc:
            raise _unavailable(exc) from exc
        if row is None:
            raise NoDataError
        try:
            medians = await self._repository.property_tax_benchmarks(
                int(row["annee"]), departement_code(ctx.citycode)
            )
        except RepositoryError:
            medians = {}
        row["reperes"] = {
            "mediane_departement": medians.get("departement"),
            "mediane_nationale": medians.get("national"),
        }
        return ProviderData(data=row)


class SchoolsProvider:
    name = "ecoles"

    def __init__(self, repository: ReferenceRepository) -> None:
        self._repository = repository

    async def fetch(self, ctx: AuditContext) -> ProviderData:
        try:
            rows = await self._repository.schools_nearby(
                ctx.lat, ctx.lon, _SCHOOL_RADIUS_M, _SCHOOL_LIMIT
            )
        except RepositoryError as exc:
            raise _unavailable(exc) from exc
        if not rows:
            raise NoDataError
        scores = [row["ips"] for row in rows if row.get("ips") is not None]
        try:
            benchmarks = await self._repository.ips_benchmarks(departement_code(ctx.citycode))
        except RepositoryError:
            benchmarks = {}
        return ProviderData(
            data={
                "rayon_m": _SCHOOL_RADIUS_M,
                "ips_moyen": round(sum(scores) / len(scores), 1) if scores else None,
                # Un IPS d'école ne se compare pas à celui d'un lycée : moyenne par niveau.
                "par_type": _ips_by_kind(rows, benchmarks),
                "etablissements": rows,
            }
        )


class PermitsProvider:
    name = "permis_construire"

    def __init__(self, repository: ReferenceRepository) -> None:
        self._repository = repository

    async def fetch(self, ctx: AuditContext) -> ProviderData:
        try:
            rows = await self._repository.permits_nearby(
                ctx.lat, ctx.lon, _PERMIT_RADIUS_M, _PERMIT_MAX_AGE_DAYS, _PERMIT_LIMIT
            )
        except RepositoryError as exc:
            raise _unavailable(exc) from exc
        if not rows:
            raise NoDataError
        risky = [row for row in rows if _is_overlook_risk(row)]
        return ProviderData(
            data={
                "rayon_m": _PERMIT_RADIUS_M,
                "nb_permis": len(rows),
                "risque_vis_a_vis": bool(risky),
                "nb_projets_a_risque": len(risky),
                "permis": rows,
            }
        )


def _is_overlook_risk(permit: dict[str, Any]) -> bool:
    levels, distance = permit.get("nb_niveaux"), permit.get("distance_m")
    return (
        # Un permis géocodé au milieu de sa rue est trop imprécis pour conclure.
        permit.get("precision_geocodage") == "numero"
        and levels is not None
        and distance is not None
        and levels >= _OVERLOOK_MIN_LEVELS
        and distance <= _OVERLOOK_RADIUS_M
    )
