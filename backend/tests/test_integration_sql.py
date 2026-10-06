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
        " code_insee, ips, geom) VALUES ($1, (SELECT max(rentree_scolaire) FROM geo_ips_ecoles),"
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
