"""Requêtes SQL exécutées sur une vraie base PostGIS.

Les autres tests simulent le dépôt : ceux-ci vérifient ce qu'ils ne voient pas, la justesse
des requêtes géographiques et des agrégats. Ils sont ignorés sans base :

    IMMO_TEST_DATABASE_URL=postgresql://immo_app:<mot de passe>@127.0.0.1:5433/postgres \\
        uv run pytest tests/test_integration_sql.py

Chaque test insère ses propres lignes, sous des codes qui n'existent pas (département « 00 »,
point au large du golfe de Guinée), et les retire en sortant.
"""

import os
from collections.abc import AsyncIterator

import asyncpg
import pytest

from app.repositories.db import create_pool
from app.repositories.reference import PostgresReferenceRepository

DSN = os.environ.get("IMMO_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(DSN is None, reason="IMMO_TEST_DATABASE_URL non défini")

SOURCE = "test-integration"
# Loin de toute donnée réelle.
LON, LAT = 0.5, 0.5

_CLEANUP = (
    ("geo_bruit_lden", "source_id = $1", SOURCE),
    ("geo_osm_poi", "source = $1", SOURCE),
    ("insee_iris_logement", "code_insee LIKE $1", "0099%"),
    ("geo_ips_ecoles", "code_insee LIKE $1", "0099%"),
    ("ref_loyers", "code_insee LIKE $1", "0099%"),
    ("ref_carte_scolaire", "code_insee LIKE $1", "0099%"),
    ("ref_zone_tendue", "code_insee LIKE $1", "0099%"),
    ("insee_iris_revenus", "code_iris LIKE $1", "0099%"),
    ("insee_population", "code_insee LIKE $1", "0099%"),
    ("geo_qpv", "code_qp LIKE $1", "QTEST%"),
)


async def _clean(pool: asyncpg.Pool) -> None:
    for table, condition, value in _CLEANUP:
        await pool.execute(f"DELETE FROM {table} WHERE {condition}", value)  # noqa: S608


@pytest.fixture
async def pool() -> AsyncIterator[asyncpg.Pool]:
    assert DSN is not None
    database = await create_pool(DSN)
    await _clean(database)
    try:
        yield database
    finally:
        await _clean(database)
        await database.close()


@pytest.fixture
def repository(pool: asyncpg.Pool) -> PostgresReferenceRepository:
    return PostgresReferenceRepository(pool)


def square(west: float, south: float, size: float = 0.001) -> str:
    east, north = west + size, south + size
    ring = f"{west} {south},{east} {south},{east} {north},{west} {north},{west} {south}"
    return f"SRID=4326;MULTIPOLYGON((({ring})))"


async def add_noise(pool: asyncpg.Pool, zone: str, kind: str, level: int, geom: str) -> None:
    await pool.execute(
        "INSERT INTO geo_bruit_lden (id_zone, source_id, code_dept, infrastructure, db_min, geom)"
        " VALUES ($1, $2, '00', $3, $4, ST_GeomFromEWKT($5))",
        f"TEST_{zone}",
        SOURCE,
        kind,
        level,
        geom,
    )


async def test_noise_along_a_street_counts_each_exposed_number_once(
    pool: asyncpg.Pool, repository: PostgresReferenceRepository
) -> None:
    # Deux zones routières qui se recouvrent sur le premier numéro, une zone ferroviaire plus loin.
    await add_noise(pool, "route55", "route", 55, square(LON, LAT))
    await add_noise(pool, "route65", "route", 65, square(LON, LAT))
    await add_noise(pool, "fer60", "fer", 60, square(LON + 0.002, LAT))
    inside_road = (LON + 0.0005, LAT + 0.0005)
    inside_rail = (LON + 0.0025, LAT + 0.0005)
    outside = (LON + 0.01, LAT + 0.01)

    levels = await repository.noise_levels_along([inside_road, inside_rail, outside, outside])

    assert [(level["infrastructure"], level["db_min"]) for level in levels] == [
        ("route", 65),
        ("fer", 60),
    ]
    # Deux numéros exposés sur quatre, même si l'un est couvert par deux zones.
    assert {level["nb_exposes"] for level in levels} == {2}
    assert await repository.noise_levels_along([outside]) == []

    assert await repository.noise_levels(inside_road[1], inside_road[0]) == [
        {"infrastructure": "route", "db_min": 65}
    ]


async def test_noise_coverage_is_reported_by_kind_of_infrastructure(
    pool: asyncpg.Pool, repository: PostgresReferenceRepository
) -> None:
    assert await repository.noise_coverage(LAT, LON) == []
    await add_noise(pool, "fer60", "fer", 60, square(LON, LAT))
    # Une carte ferroviaire à proximité ne vaut pas couverture routière.
    assert await repository.noise_coverage(LAT + 0.02, LON) == ["fer"]
    assert await repository.noise_coverage(LAT + 5, LON) == []


async def add_iris(pool: asyncpg.Pool, code: str, dwellings: int, tenants: int) -> None:
    await pool.execute(
        "INSERT INTO insee_iris_logement (code_iris, annee, code_insee, logements,"
        " residences_principales, residences_secondaires, logements_vacants, proprietaires,"
        " locataires, locataires_hlm) VALUES ($1, 2022, $2, $3, $3, 0, 0, 0, $4, 0)",
        code,
        code[:5],
        dwellings,
        tenants,
    )


async def test_commune_housing_sums_its_iris_and_follows_arrondissement_prefixes(
    pool: asyncpg.Pool, repository: PostgresReferenceRepository
) -> None:
    await add_iris(pool, "009910101", 100, 40)
    await add_iris(pool, "009910102", 300, 60)
    await add_iris(pool, "009920101", 600, 600)

    commune = await repository.commune_housing("00991")
    assert commune is not None
    assert (commune["logements"], commune["locataires"], commune["annee"]) == (400, 100, 2022)
    # Paris, Lyon, Marseille : le préfixe réunit les arrondissements.
    city = await repository.commune_housing("0099")
    assert city is not None
    assert city["logements"] == 1000
    assert await repository.commune_housing("00999") is None


async def add_school(pool: asyncpg.Pool, uai: str, code: str, kind: str, score: float) -> None:
    await pool.execute(
        "INSERT INTO geo_ips_ecoles (uai, rentree_scolaire, nom, type_etablissement, secteur,"
        " code_insee, ips, geom) VALUES ($1,"
        # Sur une base vierge (CI), aucune rentrée n'existe encore : on en fixe une.
        " (SELECT coalesce(max(rentree_scolaire), 2025) FROM geo_ips_ecoles),"
        " 'Test', $2, 'public', $3, $4, ST_SetSRID(ST_MakePoint($5, $6), 4326))",
        uai,
        kind,
        code,
        score,
        LON,
        LAT,
    )


async def test_commune_schools_average_by_level_across_arrondissements(
    pool: asyncpg.Pool, repository: PostgresReferenceRepository
) -> None:
    await add_school(pool, "0099001A", "00991", "ecole", 100)
    await add_school(pool, "0099002B", "00992", "ecole", 120)
    await add_school(pool, "0099003C", "00992", "lycee", 130)

    one = await repository.commune_schools("00991")
    assert [(row["type_etablissement"], row["nb"], row["ips_moyen"]) for row in one] == [
        ("ecole", 1, 100.0)
    ]
    both = await repository.commune_schools("0099")
    assert [(row["type_etablissement"], row["nb"], row["ips_moyen"]) for row in both] == [
        ("ecole", 2, 110.0),
        ("lycee", 1, 130.0),
    ]

    nearby = await repository.schools_nearby(LAT, LON, 500, 10)
    assert {row["uai"] for row in nearby} == {"0099001A", "0099002B", "0099003C"}
    assert all((round(row["lon"], 3), round(row["lat"], 3)) == (LON, LAT) for row in nearby)


async def test_points_of_interest_measure_the_distance_to_the_outline_of_a_park(
    pool: asyncpg.Pool, repository: PostgresReferenceRepository
) -> None:
    # Un parc dont le bord est à ~110 m du point et le centre à plus de 500 m.
    await pool.execute(
        "INSERT INTO geo_osm_poi (osm_type, osm_id, categorie, type, nom, source, geom)"
        " VALUES ('w', -1, 'espaces_verts', 'park', 'Parc test', $1,"
        " ST_GeomFromEWKT($2))",
        SOURCE,
        f"SRID=4326;MULTIPOINT(({LON + 0.001} {LAT}),({LON + 0.012} {LAT}),"
        f"({LON + 0.012} {LAT + 0.01}))",
    )
    rows = await repository.pois_nearby(LAT, LON, 500, 10)
    assert rows is not None
    assert [row["nom"] for row in rows] == ["Parc test"]
    assert 100 < rows[0]["distance_m"] < 120
    # La position renvoyée est le point du contour le plus proche, pas le centre.
    assert round(rows[0]["lon"], 3) == LON + 0.001

    # Secteur ingéré mais sans équipement à portée : liste vide, et non « non couvert ».
    assert await repository.pois_nearby(LAT + 0.05, LON, 500, 10) == []
    assert await repository.pois_nearby(LAT + 5, LON, 500, 10) is None


async def test_commune_rents_weight_arrondissements_by_their_observations(
    pool: asyncpg.Pool, repository: PostgresReferenceRepository
) -> None:
    rows = [
        ("00991", "appartement", 30.0, 25.0, 36.0, 300, "commune"),
        ("00992", "appartement", 20.0, 16.0, 24.0, 100, "maille"),
        # Sans annonce observée, la zone compte pour une : elle ne disparaît pas de la moyenne.
        ("00993", "maison", 12.0, 9.0, 15.0, 0, "commune"),
    ]
    await pool.executemany(
        "INSERT INTO ref_loyers (code_insee, type_bien, loyer_m2, borne_basse, borne_haute,"
        " nb_observations, niveau_prediction, millesime) VALUES ($1, $2, $3, $4, $5, $6,"
        " $7, 2025)",
        rows,
    )

    city = await repository.commune_rents("0099")
    assert city["appartement"]["loyer_m2"] == pytest.approx(27.5)
    assert (city["appartement"]["loyer_min"], city["appartement"]["loyer_max"]) == (20.0, 30.0)
    assert (city["appartement"]["borne_basse"], city["appartement"]["borne_haute"]) == (16.0, 36.0)
    assert city["appartement"]["nb_zones"] == 2
    assert city["appartement"]["niveau_prediction"] == "maille", "le niveau le moins précis"
    assert city["maison"]["niveau_prediction"] == "commune"
    assert city["maison"]["loyer_m2"] == pytest.approx(12.0)

    single = await repository.commune_rents("00992")
    assert set(single) == {"appartement"}
    assert single["appartement"]["nb_zones"] == 1
    assert await repository.commune_rents("00999") == {}


async def test_school_sector_reads_the_street_or_the_whole_commune_and_names_the_colleges(
    pool: asyncpg.Pool, repository: PostgresReferenceRepository
) -> None:
    await pool.executemany(
        "INSERT INTO ref_carte_scolaire (code_insee, voie, numero_debut, numero_fin, parite, uai,"
        " secteur_unique) VALUES ($1, $2, $3, $4, $5, $6, $7)",
        [
            ("00991", "RUE DU TEST", 1, 59, "I", "0099001A", False),
            ("00991", "RUE DU TEST", 2, 60, "P", "0099002B", False),
            ("00991", "RUE AUTRE", 1, 9999, "PI", "0099003C", False),
            ("00992", "", None, None, None, "0099004D", True),
        ],
    )
    await add_school(pool, "0099001A", "00991", "college", 112.0)

    rows, colleges = await repository.school_sector("00991", "RUE DU TEST")
    assert {row["uai"] for row in rows} == {"0099001A", "0099002B"}
    assert colleges == 3, "collèges de toute la commune, pas de la seule voie"
    # Voie absente de la carte : la commune y figure quand même.
    assert await repository.school_sector("00991", "RUE INCONNUE") == ([], 3)
    assert await repository.school_sector("00999", "RUE DU TEST") == ([], 0)
    whole, _ = await repository.school_sector("00992", "N IMPORTE")
    assert [(row["uai"], row["secteur_unique"]) for row in whole] == [("0099004D", True)]

    # Seul le collège connu du référentiel des établissements est décrit.
    named = await repository.colleges(["0099001A", "0099002B"], LAT, LON)
    assert [(college["uai"], college["nom"], college["distance_m"]) for college in named] == [
        ("0099001A", "Test", 0.0)
    ]


async def test_tense_zone_is_found_under_any_of_the_commune_codes(
    pool: asyncpg.Pool, repository: PostgresReferenceRepository
) -> None:
    await pool.execute(
        "INSERT INTO ref_zone_tendue (code_insee, categorie, reference)"
        " VALUES ('00990', 'touristique', 'test')"
    )
    # Un arrondissement n'a pas de ligne : c'est celle de sa commune qui répond.
    assert await repository.tense_zone(["00991", "00990"]) == {
        "categorie": "touristique",
        "reference": "test",
    }
    assert await repository.tense_zone(["00998"]) is None


async def test_priority_district_is_the_one_containing_the_point_else_the_nearest(
    pool: asyncpg.Pool, repository: PostgresReferenceRepository
) -> None:
    for code, name, west in (("QTEST1", "Près", LON), ("QTEST2", "Loin", LON + 0.003)):
        await pool.execute(
            "INSERT INTO geo_qpv (code_qp, nom, code_insee, commune, geom)"
            " VALUES ($1, $2, '00990', 'Testville', ST_GeomFromEWKT($3))",
            code,
            name,
            square(west, LAT),
        )
    assert await repository.priority_districts_loaded()

    inside = await repository.priority_district(LAT + 0.0005, LON + 0.0005, 500)
    assert inside == {"code_qp": "QTEST1", "nom": "Près", "commune": "Testville", "distance_m": 0}

    # Environ 110 m à l'ouest du premier périmètre, plus de 400 m du second.
    near = await repository.priority_district(LAT + 0.0005, LON - 0.001, 500)
    assert near is not None and near["code_qp"] == "QTEST1"
    assert 100 <= near["distance_m"] <= 120

    assert await repository.priority_district(LAT + 0.0005, LON - 0.001, 50) is None
    assert await repository.priority_district(LAT + 0.5, LON + 0.5, 500) is None


async def test_income_and_population_lookups(
    pool: asyncpg.Pool, repository: PostgresReferenceRepository
) -> None:
    await pool.execute(
        "INSERT INTO insee_iris_revenus"
        " (code_iris, annee, revenu_median, revenu_q1, revenu_q3, taux_pauvrete_pct)"
        " VALUES ('009900101', 2021, 23950, 16980, 34630, NULL)"
    )
    assert await repository.iris_income("009900101") == {
        "annee": 2021,
        "revenu_median": 23950,
        "revenu_q1": 16980,
        "revenu_q3": 34630,
        "taux_pauvrete_pct": None,
    }
    assert await repository.iris_income("009909999") is None

    await pool.execute(
        "INSERT INTO insee_population (code_insee, annee, population, population_6, population_11)"
        " VALUES ('00990', 2022, 1000, 900, NULL), ('00991', 2022, 100, 110, 120)"
    )
    # Le code le plus précis l'emporte : l'arrondissement avant sa commune.
    arrondissement = await repository.population(["00991", "00990"])
    assert arrondissement is not None
    assert (arrondissement["code_insee"], arrondissement["population"]) == ("00991", 100)
    commune = await repository.population(["00998", "00990"])
    assert commune is not None
    assert (commune["population"], commune["population_11"]) == (1000, None)
    assert await repository.population(["00998"]) is None
