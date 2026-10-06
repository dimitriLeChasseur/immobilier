"""Fiches communales publiques, destinées au référencement.

Elles ne contiennent que des chiffres à l'échelle de la commune, tirés des référentiels
locaux. Aucune vente DVF n'y figure : leurs conditions de réutilisation interdisent
l'indexation des mutations par les moteurs de recherche.
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Protocol

from app.core.errors import SourceError
from app.core.geo import commune_codes, departement_code
from app.core.http import HttpClient
from app.schemas.commune import (
    Benchmark,
    CommuneCrime,
    CommuneHousing,
    CommuneProfile,
    CommuneTax,
    SchoolLevel,
)

_GEO_URL = "https://geo.api.gouv.fr/communes"
_FIELDS = "nom,code,population,departement,codesPostaux,centre"
_CODE = re.compile(r"^[0-9][0-9AB][0-9]{3}$")
_SLUG_NOISE = re.compile(r"[^a-z0-9]+")
_BURGLARY = "Cambriolages de logement"
_PERCENT = 100.0


def slugify(name: str, code: str) -> str:
    """Segment d'URL d'une commune : « angers-49007 »."""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return f"{_SLUG_NOISE.sub('-', plain).strip('-')}-{code.lower()}"


def code_from_slug(slug: str) -> str | None:
    """Code INSEE porté par un segment d'URL, None s'il n'en a pas la forme."""
    code = slug.rsplit("-", 1)[-1].upper()
    return code if _CODE.match(code) else None


@dataclass(frozen=True, slots=True)
class CommuneIdentity:
    code: str
    name: str
    departement_code: str
    departement_name: str
    population: int | None
    postcodes: tuple[str, ...]
    centre: tuple[float, float] | None


def parse_identity(row: Any) -> CommuneIdentity | None:
    if not isinstance(row, dict):
        return None
    code, name = row.get("code"), row.get("nom")
    if not isinstance(code, str) or not isinstance(name, str) or not _CODE.match(code):
        return None
    departement = row.get("departement") or {}
    coordinates = (row.get("centre") or {}).get("coordinates")
    population = row.get("population")
    return CommuneIdentity(
        code=code,
        name=name,
        departement_code=str(departement.get("code") or departement_code(code)),
        departement_name=str(departement.get("nom") or ""),
        population=population if isinstance(population, int) else None,
        postcodes=tuple(str(item) for item in row.get("codesPostaux") or []),
        centre=(float(coordinates[0]), float(coordinates[1]))
        if isinstance(coordinates, list) and len(coordinates) >= 2  # noqa: PLR2004
        else None,
    )


class CommuneRepository(Protocol):
    async def property_tax(self, codes: list[str]) -> dict[str, Any] | None: ...

    async def property_tax_benchmarks(self, year: int, departement: str) -> dict[str, float]: ...

    async def crime_indicators(self, codes: list[str]) -> list[dict[str, Any]]: ...

    async def crime_benchmarks(
        self, year: int, departement: str
    ) -> dict[str, dict[str, float]]: ...

    async def crime_rates(self, codes: list[str], year: int) -> dict[str, float]: ...

    async def ips_benchmarks(self, departement: str) -> dict[str, dict[str, float]]: ...

    async def commune_schools(self, code: str) -> list[dict[str, Any]]: ...

    async def commune_housing(self, code: str) -> dict[str, Any] | None: ...

    async def connectivity(self, codes: list[str]) -> dict[str, Any] | None: ...


def _share(part: Any, total: Any) -> float | None:
    if not isinstance(part, int | float) or not isinstance(total, int | float) or not total:
        return None
    return round(_PERCENT * part / total, 1)


