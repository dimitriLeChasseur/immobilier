"""Enseignement supérieur à proximité, joint au bloc des établissements scolaires."""

from typing import Any

import pytest

from app.core.errors import NoDataError, SourceError
from app.schemas.audit import SourceResult
from app.services.providers.base import AuditContext
from app.services.providers.higher_education import HigherEducationFinder
from app.services.providers.reference import SchoolsProvider
from app.services.synthesis import build_synthesis

CTX = AuditContext(lat=47.47408, lon=-0.55107, citycode="49007")
MAIN = {
    "results": [
        {
            "uo_lib": "Université d'Angers",
            "sigle": "UA",
            "type_d_etablissement": ["Université"],
            "secteur_d_etablissement": "public",
            "coordonnees": {"lon": -0.549657, "lat": 47.47687},
            "uai": "0490970N",
        },
        {
            "uo_lib": "École supérieure d'électronique de l'Ouest",
            "sigle": "ESEO",
            "type_d_etablissement": ["École"],
            "secteur_d_etablissement": "privé",
            "coordonnees": {"lon": -0.550804, "lat": 47.493396},
            "uai": "0490075R",
        },
        {"uo_lib": "Sans position", "uai": "0000000X"},
    ]
}
SITES = {
    "results": [
        # Siège déjà connu par le premier jeu : même code UAI.
        {
            "implantation_lib": "UNIVERSITÉ D'ANGERS",
            "type_d_etablissement": "Université",
            "coordonnees": {"lon": -0.549936, "lat": 47.477092},
            "uai": "0490970N",
            "effectif": 1258,
        },
        # Composante logée dans le bâtiment du siège : elle ne fait pas une ligne de plus.
        {
            "implantation_lib": "DIRECTION DE LA FORMATION CONTINUE, UNIVERSITÉ D'ANGERS",
            "type_d_etablissement": "Université",
            "coordonnees": {"lon": -0.54966, "lat": 47.47688},
            "uai": "0492300D",
        },
        {
            "implantation_lib": "BIBLIOTHÈQUE UNIVERSITAIRE SAINT-SERGE",
            "type_d_etablissement": "Université",
            "coordonnees": {"lon": -0.5470, "lat": 47.4790},
            "uai": "0492400E",
        },
        {
            "implantation_lib": "UNITÉ DE FORMATION ET DE RECHERCHE SANTÉ, UNIVERSITÉ D'ANGERS",
            "type_d_etablissement": "Université",
            "coordonnees": {"lon": -0.550971, "lat": 47.488092},
            "uai": "0492225C",
            "effectif": 2820,
        },
    ]
}


class FakeHttp:
    def __init__(self, main: Any, sites: Any) -> None:
        self._main, self._sites = main, sites
        self.params: list[dict[str, Any]] = []

    async def get_json(self, source: str, url: str, *, params: Any = None) -> Any:
        self.params.append(dict(params or {}))
        outcome = self._main if "principaux" in url else self._sites
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


async def test_both_datasets_are_merged_without_duplicates_nearest_first() -> None:
    http = FakeHttp(MAIN, SITES)
    found, incomplete = await HigherEducationFinder(http).nearby(CTX)  # type: ignore[arg-type]

    assert not incomplete
    assert (
        "within_distance(coordonnees, geom'POINT(-0.55107 47.47408)', 3000m)"
        in (http.params[0]["where"])
    )
    assert [school["nom"] for school in found["etablissements"]] == [
        "Université d'Angers",
        "Unité de formation et de recherche santé, université d'angers",
        "École supérieure d'électronique de l'Ouest",
    ]
    nearest = found["etablissements"][0]
    assert (nearest["sigle"], nearest["secteur"], nearest["type"]) == ("UA", "public", "Université")
    assert 300 < nearest["distance_m"] < 350
    assert found["etablissements"][1]["effectif"] == 2820
    assert found["nb"] == 3
    assert "uai" not in nearest


async def test_one_dataset_down_gives_a_partial_list_and_both_down_an_error() -> None:
    half = FakeHttp(MAIN, SourceError("timeout"))
    found, incomplete = await HigherEducationFinder(half).nearby(CTX)  # type: ignore[arg-type]
    assert incomplete
    assert found["nb"] == 2

    down = FakeHttp(SourceError("timeout"), SourceError("timeout"))
    with pytest.raises(SourceError):
        await HigherEducationFinder(down).nearby(CTX)  # type: ignore[arg-type]


class Repository:
    def __init__(self, schools: list[dict[str, Any]]) -> None:
        self._schools = schools

    async def schools_nearby(self, *args: Any) -> list[dict[str, Any]]:
        return self._schools

    async def school_sector(self, code: str, street: str) -> tuple[list[dict[str, Any]], int]:
        return [], 0

    async def colleges(self, uais: list[str], lat: float, lon: float) -> list[dict[str, Any]]:
        return []

    async def ips_benchmarks(self, departement: str) -> dict[str, dict[str, float]]:
        return {}


SCHOOL = {"uai": "0490001A", "type_etablissement": "ecole", "ips": 120.0}


async def test_schools_block_carries_higher_education_and_survives_its_outage() -> None:
    finder = HigherEducationFinder(FakeHttp(MAIN, SITES))  # type: ignore[arg-type]
    result = await SchoolsProvider(Repository([SCHOOL]), finder).fetch(CTX)  # type: ignore[arg-type]
    assert result.missing == ()
    assert result.data["superieur"]["nb"] == 3
    assert result.data["etablissements"] == [SCHOOL]

    down = HigherEducationFinder(FakeHttp(SourceError("timeout"), SourceError("timeout")))  # type: ignore[arg-type]
    degraded = await SchoolsProvider(Repository([SCHOOL]), down).fetch(CTX)  # type: ignore[arg-type]
    assert degraded.missing == ("superieur",)
    assert "superieur" not in degraded.data
    assert degraded.data["ips_moyen"] == 120.0


async def test_a_campus_alone_is_an_answer_and_nothing_at_all_is_no_data() -> None:
    finder = HigherEducationFinder(FakeHttp(MAIN, SITES))  # type: ignore[arg-type]
    campus_only = await SchoolsProvider(Repository([]), finder).fetch(CTX)  # type: ignore[arg-type]
    assert campus_only.data["etablissements"] == []
    assert campus_only.data["superieur"]["nb"] == 3

    empty = HigherEducationFinder(FakeHttp({"results": []}, {"results": []}))  # type: ignore[arg-type]
    with pytest.raises(NoDataError):
        await SchoolsProvider(Repository([]), empty).fetch(CTX)  # type: ignore[arg-type]

    # Rien en base et le service muet : on ne peut pas affirmer qu'il n'y a rien.
    down = HigherEducationFinder(FakeHttp(SourceError("timeout"), SourceError("timeout")))  # type: ignore[arg-type]
    with pytest.raises(SourceError):
        await SchoolsProvider(Repository([]), down).fetch(CTX)  # type: ignore[arg-type]


def test_a_campus_within_walking_distance_is_a_rental_strength() -> None:
    def campus(distance: int) -> SourceResult:
        school = {"nom": "Université d'Angers", "sigle": "UA", "distance_m": distance}
        return SourceResult(status="ok", data={"superieur": {"etablissements": [school]}})

    near = build_synthesis({"ecoles": campus(320)}).points_forts
    assert [(item.theme, item.titre) for item in near] == [
        ("Marché locatif", "Enseignement supérieur à 320 m")
    ]
    assert "UA est à distance de marche" in near[0].detail
    assert build_synthesis({"ecoles": campus(1500)}).points_forts == []
