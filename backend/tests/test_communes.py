"""Fiches communales publiques : identité, chiffres communaux, route."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_rate_limiter
from app.api.routers import communes
from app.api.routers.communes import get_commune_service
from app.core.errors import SourceError
from app.core.geo import commune_prefix
from app.core.rate_limit import SlidingWindowRateLimiter
from app.seo import parse_rents
from app.services.communes import (
    CommuneService,
    StaticRents,
    TabularRents,
    code_from_slug,
    parse_identity,
    slugify,
)

ANGERS = {
    "nom": "Angers",
    "code": "49007",
    "population": 159022,
    "codesPostaux": ["49000", "49100"],
    "centre": {"type": "Point", "coordinates": [-0.5629, 47.4819]},
    "departement": {"code": "49", "nom": "Maine-et-Loire"},
}


@pytest.mark.parametrize(
    ("name", "code", "slug"),
    [
        ("Angers", "49007", "angers-49007"),
        ("Saint-Étienne", "42218", "saint-etienne-42218"),
        ("L'Haÿ-les-Roses", "94038", "l-hay-les-roses-94038"),
        ("Ajaccio", "2A004", "ajaccio-2a004"),
    ],
)
def test_slug_round_trip(name: str, code: str, slug: str) -> None:
    assert slugify(name, code) == slug
    assert code_from_slug(slug) == code


@pytest.mark.parametrize("slug", ["angers", "angers-4900", "angers-490071", "", "x-../etc"])
def test_slug_without_a_commune_code_is_rejected(slug: str) -> None:
    assert code_from_slug(slug) is None


def test_arrondissement_cities_are_queried_by_their_arrondissement_prefix() -> None:
    assert [commune_prefix(code) for code in ("75056", "69123", "13055")] == ["751", "6938", "132"]
    assert commune_prefix("49007") == "49007"
    # Un arrondissement n'est pas la commune entière.
    assert commune_prefix("75101") == "75101"


def test_identity_parsing_tolerates_missing_optional_fields() -> None:
    identity = parse_identity(ANGERS)
    assert identity is not None
    assert (identity.name, identity.departement_name, identity.centre) == (
        "Angers",
        "Maine-et-Loire",
        (-0.5629, 47.4819),
    )
    bare = parse_identity({"nom": "Ajaccio", "code": "2A004"})
    assert bare is not None
    assert (bare.departement_code, bare.population, bare.centre) == ("2A", None, None)
    assert parse_identity({"nom": "x", "code": "abc"}) is None
    assert parse_identity(None) is None


class Repository:
    def __init__(self, empty: bool = False) -> None:
        self.empty = empty

    async def property_tax(self, codes: list[str]) -> dict[str, Any] | None:
        return None if self.empty else {"annee": 2025, "taux_tfb_total": 56.65, "taux_teom": 8.71}

    async def property_tax_benchmarks(self, year: int, departement: str) -> dict[str, float]:
        return {"departement": 46.57, "national": 40.33}

    async def crime_indicators(self, codes: list[str]) -> list[dict[str, Any]]:
        if self.empty:
            return []
        return [
            {"indicateur": "Vols de véhicule", "annee": 2025, "taux_pour_mille": 1.2},
            {"indicateur": "Cambriolages de logement", "annee": 2025, "taux_pour_mille": 1.6885},
        ]

    async def crime_benchmarks(self, year: int, departement: str) -> dict[str, dict[str, float]]:
        return {"Cambriolages de logement": {"departement": 1.97, "national": 3.27}}

    async def crime_rates(self, codes: list[str], year: int) -> dict[str, float]:
        return {"Cambriolages de logement": 2.29}

    async def ips_benchmarks(self, departement: str) -> dict[str, dict[str, float]]:
        return {"ecole": {"national": 104.8}}

    async def commune_schools(self, code: str) -> list[dict[str, Any]]:
        if self.empty:
            return []
        return [
            {"type_etablissement": "ecole", "nb": 52, "ips_moyen": 105.66},
            {"type_etablissement": "lycee", "nb": 13, "ips_moyen": 115.6},
        ]

    async def commune_housing(self, code: str) -> dict[str, Any] | None:
        if self.empty:
            return None
        return {
            "annee": 2022,
            "logements": 92383.0,
            "residences_principales": 80000.0,
            "logements_vacants": 5543.0,
            "proprietaires": 25920.0,
            "locataires": 53040.0,
        }

    async def connectivity(self, codes: list[str]) -> dict[str, Any] | None:
        return None if self.empty else {"nb_locaux": 1000, "eligibles_fibre": 973}


class FakeHttp:
    def __init__(self, outcome: Any) -> None:
        self._outcome = outcome
        self.urls: list[str] = []

    async def get_json(self, source: str, url: str, *, params: Any = None) -> Any:
        self.urls.append(url)
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


async def test_profile_gathers_commune_level_figures_with_their_benchmarks() -> None:
    service = CommuneService(FakeHttp(ANGERS), Repository())  # type: ignore[arg-type]
    identity = await service.identity("49007")
    assert identity is not None
    profile = await service.profile(identity)

    assert profile.slug == "angers-49007"
    assert profile.taxe_fonciere is not None
    assert profile.taxe_fonciere.taux_tfb_total.model_dump() == {
        "valeur": 56.65,
        "departement": 46.57,
        "national": 40.33,
    }
    assert profile.delinquance is not None
    assert profile.delinquance.cambriolages.valeur == 1.69
    assert profile.delinquance.annee_precedente == 2.29
    assert profile.ecoles["ecole"].model_dump() == {
        "nb": 52,
        "ips_moyen": 105.7,
        "moyenne_nationale": 104.8,
    }
    assert profile.ecoles["lycee"].moyenne_nationale is None
    assert profile.part_fibre_pct == 97.3
    assert profile.logement is not None
    assert (profile.logement.part_locataires_pct, profile.logement.part_vacants_pct) == (66.3, 6.0)
    # Aucune donnée à l'adresse ni vente DVF dans une fiche indexable.
    assert "dvf" not in profile.model_dump_json().lower()


async def test_profile_of_a_commune_absent_from_the_references_is_still_served() -> None:
    service = CommuneService(FakeHttp(ANGERS), Repository(empty=True))  # type: ignore[arg-type]
    identity = await service.identity("49007")
    assert identity is not None
    profile = await service.profile(identity)
    assert profile.nom == "Angers"
    assert (profile.taxe_fonciere, profile.delinquance, profile.logement) == (None, None, None)
    assert profile.ecoles == {}
    assert profile.part_fibre_pct is None


async def test_directory_ranks_communes_by_population() -> None:
    rows = [
        {"nom": "Petite", "code": "49001", "population": 300},
        ANGERS,
        {"nom": "x", "code": "?"},
    ]
    service = CommuneService(FakeHttp(rows), Repository())  # type: ignore[arg-type]
    assert [commune.name for commune in await service.directory()] == ["Angers", "Petite"]


def make_client(http: FakeHttp) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(communes.router)
    limiter = SlidingWindowRateLimiter(limit=20, window_s=60)
    service = CommuneService(http, Repository())  # type: ignore[arg-type]
    app.dependency_overrides[get_commune_service] = lambda: service
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    with TestClient(app) as client:
        yield client


def test_route_serves_a_cacheable_public_profile() -> None:
    client = next(make_client(FakeHttp(ANGERS)))
    response = client.get("/api/v1/communes/49007")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "public, max-age=86400"
    assert response.json()["nom"] == "Angers"


def test_route_rejects_malformed_codes_and_reports_unknown_or_unreachable() -> None:
    client = next(make_client(FakeHttp(ANGERS)))
    assert client.get("/api/v1/communes/4900").status_code == 422
    assert client.get("/api/v1/communes/49007x").status_code == 422

    unknown = next(make_client(FakeHttp(SourceError("not_found", "404", transient=False))))
    assert unknown.get("/api/v1/communes/99999").status_code == 404

    down = next(make_client(FakeHttp(SourceError("timeout"))))
    assert down.get("/api/v1/communes/49007").status_code == 503


async def test_rents_join_the_profile_and_their_absence_is_harmless() -> None:
    rents = StaticRents({"49007": {"appartement": 14.6, "t1_t2": 16.6}})
    service = CommuneService(FakeHttp(ANGERS), Repository(), rents)  # type: ignore[arg-type]
    identity = await service.identity("49007")
    assert identity is not None
    assert (await service.profile(identity)).loyers == {"appartement": 14.6, "t1_t2": 16.6}
    assert await rents.rents(["99999"]) == {}

    class Tabular:
        async def get_json(self, source: str, url: str, *, params: Any = None) -> Any:
            if "maisons" in url:
                raise SourceError("timeout")
            return {"data": [{"loypredm2": 14.5737 if "apparts" in url else None}]}

    live = TabularRents(Tabular(), {"appartement": "apparts", "maison": "maisons", "t1_t2": "vide"})  # type: ignore[arg-type]
    assert await live.rents(["49007"]) == {"appartement": 14.6}


def test_bulk_rent_file_uses_semicolons_and_decimal_commas() -> None:
    content = (
        b'"id_zone";"INSEE_C";"LIBGEO";"loypredm2"\r\n'
        b'"1";"49007";"Angers";14,5737\r\n'
        b'"2";"05066";"La Haute-Beaume";9,7576\r\n'
        b'"3";"00000";"Sans valeur";\r\n'
    )
    assert parse_rents(content) == {"49007": 14.6, "05066": 9.8}
