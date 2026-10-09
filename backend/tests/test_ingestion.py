"""Ingestion : conversion des lignes sources et rapprochement du géocodage (sans réseau)."""

import argparse
from datetime import date

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from app.ingestion.__main__ import parse_arguments, parse_departements
from app.ingestion.common import (
    Downloader,
    IngestionOptions,
    batched,
    departement_of,
    read_csv,
    to_date,
    to_integer,
    to_number,
)
from app.ingestion.datasets import (
    parse_connectivity_row,
    parse_crime_row,
    parse_iris_housing_row,
    parse_property_tax_row,
    parse_rent_row,
    parse_school_row,
)
from app.ingestion.sitadel import (
    ALL_DEPARTEMENTS,
    Permit,
    geocoding_request,
    merge_geocoding,
    parse_permit_row,
)


def test_number_parsing_handles_french_format_and_missing_values() -> None:
    assert to_number("1,3620690") == pytest.approx(1.362069)
    assert to_number("12.5") == 12.5
    for missing in ("NA", "", None):
        assert to_number(missing) is None
    assert to_number("abc") is None
    assert to_integer("767") == 767
    assert to_integer("NA") is None
    assert to_date("2024-06-07") == date(2024, 6, 7)
    assert to_date("") is None
    assert to_date("07/06/2024") is None


def test_departement_filter() -> None:
    assert departement_of("49007") == "49"
    assert departement_of("2A004") == "2A"
    assert departement_of("97411") == "974"
    options = IngestionOptions(departements=frozenset({"49", "974"}))
    assert options.accepts("49007")
    assert options.accepts("97411")
    assert not options.accepts("75101")
    assert IngestionOptions().accepts("75101")


def test_csv_helpers() -> None:
    assert read_csv("﻿a;b\n1;2\n") == [{"a": "1", "b": "2"}]
    assert list(batched(range(5), 2)) == [[0, 1], [2, 3], [4]]


def test_cli_arguments() -> None:
    selected, options = parse_arguments(["all", "--departements", "49, 2a"])
    assert selected == ["ssmsi", "dgfip", "ips", "iris", "arcep", "loyers", "sitadel"]
    assert options.departements == frozenset({"49", "2A"})
    assert parse_arguments(["ips", "ips"])[0] == ["ips"]
    with pytest.raises(argparse.ArgumentTypeError):
        parse_departements("49,999")
    assert len(ALL_DEPARTEMENTS) == 101
    assert "20" not in ALL_DEPARTEMENTS


CRIME_ROW = {
    "CODGEO_2026": "49007",
    "annee": "2025",
    "indicateur": "Cambriolages de logement",
    "unite_de_compte": "Infraction",
    "nombre": "512",
    "taux_pour_mille": "3,1834567",
    "est_diffuse": "diff",
    "insee_pop": "160830",
}


def test_crime_row() -> None:
    assert parse_crime_row(CRIME_ROW, "CODGEO_2026", 2024) == (
        "49007",
        "Cambriolages de logement",
        2025,
        "Infraction",
        True,
        512,
        pytest.approx(3.1834567),
        160830,
    )
    hidden = CRIME_ROW | {"nombre": "NA", "taux_pour_mille": "NA", "est_diffuse": "ndiff"}
    parsed = parse_crime_row(hidden, "CODGEO_2026", 2024)
    assert parsed is not None
    assert parsed[4:7] == (False, None, None)
    assert parse_crime_row(CRIME_ROW, "CODGEO_2026", 2026) is None, "année trop ancienne"
    assert parse_crime_row(CRIME_ROW | {"CODGEO_2026": "ZZZZZ"}, "CODGEO_2026", 2024) is None