class CommuneService:
    def __init__(self, http: HttpClient, repository: CommuneRepository) -> None:
        self._http = http
        self._repository = repository

    async def identity(self, code: str) -> CommuneIdentity | None:
        """Commune désignée par ce code INSEE, None si elle n'existe pas."""
        try:
            payload = await self._http.get_json(
                "geo_api", f"{_GEO_URL}/{code}", params={"fields": _FIELDS}
            )
        except SourceError as exc:
            if exc.kind == "not_found":
                return None
            raise
        return parse_identity(payload)

    async def directory(self) -> list[CommuneIdentity]:
        """Toutes les communes, de la plus peuplée à la moins peuplée."""
        payload = await self._http.get_json(
            "geo_api", _GEO_URL, params={"fields": _FIELDS, "type": "commune-actuelle"}
        )
        rows = payload if isinstance(payload, list) else []
        communes = [identity for row in rows if (identity := parse_identity(row)) is not None]
        return sorted(communes, key=lambda commune: -(commune.population or 0))

    async def profile(self, identity: CommuneIdentity) -> CommuneProfile:
        codes = commune_codes(identity.code)
        departement = identity.departement_code
        connectivity = await self._repository.connectivity(codes)
        return CommuneProfile(
            code=identity.code,
            nom=identity.name,
            slug=slugify(identity.name, identity.code),
            departement_code=departement,
            departement_nom=identity.departement_name,
            population=identity.population,
            codes_postaux=list(identity.postcodes),
            centre=identity.centre,
            taxe_fonciere=await self._tax(codes, departement),
            delinquance=await self._crime(codes, departement),
            ecoles=await self._schools(identity.code, departement),
            part_fibre_pct=_share(
                (connectivity or {}).get("eligibles_fibre"), (connectivity or {}).get("nb_locaux")
            ),
            logement=await self._housing(identity.code),
        )

    async def _tax(self, codes: list[str], departement: str) -> CommuneTax | None:
        row = await self._repository.property_tax(codes)
        if row is None or row.get("taux_tfb_total") is None:
            return None
        year = int(row["annee"])
        medians = await self._repository.property_tax_benchmarks(year, departement)
        return CommuneTax(
            annee=year,
            taux_tfb_total=Benchmark(
                valeur=float(row["taux_tfb_total"]),
                departement=medians.get("departement"),
                national=medians.get("national"),
            ),
            taux_teom=row.get("taux_teom"),
        )

    async def _crime(self, codes: list[str], departement: str) -> CommuneCrime | None:
        rows = await self._repository.crime_indicators(codes)
        burglaries = next((row for row in rows if row.get("indicateur") == _BURGLARY), None)
        if burglaries is None or burglaries.get("taux_pour_mille") is None:
            return None
        year = int(burglaries["annee"])
        benchmarks = (await self._repository.crime_benchmarks(year, departement)).get(_BURGLARY, {})
        previous = await self._repository.crime_rates(codes, year - 1)
        return CommuneCrime(
            annee=year,
            cambriolages=Benchmark(
                valeur=round(float(burglaries["taux_pour_mille"]), 2),
                departement=benchmarks.get("departement"),
                national=benchmarks.get("national"),
            ),
            annee_precedente=previous.get(_BURGLARY),
        )

    async def _schools(self, code: str, departement: str) -> dict[str, SchoolLevel]:
        rows = await self._repository.commune_schools(code)
        if not rows:
            return {}
        benchmarks = await self._repository.ips_benchmarks(departement)
        return {
            str(row["type_etablissement"]): SchoolLevel(
                nb=int(row["nb"]),
                ips_moyen=round(float(row["ips_moyen"]), 1),
                moyenne_nationale=benchmarks.get(str(row["type_etablissement"]), {}).get(
                    "national"
                ),
            )
            for row in rows
        }

    async def _housing(self, code: str) -> CommuneHousing | None:
        row = await self._repository.commune_housing(code)
        if row is None or not row.get("logements"):
            return None
        main_homes = row.get("residences_principales")
        return CommuneHousing(
            annee=int(row["annee"]),
            logements=round(float(row["logements"])),
            part_locataires_pct=_share(row.get("locataires"), main_homes),
            part_proprietaires_pct=_share(row.get("proprietaires"), main_homes),
            part_vacants_pct=_share(row.get("logements_vacants"), row.get("logements")),
        )
