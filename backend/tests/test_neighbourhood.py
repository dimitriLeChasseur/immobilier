"""Profil du quartier : revenus à l'IRIS, quartier prioritaire, évolution de la population."""

import asyncio
import json
from typing import Any

import pytest

from app.core.errors import NoDataError, RepositoryError, SourceError
from app.ingestion.datasets import (
    parse_commune_income_row,
    parse_iris_income_row,
    parse_population_row,
    parse_priority_district,
)
from app.services.iris import Iris, IrisLocator
from app.services.providers.base import AuditContext
from app.services.providers.neighbourhood import NeighbourhoodProvider
from app.services.teaser import LOCKED, mask_data

ANGERS = AuditContext(lat=47.47, lon=-0.55, citycode="49007")
PARIS_1 = AuditContext(lat=48.86, lon=2.33, citycode="75101")
INCOME = {
    "annee": 2021,
    "revenu_median": 27000,
    "revenu_q1": 17570,
    "revenu_q3": 40070,
    "taux_pauvrete_pct": 17.0,
}
POPULATION = {
    "code_insee": "49007",
    "annee": 2022,
    "population": 157555,
    "population_6": 151229,
    "population_11": 148803,
}
VOLTAIRE = Iris("490070105", "Voltaire")
DISTRICT = {"code_qp": "QN04901M", "nom": "Belle Beille", "commune": "Angers", "distance_m": 15}


class FakeIris:
    def __init__(self, iris: Iris | None = VOLTAIRE, fails: bool = False) -> None:
        self._iris, self._fails = iris, fails

    async def locate(self, lat: float, lon: float) -> Iris | None:
        if self._fails:
            raise SourceError("timeout", "ign_wfs")
        return self._iris


class FakeRepository:
    def __init__(
        self,
        income: dict[str, Any] | None = None,
        population: dict[str, Any] | None = None,
        district: dict[str, Any] | None = None,
        districts_loaded: bool = True,
        broken: bool = False,
        commune_income: dict[str, Any] | None = None,
    ) -> None:
        self._commune_income = commune_income
        self.income_queries: list[list[str]] = []
        self._income, self._population, self._district = income, population, district
        self._loaded, self._broken = districts_loaded, broken
        self.population_queries: list[list[str]] = []

    async def iris_income(self, code_iris: str) -> dict[str, Any] | None:
        return self._income

    async def commune_income(self, codes: list[str]) -> dict[str, Any] | None:
        self.income_queries.append(codes)
        return self._commune_income

    async def population(self, codes: list[str]) -> dict[str, Any] | None:
        self.population_queries.append(codes)
        return self._population

    async def priority_district(
        self, lat: float, lon: float, radius_m: int
    ) -> dict[str, Any] | None:
        if self._broken:
            raise RepositoryError("down")
        return self._district

    async def priority_districts_loaded(self) -> bool:
        return self._loaded


def provider(repository: FakeRepository, iris: FakeIris | None = None) -> NeighbourhoodProvider:
    return NeighbourhoodProvider(repository, iris or FakeIris())  # type: ignore[arg-type]


async def test_profile_gathers_income_population_and_nearby_priority_district() -> None:
    result = await provider(FakeRepository(INCOME, POPULATION, DISTRICT)).fetch(ANGERS)

    assert result.missing == ()
    assert result.data["iris"] == {"code": "490070105", "nom": "Voltaire"}
    assert result.data["revenus"] == {
        **INCOME,
        "echelle": "iris",
        "arrondissement": False,
        # Repère de la même édition : sans lui, un niveau de vie médian ne se lit pas.
        "reference_nationale": {"revenu_median": 23160, "taux_pauvrete_pct": 14.5},
    }
    assert result.data["population"] == {
        "annee": 2022,
        "habitants": 157555,
        "evolution_6_ans_pct": 4.2,
        "evolution_11_ans_pct": 5.9,
        "arrondissement": False,
    }
    # À 15 m du périmètre : voisin, pas dedans.
    assert result.data["quartier_prioritaire"] == {
        "dans_un_quartier": False,
        "code": "QN04901M",
        "nom": "Belle Beille",
        "commune": "Angers",
        "distance_m": 15,
        "rayon_m": 500,
    }


async def test_address_inside_a_priority_district() -> None:
    inside = FakeRepository(INCOME, POPULATION, DISTRICT | {"distance_m": 0})
    result = await provider(inside).fetch(ANGERS)
    assert result.data["quartier_prioritaire"]["dans_un_quartier"] is True