def test_property_tax_row() -> None:
    row = {
        "exercice": "2025",
        "insee_com": "49007",
        "libcom": "ANGERS",
        "e12vote": "54.24",
        "e32vote": "2.18",
        "taux_global_tfb": "56.65",
        "taux_plein_teom": "8.71",
    }
    assert parse_property_tax_row(row) == ("49007", 2025, "ANGERS", 54.24, 2.18, 56.65, 8.71)
    assert parse_property_tax_row(row | {"e32vote": ""}) == (
        "49007", 2025, "ANGERS", 54.24, 0.0, 56.65, 8.71
    )  # fmt: skip
    assert parse_property_tax_row(row | {"taux_global_tfb": ""}) is None


def test_school_row_needs_coordinates_and_score() -> None:
    coordinates = {"0490001A": (47.47, -0.55)}
    row = {
        "rentree_scolaire": "2025-2026",
        "code_insee_de_la_commune": "49007",
        "uai": "0490001a",
        "nom_de_l_etablissement": "LYCEE DAVID D'ANGERS",
        "secteur": "privé sous contrat",
        "ips_etab": "118.4",
        "ecart_type_etablissement": "31.2",
    }
    parsed = parse_school_row(row, "lycee", "ips_etab", "ecart_type_etablissement", coordinates)
    assert parsed == (
        "0490001A",
        2025,
        "LYCEE DAVID D'ANGERS",
        "lycee",
        "prive",
        "49007",
        118.4,
        31.2,
        -0.55,
        47.47,
    )
    assert parse_school_row(row, "lycee", "ips_etab", None, {}) is None
    assert parse_school_row(row | {"ips_etab": ""}, "lycee", "ips_etab", None, coordinates) is None


PERMIT_ROW = {
    "COMM": "49002",
    "TYPE_DAU": "PC",
    "NUM_DAU": "04900223M0028",
    "ETAT_DAU": "2",
    "DATE_REELLE_AUTORISATION": "2024-06-07",
    "DATE_REELLE_DOC": "",
    "DATE_REELLE_DAACT": "",
    "ADR_NUM_TER": "161",
    "ADR_LIBVOIE_TER": "RUE ALBERT POTTIER",
    "ADR_LIEUDIT_TER": "",
    "ADR_LOCALITE_TER": "ALLONNES",
    "ADR_CODPOST_TER": "49650",
    "NATURE_PROJET_DECLAREE": "1",
    "NB_NIV_MAX": "3",
    "NB_LGT_TOT_CREES": "21",
    "SURF_HAB_CREEE": "1450",
    "SURF_LOC_CREEE": "187",
}


def test_permit_row() -> None:
    permit = parse_permit_row(PERMIT_ROW, "logement")
    assert permit is not None
    assert permit.values == (
        "04900223M0028",
        "PC",
        "autorise",
        date(2024, 6, 7),
        None,
        None,
        "49002",
        "161 RUE ALBERT POTTIER, ALLONNES",
        "construction neuve",
        "logement",
        21,
        3,
        1637.0,
    )
    assert (permit.street_address, permit.postcode) == ("161 RUE ALBERT POTTIER", "49650")


@pytest.mark.parametrize(
    "overrides",
    [
        {"DATE_REELLE_AUTORISATION": ""},
        {"ETAT_DAU": "9"},
        {"ADR_NUM_TER": "", "ADR_LIBVOIE_TER": ""},
        {"TYPE_DAU": "XX"},
        {"COMM": ""},
    ],
)
def test_unusable_permit_rows_are_skipped(overrides: dict[str, str]) -> None:
    assert parse_permit_row(PERMIT_ROW | overrides, "logement") is None


def test_geocoding_roundtrip_keeps_only_precise_matches() -> None:
    permits = [
        Permit(values=(f"P{i}",), street_address=f"{i} RUE X", postcode="49000", citycode="49007")
        for i in range(5)
    ]
    assert geocoding_request(permits).splitlines()[:2] == [
        "idx,adresse,postcode,citycode",
        "0,0 RUE X,49000,49007",
    ]
    response = (
        "idx,adresse,postcode,citycode,latitude,longitude,result_score,result_type\n"
        "0,0 RUE X,49000,49007,47.47,-0.55,0.96,housenumber\n"
        "1,1 RUE X,49000,49007,47.48,-0.56,0.71,street\n"
        "2,2 RUE X,49000,49007,47.49,-0.57,0.31,housenumber\n"  # score trop faible
        "3,3 RUE X,49000,49007,47.50,-0.58,0.90,municipality\n"  # trop imprécis
        "4,4 RUE X,49000,49007,,,,\n"  # non trouvé
        "99,?,49000,49007,47.47,-0.55,0.99,housenumber\n"  # index inconnu
    )
    assert merge_geocoding(permits, response) == [
        ("P0", "numero", -0.55, 47.47),
        ("P1", "voie", -0.56, 47.48),
    ]


