"""Collège de secteur et zone tendue : lecture des fichiers et résolution pour une adresse."""

from typing import Any

import pytest

from app.ingestion.datasets import parse_school_sector_row, parse_tense_zone_row
from app.services.providers.base import AuditContext
from app.services.providers.reference import SchoolsProvider
from app.services.school_sectors import resolve_sector


def stretch(uai: str, first: int | None, last: int | None, parity: str | None) -> dict[str, Any]:
    return {
        "uai": uai,
        "secteur_unique": False,
        "numero_debut": first,
        "numero_fin": last,
        "parite": parity,
    }


STREET = [
    stretch("0490001A", 1, 59, "I"),
    stretch("0490002B", 2, 60, "P"),
    stretch("0490002B", 61, 9999, "PI"),
]


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        (17, ("adresse", ["0490001A"])),
        (18, ("adresse", ["0490002B"])),
        (61, ("adresse", ["0490002B"])),
        # Numéro inconnu (audit d'une voie) : tous les collèges de la voie.
        (None, ("voie", ["0490001A", "0490002B"])),
    ],
)
def test_sector_follows_number_ranges_and_parity(
    number: int | None, expected: tuple[str, list[str]]
) -> None:
    assert resolve_sector(STREET, 14, number) == expected


def test_sector_falls_back_honestly() -> None:
    # Numéro hors des tronçons décrits : la voie reste connue, pas le collège exact.
    assert resolve_sector([stretch("0490001A", 1, 9, None)], 14, 40) == ("voie", ["0490001A"])
    whole = [
        {"uai": "0050010C", "secteur_unique": True},
        {"uai": "0050011D", "secteur_unique": True},
    ]
    assert resolve_sector(whole, 2, 12) == ("commune", ["0050010C", "0050011D"])
    assert resolve_sector([], 14, 12) == ("indetermine", [])
    assert resolve_sector([], 0, 12) == ("non_couvert", [])


class Repository:
    def __init__(self) -> None:
        self.queries: list[tuple[str, str]] = []

    async def schools_nearby(self, *args: Any) -> list[dict[str, Any]]:
        return [{"uai": "0490900Z", "type_etablissement": "ecole", "ips": 101.0}]

    async def ips_benchmarks(self, departement: str) -> dict[str, dict[str, float]]:
        return {}

    async def school_sector(self, code: str, street: str) -> tuple[list[dict[str, Any]], int]:
        self.queries.append((code, street))
        return STREET, 14

    async def colleges(self, uais: list[str], lat: float, lon: float) -> list[dict[str, Any]]:
        return [{"uai": "0490001A", "nom": "Collège Chevreul", "ips": 118.2, "distance_m": 640}]


async def test_schools_source_names_the_sector_college_of_the_address() -> None:
    repository = Repository()
    ctx = AuditContext(
        lat=47.47, lon=-0.55, citycode="49007", street_name="Rue Saint-Aubin", house_number=17
    )
    data = (await SchoolsProvider(repository).fetch(ctx)).data  # type: ignore[arg-type]
    # Le nom de voie est comparé sous sa forme normalisée, celle de la carte scolaire.
    assert repository.queries == [("49007", "RUE SAINT AUBIN")]
    assert data["college_secteur"] == {
        "statut": "adresse",
        "colleges": [
            {"uai": "0490001A", "nom": "Collège Chevreul", "ips": 118.2, "distance_m": 640}
        ],
        "nb_colleges_commune": 14,
    }

    # Sans numéro, les deux collèges de la voie ; celui que le référentiel des
    # établissements ne connaît pas garde son identifiant.
    street_only = AuditContext(lat=47.47, lon=-0.55, citycode="49007", street_name="Rue X")
    sector = (await SchoolsProvider(repository).fetch(street_only)).data["college_secteur"]  # type: ignore[arg-type]
    assert sector["statut"] == "voie"
    assert [college["uai"] for college in sector["colleges"]] == ["0490001A", "0490002B"]


def test_school_map_rows() -> None:
    row = {
        "code_insee": "49007",
        "type_et_libelle": "RUE DE L ILE DE FRANCE",
        "n_de_voie_debut": "10.0",
        "n_de_voie_fin": "58.0",
        "parite": "P",
        "code_rne": "0490953V",
        "secteur_unique": "N",
    }
    assert parse_school_sector_row(row) == (
        "49007", "RUE DE L ILE DE FRANCE", 10, 58, "P", "0490953V", False,
    )  # fmt: skip
    whole = {"code_insee": "05046", "code_rne": "0050010C", "secteur_unique": "O"}
    assert parse_school_sector_row(whole) == ("05046", "", None, None, None, "0050010C", True)
    # Secteur décrit par un lieu-dit seul, ou ligne sans collège : inexploitable.
    assert parse_school_sector_row({**row, "type_et_libelle": ""}) is None
    assert parse_school_sector_row({**row, "code_rne": ""}) is None


def test_tense_zone_rows_read_the_latest_list() -> None:
    row = {
        "CODGEO25": "05046",
        "LIBGEO": "Embrun",
        "Zonage TLV 2013": "Non TLV",
        "Zonage TLV 2023": "3. Non tendue",
        "Zonage TLV post décret 22/12/2025": "2. Zone touristique et tendue",
    }
    assert parse_tense_zone_row(row) == ("05046", "touristique", "post décret 22/12/2025")
    last = "Zonage TLV post décret 22/12/2025"
    assert parse_tense_zone_row({**row, last: "1. Zone tendue"}) == (
        "05046", "tendue", "post décret 22/12/2025",
    )  # fmt: skip
    assert parse_tense_zone_row({**row, last: ""}) is None
    assert parse_tense_zone_row({"CODGEO25": "05046"}) is None