async def test_no_district_nearby_is_stated_only_when_boundaries_are_loaded() -> None:
    loaded = await provider(FakeRepository(INCOME, POPULATION)).fetch(ANGERS)
    assert loaded.data["quartier_prioritaire"] == {"dans_un_quartier": False, "rayon_m": 500}

    # Table vide : on ne conclut pas à l'absence de quartier prioritaire.
    empty = await provider(FakeRepository(INCOME, POPULATION, districts_loaded=False)).fetch(ANGERS)
    assert empty.data["quartier_prioritaire"] is None


async def test_income_not_published_keeps_the_neighbourhood_name() -> None:
    result = await provider(FakeRepository(None, POPULATION)).fetch(ANGERS)
    assert result.data["iris"] == {"code": "490070105", "nom": "Voltaire"}
    assert result.data["revenus"] is None

    outside = await provider(FakeRepository(INCOME, POPULATION), FakeIris(None)).fetch(ANGERS)
    assert outside.data["iris"] is None and outside.data["revenus"] is None


async def test_commune_income_takes_over_when_the_neighbourhood_has_none() -> None:
    commune = {**INCOME, "code_insee": "49007", "revenu_median": 22000}
    # Quartier sans chiffres, quartier au seul taux de pauvreté, adresse hors de tout IRIS.
    for repository, iris in (
        (FakeRepository(None, POPULATION, commune_income=commune), FakeIris()),
        (
            FakeRepository({**INCOME, "revenu_median": None}, POPULATION, commune_income=commune),
            FakeIris(),
        ),
        (FakeRepository(INCOME, POPULATION, commune_income=commune), FakeIris(None)),
    ):
        result = await provider(repository, iris).fetch(ANGERS)
        assert repository.income_queries == [["49007"]]
        assert result.data["revenus"]["echelle"] == "commune"
        assert result.data["revenus"]["revenu_median"] == 22000
        assert result.data["revenus"]["arrondissement"] is False
        assert "code_insee" not in result.data["revenus"]

    # Un quartier diffusé n'interroge pas la commune.
    known = FakeRepository(INCOME, POPULATION, commune_income=commune)
    assert (await provider(known).fetch(ANGERS)).data["revenus"]["echelle"] == "iris"
    assert known.income_queries == []

    paris = FakeRepository(None, POPULATION, commune_income={**commune, "code_insee": "75101"})
    result = await provider(paris).fetch(PARIS_1)
    assert paris.income_queries == [["75101", "75056"]]
    assert result.data["revenus"]["arrondissement"] is True


async def test_arrondissement_population_is_flagged_and_new_communes_have_no_trend() -> None:
    repository = FakeRepository(
        INCOME, {**POPULATION, "code_insee": "75101", "population_6": None, "population_11": 0}
    )
    result = await provider(repository).fetch(PARIS_1)
    assert repository.population_queries == [["75101", "75056"]]
    assert result.data["population"]["arrondissement"] is True
    assert result.data["population"]["evolution_6_ans_pct"] is None
    assert result.data["population"]["evolution_11_ans_pct"] is None


async def test_partial_failures_are_reported_not_fatal() -> None:
    result = await provider(FakeRepository(INCOME, POPULATION), FakeIris(fails=True)).fetch(ANGERS)
    assert result.missing == ("revenus",)
    assert result.data["revenus"] is None and result.data["iris"] is None
    assert result.data["population"]["habitants"] == 157555

    broken = await provider(FakeRepository(INCOME, POPULATION, broken=True)).fetch(ANGERS)
    assert broken.missing == ("quartier_prioritaire",)
    assert broken.data["revenus"]["revenu_median"] == 27000


async def test_nothing_known_is_an_empty_source() -> None:
    with pytest.raises(NoDataError):
        await provider(FakeRepository(districts_loaded=False), FakeIris(None)).fetch(ANGERS)


def test_only_the_commune_population_is_free_in_the_teaser() -> None:
    masked = mask_data(
        "quartier",
        {
            "iris": {"code": "490070105", "nom": "Voltaire"},
            "population": {"habitants": 157555},
            "revenus": INCOME,
            "quartier_prioritaire": DISTRICT,
        },
    )
    assert masked["iris"] == {"code": "490070105", "nom": "Voltaire"}
    assert masked["population"] == {"habitants": 157555}
    assert masked["revenus"] == LOCKED and masked["quartier_prioritaire"] == LOCKED
    assert "27000" not in json.dumps(masked) and "Belle Beille" not in json.dumps(masked)


# --- Localisation de l'IRIS ---------------------------------------------------------------