def test_permit_row_discards_implausible_levels() -> None:
    for raw in ("-1", "239"):
        permit = parse_permit_row(PERMIT_ROW | {"NB_NIV_MAX": raw}, "logement")
        assert permit is not None
        assert permit.values[11] is None


async def test_downloader_retries_transient_failures_then_succeeds() -> None:
    calls = {"count": 0}

    async def flaky(_: web.Request) -> web.Response:
        calls["count"] += 1
        if calls["count"] < 3:
            return web.Response(status=503)
        return web.Response(text="ok")

    async def missing(_: web.Request) -> web.Response:
        calls["count"] += 1
        return web.Response(status=404)

    app = web.Application()
    app.add_routes([web.get("/flaky", flaky), web.get("/missing", missing)])
    server = TestServer(app)
    await server.start_server()
    try:
        async with aiohttp.ClientSession() as session:
            downloader = Downloader(session, attempts=4, retry_delay_s=0.001)
            assert await downloader.text(str(server.make_url("/flaky"))) == "ok"
            assert calls["count"] == 3

            calls["count"] = 0
            missing_url = str(server.make_url("/missing"))
            with pytest.raises(aiohttp.ClientResponseError):
                await downloader.text(missing_url)
            assert calls["count"] == 1, "une erreur 404 n'est pas réessayée"
    finally:
        await server.close()


def test_iris_housing_row() -> None:
    row = {
        "IRIS": "490070107",
        "COM": "49007",
        "P22_LOG": "2100.4",
        "P22_RP": "1800",
        "P22_RSECOCC": "120",
        "P22_LOGVAC": "180.4",
        "P22_RP_PROP": "500",
        "P22_RP_LOC": "1250",
        "P22_RP_LOCHLMV": "90",
    }
    assert parse_iris_housing_row(row) == (
        "490070107", 2022, "49007", 2100, 1800, 120, 180, 500, 1250, 90
    )  # fmt: skip
    assert parse_iris_housing_row(row | {"P22_RP_LOC": ""}) is None
    assert parse_iris_housing_row(row | {"IRIS": "49007"}) is None


def test_connectivity_row_keeps_only_the_all_premises_line() -> None:
    row = {
        "code_insee": "49007",
        "nbr": "109137",
        "type": "all",
        "elig_ftth": "106184",
        "elig_coax": "83761",
        "elig_4gf": "109037",
        "date": "2026-06-30",
    }
    assert parse_connectivity_row(row) == (
        "49007", date(2026, 6, 30), 109137, 106184, 83761, 109037
    )  # fmt: skip
    assert parse_connectivity_row(row | {"type": "res"}) is None
    assert parse_connectivity_row(row | {"nbr": "0"}) is None


def test_rent_row_reads_decimal_commas_and_skips_unusable_lines() -> None:
    row = {
        "INSEE_C": "75101",
        "loypredm2": "34,5212",
        "lwr.IPm2": "27,1",
        "upr.IPm2": "43,958",
        "TYPPRED": "commune",
        "nbobs_com": "1520",
    }
    assert parse_rent_row(row, "appartement", 2025) == (
        "75101", "appartement", 34.5212, 27.1, 43.958, 1520, "commune", 2025,
    )  # fmt: skip
    assert parse_rent_row({**row, "loypredm2": ""}, "maison", 2025) is None
    assert parse_rent_row({**row, "INSEE_C": "7510"}, "maison", 2026) is None
