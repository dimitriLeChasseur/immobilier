"""Sources adossées aux référentiels statiques de la base locale."""

from typing import Any

from app.core.errors import NoDataError, RepositoryError, SourceError
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
        return ProviderData(data={"annee": rows[0]["annee"], "indicateurs": rows})


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
        return ProviderData(
            data={
                "rayon_m": _SCHOOL_RADIUS_M,
                "ips_moyen": round(sum(scores) / len(scores), 1) if scores else None,
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