class CountingHttp:
    def __init__(self, zones: list[dict[str, Any]], failures: int = 0) -> None:
        self._zones, self._failures = zones, failures
        self.calls = 0

    async def get_json(self, source: str, url: str, *, params: Any = None) -> Any:
        self.calls += 1
        await asyncio.sleep(0)
        if self.calls <= self._failures:
            raise SourceError("http_error", "503")
        assert "POINT(-0.55 47.47)" in params["CQL_FILTER"]
        return {"features": [{"properties": zone} for zone in self._zones]}


async def test_two_sources_asking_for_the_same_point_share_one_request() -> None:
    http = CountingHttp([{"code_iris": "490070105", "nom_iris": "Voltaire"}])
    locator = IrisLocator(http)  # type: ignore[arg-type]

    first, second = await asyncio.gather(locator.locate(47.47, -0.55), locator.locate(47.47, -0.55))

    assert first == second == Iris("490070105", "Voltaire")
    assert await locator.locate(47.47, -0.55) == first
    assert http.calls == 1


async def test_a_failed_lookup_is_not_remembered() -> None:
    http = CountingHttp([{"code_iris": "490070105", "nom_iris": None}], failures=1)
    locator = IrisLocator(http)  # type: ignore[arg-type]

    with pytest.raises(SourceError):
        await locator.locate(47.47, -0.55)
    assert await locator.locate(47.47, -0.55) == Iris("490070105", None)
    assert http.calls == 2


async def test_a_point_outside_any_neighbourhood_has_no_iris() -> None:
    assert await IrisLocator(CountingHttp([])).locate(47.47, -0.55) is None  # type: ignore[arg-type]


# --- Lecture des fichiers -----------------------------------------------------------------


def test_iris_income_row_keeps_published_figures_only() -> None:
    row = {
        "IRIS": "490070101",
        "DISP_TP6021": "15,0",
        "DISP_Q121": "16980",
        "DISP_MED21": "23950",
        "DISP_Q321": "34630",
    }
    assert parse_iris_income_row(row) == ("490070101", 2021, 23950, 16980, 34630, 15.0)
    # Taux de pauvreté sous secret statistique : le reste est gardé.
    assert parse_iris_income_row(row | {"DISP_TP6021": "s"}) == (
        "490070101", 2021, 23950, 16980, 34630, None
    )  # fmt: skip
    hidden = dict.fromkeys(("DISP_TP6021", "DISP_Q121", "DISP_MED21", "DISP_Q321"), "ns")
    assert parse_iris_income_row(row | hidden) is None
    assert parse_iris_income_row(row | {"IRIS": "49007"}) is None


def test_population_row_rounds_census_estimates() -> None:
    assert parse_population_row("05046", ["6386.99999999999", "6173.99999999999", "6155"]) == (
        "05046", 2022, 6387, 6174, 6155
    )  # fmt: skip
    # Commune créée depuis : pas de population antérieure.
    assert parse_population_row("2A004", ["75343", "", "NA"]) == ("2A004", 2022, 75343, None, None)
    assert parse_population_row("05046", ["", "6174", "6155"]) is None
    assert parse_population_row("ZZZZZ", ["10", "10", "10"]) is None


def test_priority_district_feature() -> None:
    geometry = {"type": "MultiPolygon", "coordinates": [[[[0, 0], [1, 0], [1, 1], [0, 0]]]]}
    feature: dict[str, object] = {
        "properties": {
            "code_qp": "QN04901M",
            "lib_qp": " Belle Beille ",
            "insee_com": "49007",
            "lib_com": "Angers",
        },
        "geometry": geometry,
    }
    assert parse_priority_district(feature) == (
        "QN04901M", "Belle Beille", "49007", "Angers", json.dumps(geometry)
    )  # fmt: skip
    assert parse_priority_district({**feature, "geometry": {"type": "Point"}}) is None
    assert parse_priority_district({**feature, "geometry": None}) is None
    assert parse_priority_district({"properties": {"lib_qp": "x"}, "geometry": geometry}) is None


def test_commune_income_rows_keep_what_is_published() -> None:
    assert parse_commune_income_row("49007", ["21450", "15020", "29570"], "21,0") == (
        "49007",
        2021,
        21450,
        15020,
        29570,
        21.0,
    )
    # Petite commune : seule la médiane échappe au secret statistique.
    assert parse_commune_income_row("01001", ["25820", "s", "s"], "s") == (
        "01001",
        2021,
        25820,
        None,
        None,
        None,
    )
    assert parse_commune_income_row("01001", ["s", "s", "s"], None) is None
    assert parse_commune_income_row("FRANCE", ["21450", "15020", "29570"], "14,5") is None
