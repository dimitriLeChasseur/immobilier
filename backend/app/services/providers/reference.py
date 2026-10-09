"""Sources adossées aux référentiels statiques de la base locale."""

from typing import Any

from app.core.errors import NoDataError, RepositoryError, SourceError
from app.core.geo import departement_code
from app.repositories.reference import ReferenceRepository
from app.services.providers.base import AuditContext, ProviderData
from app.services.providers.higher_education import HigherEducationFinder
from app.services.school_sectors import resolve_sector
from app.services.street import normalize_street_name

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

    def __init__(
        self, repository: ReferenceRepository, higher_education: HigherEducationFinder | None = None
    ) -> None:
        self._repository = repository
        self._higher_education = higher_education

    async def fetch(self, ctx: AuditContext) -> ProviderData:
        try:
            rows = await self._repository.schools_nearby(
                ctx.lat, ctx.lon, _SCHOOL_RADIUS_M, _SCHOOL_LIMIT
            )
        except RepositoryError as exc:
            raise _unavailable(exc) from exc
        higher, missing = await self._higher(ctx)
        if not rows and not (higher or {}).get("etablissements"):
            if missing:
                # Rien en base et l'enseignement supérieur n'a pas répondu : on ne conclut pas.
                raise SourceError("http_error", "esr")
            raise NoDataError
        scores = [row["ips"] for row in rows if row.get("ips") is not None]
        try:
            benchmarks = await self._repository.ips_benchmarks(departement_code(ctx.citycode))
        except RepositoryError:
            benchmarks = {}
        data: dict[str, Any] = {
            "rayon_m": _SCHOOL_RADIUS_M,
            "ips_moyen": round(sum(scores) / len(scores), 1) if scores else None,
            # Un IPS d'école ne se compare pas à celui d'un lycée : moyenne par niveau.
            "par_type": _ips_by_kind(rows, benchmarks),
            "etablissements": rows,
        }
        if higher is not None:
            data["superieur"] = higher
        try:
            data["college_secteur"] = await self._sector(ctx)
        except RepositoryError:
            missing = (*missing, "college_secteur")
        return ProviderData(data=data, missing=missing)

    async def _sector(self, ctx: AuditContext) -> dict[str, Any]:
        """Collège public de secteur de l'adresse, d'après la carte scolaire."""
        street = normalize_street_name(ctx.street_name)
        rows, nb_colleges = await self._repository.school_sector(ctx.citycode, street)
        status, uais = resolve_sector(rows, nb_colleges, ctx.house_number)
        colleges = await self._repository.colleges(uais, ctx.lat, ctx.lon) if uais else []
        known = {college["uai"] for college in colleges}
        return {
            "statut": status,
            # Un collège absent du référentiel des établissements garde au moins son identifiant.
            "colleges": colleges + [{"uai": uai} for uai in uais if uai not in known],
            "nb_colleges_commune": nb_colleges,
        }

    async def _higher(self, ctx: AuditContext) -> tuple[dict[str, Any] | None, tuple[str, ...]]:
        """Enseignement supérieur à proximité ; son absence de réponse ne retire pas les écoles."""
        if self._higher_education is None:
            return None, ()
        try:
            found, incomplete = await self._higher_education.nearby(ctx)
        except SourceError:
            return None, ("superieur",)
        return found, ("superieur",) if incomplete else ()


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
