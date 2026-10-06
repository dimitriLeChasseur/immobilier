"""Accès aux référentiels statiques (SSMSI, DGFiP, IPS, SITADEL)."""

import time
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any, Protocol

import asyncpg

from app.repositories.db import db_errors

# Les requêtes ci-dessous n'interpolent que des fragments SQL constants (jamais de donnée
# utilisateur) : l'alerte S608 de ruff y est donc neutralisée.
_BENCHMARK_TTL_S = 24 * 3600
_POINT_GEOM = "ST_SetSRID(ST_MakePoint($1, $2), 4326)"
_POINT_GEOG = f"{_POINT_GEOM}::geography"

# Pour chaque requête par commune : le code le plus précis (arrondissement) est préféré.
_CRIME = """
    SELECT indicateur, annee, unite_de_compte, est_diffuse, nombre, taux_pour_mille, population
    FROM insee_ssmsi
    WHERE code_insee = $1
      AND annee = (SELECT max(annee) FROM insee_ssmsi WHERE code_insee = $1)
    ORDER BY indicateur
"""

# Taux pour 1 000 habitants à l'échelle d'un territoire, sur les seules communes dont la
# donnée est diffusée (les autres, trop petites, n'ont ni nombre ni population exploitable).
# $2 : préfixe de département, ou chaîne vide pour la France entière.
_CRIME_BENCHMARK = """
    SELECT indicateur,
           1000.0 * sum(nombre) / nullif(sum(population), 0) AS taux_pour_mille
    FROM insee_ssmsi
    WHERE annee = $1 AND est_diffuse AND left(code_insee, length($2)) = $2
    GROUP BY indicateur
"""

_CRIME_YEAR = """
    SELECT indicateur, taux_pour_mille
    FROM insee_ssmsi
    WHERE code_insee = $1 AND annee = $2 AND est_diffuse
"""

_PROPERTY_TAX_BENCHMARK = """
    SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY taux_tfb_total) AS mediane
    FROM insee_dgfip
    WHERE annee = $1 AND left(code_insee, length($2)) = $2
"""

_IPS_BENCHMARK = """
    SELECT type_etablissement, avg(ips) AS ips_moyen
    FROM geo_ips_ecoles
    WHERE rentree_scolaire >= (SELECT max(rentree_scolaire) FROM geo_ips_ecoles) - 1
      AND left(code_insee, length($1)) = $1
    GROUP BY type_etablissement
"""

_COMMUNE_SCHOOLS = """
    SELECT type_etablissement, count(*) AS nb, avg(ips) AS ips_moyen
    FROM (
        SELECT DISTINCT ON (uai) uai, type_etablissement, ips
        FROM geo_ips_ecoles
        WHERE code_insee = $1
          AND rentree_scolaire >= (SELECT max(rentree_scolaire) FROM geo_ips_ecoles) - 1
        ORDER BY uai, rentree_scolaire DESC
    ) AS etablissements
    WHERE ips IS NOT NULL
    GROUP BY type_etablissement
    ORDER BY type_etablissement
"""

# Les quartiers IRIS d'une commune portent son code en préfixe.
_COMMUNE_HOUSING = """
    SELECT max(annee) AS annee, sum(logements) AS logements,
           sum(residences_principales) AS residences_principales,
           sum(logements_vacants) AS logements_vacants,
           sum(proprietaires) AS proprietaires, sum(locataires) AS locataires
    FROM insee_iris_logement
    WHERE left(code_iris, 5) = $1
"""

_PROPERTY_TAX = """
    SELECT annee, libelle_commune, taux_tfb_commune, taux_tfb_epci, taux_tfb_total, taux_teom
    FROM insee_dgfip
    WHERE code_insee = $1
    ORDER BY annee DESC
    LIMIT 1
"""

_SCHOOLS = f"""
    SELECT * FROM (
        -- Dernière rentrée connue de chaque établissement : écoles et collèges/lycées
        -- ne sont pas publiés la même année.
        SELECT DISTINCT ON (uai)
               uai, nom, type_etablissement, secteur, ips, ecart_type_ips, rentree_scolaire,
               round(ST_Distance(geom::geography, {_POINT_GEOG})) AS distance_m
        FROM geo_ips_ecoles
        WHERE ST_DWithin(geom::geography, {_POINT_GEOG}, $3)
          -- Écarte les établissements disparus des publications récentes (fermés).
          AND rentree_scolaire >= (SELECT max(rentree_scolaire) FROM geo_ips_ecoles) - 1
        ORDER BY uai, rentree_scolaire DESC
    ) AS etablissements
    ORDER BY distance_m
    LIMIT $4
"""  # noqa: S608

_PERMITS = f"""
    SELECT num_permis, type_autorisation, etat, date_autorisation, nature_projet, destination,
           nb_logements, nb_niveaux, surface_plancher_m2, adresse, precision_geocodage,
           round(ST_Distance(geom::geography, {_POINT_GEOG})) AS distance_m
    FROM geo_sitadel
    WHERE ST_DWithin(geom::geography, {_POINT_GEOG}, $3)
      AND date_autorisation >= current_date - $4::int
      AND etat IN ('autorise', 'commence')
    ORDER BY distance_m
    LIMIT $5
"""  # noqa: S608


_IRIS_HOUSING = """
    SELECT annee, logements, residences_principales, residences_secondaires, logements_vacants,
           proprietaires, locataires, locataires_hlm
    FROM insee_iris_logement
    WHERE code_iris = $1
"""

_CONNECTIVITY = """
    SELECT date_donnees, nb_locaux, eligibles_fibre, eligibles_cable, eligibles_4g_fixe
    FROM arcep_connectivite
    WHERE code_insee = $1
"""


_NOISE_LEVELS = f"""
    SELECT infrastructure, max(db_min) AS db_min
    FROM geo_bruit_lden
    WHERE ST_Intersects(geom, {_POINT_GEOM})
    GROUP BY infrastructure
    ORDER BY db_min DESC
"""  # noqa: S608

# $1, $2 : longitudes et latitudes des numéros d'une voie.
_NOISE_ALONG = """
    WITH numbers AS (
        SELECT row_number() OVER () AS id, ST_SetSRID(ST_MakePoint(lon, lat), 4326) AS geom
        FROM unnest($1::float8[], $2::float8[]) AS t(lon, lat)
    ),
    hits AS (
        SELECT n.id, z.infrastructure, max(z.db_min) AS db_min
        FROM numbers n JOIN geo_bruit_lden z ON ST_Intersects(z.geom, n.geom)
        GROUP BY n.id, z.infrastructure
    )
    SELECT infrastructure, max(db_min) AS db_min, count(*) AS nb_points,
           (SELECT count(DISTINCT id) FROM hits) AS nb_exposes
    FROM hits
    GROUP BY infrastructure
    ORDER BY db_min DESC
"""

# Une carte routière ne dit rien du bruit ferroviaire : la couverture se mesure par type.
_NOISE_COVERAGE = f"""
    SELECT DISTINCT infrastructure
    FROM geo_bruit_lden
    WHERE ST_DWithin(geom, {_POINT_GEOM}, $3)
    ORDER BY infrastructure
"""  # noqa: S608


_POIS = f"""
    SELECT categorie, type, nom,
           ST_X(ST_ClosestPoint(geom, {_POINT_GEOM})) AS lon,
           ST_Y(ST_ClosestPoint(geom, {_POINT_GEOM})) AS lat,
           ST_Distance(geom::geography, {_POINT_GEOG}) AS distance_m
    FROM geo_osm_poi
    WHERE ST_DWithin(geom::geography, {_POINT_GEOG}, $3)
    ORDER BY distance_m
    LIMIT $4
"""  # noqa: S608

_POI_COVERAGE = f"""
    SELECT EXISTS (
        SELECT 1 FROM geo_osm_poi WHERE ST_DWithin(geom::geography, {_POINT_GEOG}, $3)
    )
"""  # noqa: S608

# Un territoire est considéré comme ingéré si un point d'intérêt existe à moins de 20 km.
_POI_COVERAGE_M = 20_000

# Un type d'infrastructure est considéré comme cartographié si une de ses zones existe à ~10 km.
_NOISE_COVERAGE_DEG = 0.1


class ReferenceRepository(Protocol):
    async def crime_indicators(self, codes: list[str]) -> list[dict[str, Any]]: ...

    async def property_tax(self, codes: list[str]) -> dict[str, Any] | None: ...

    async def crime_benchmarks(self, year: int, departement: str) -> dict[str, dict[str, float]]:
        """Taux pour 1 000 hab. par indicateur : {indicateur: {departement, national}}."""
        ...

    async def crime_rates(self, codes: list[str], year: int) -> dict[str, float]: ...

    async def property_tax_benchmarks(self, year: int, departement: str) -> dict[str, float]: ...

    async def ips_benchmarks(self, departement: str) -> dict[str, dict[str, float]]: ...

    async def schools_nearby(
        self, lat: float, lon: float, radius_m: int, limit: int
    ) -> list[dict[str, Any]]: ...

    async def permits_nearby(
        self, lat: float, lon: float, radius_m: int, max_age_days: int, limit: int
    ) -> list[dict[str, Any]]: ...

    async def iris_housing(self, code_iris: str) -> dict[str, Any] | None: ...

    async def connectivity(self, codes: list[str]) -> dict[str, Any] | None: ...

    async def noise_levels(self, lat: float, lon: float) -> list[dict[str, Any]]: ...

    async def noise_coverage(self, lat: float, lon: float) -> list[str]: ...

    async def noise_levels_along(
        self, points: Sequence[tuple[float, float]]
    ) -> list[dict[str, Any]]: ...

    async def pois_nearby(
        self, lat: float, lon: float, radius_m: int, limit: int
    ) -> list[dict[str, Any]] | None: ...


def _jsonable(record: asyncpg.Record) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for key, value in record.items():
        if isinstance(value, Decimal):
            row[key] = float(value)
        elif isinstance(value, date):
            row[key] = value.isoformat()
        else:
            row[key] = value
    return row


class PostgresReferenceRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool
        self._benchmarks: dict[tuple[Any, ...], tuple[float, list[asyncpg.Record]]] = {}

    async def crime_indicators(self, codes: list[str]) -> list[dict[str, Any]]:
        for code in codes:
            async with db_errors():
                records = await self._pool.fetch(_CRIME, code)
            if records:
                return [_jsonable(record) for record in records]
        return []

    async def property_tax(self, codes: list[str]) -> dict[str, Any] | None:
        for code in codes:
            async with db_errors():
                record = await self._pool.fetchrow(_PROPERTY_TAX, code)
            if record is not None:
                return _jsonable(record)
        return None

    async def _memo(self, key: tuple[Any, ...], query: str, *args: Any) -> list[asyncpg.Record]:
        """Agrégat de territoire, gardé en mémoire : il ne change qu'à une réingestion."""
        cached = self._benchmarks.get(key)
        if cached is not None and time.monotonic() - cached[0] < _BENCHMARK_TTL_S:
            return cached[1]
        async with db_errors():
            records: list[asyncpg.Record] = await self._pool.fetch(query, *args)
        self._benchmarks[key] = (time.monotonic(), records)
        return records

    async def crime_benchmarks(self, year: int, departement: str) -> dict[str, dict[str, float]]:
        benchmarks: dict[str, dict[str, float]] = {}
        for scope, prefix in (("departement", departement), ("national", "")):
            for record in await self._memo(("crime", year, prefix), _CRIME_BENCHMARK, year, prefix):
                if record["taux_pour_mille"] is not None:
                    rate = round(float(record["taux_pour_mille"]), 2)
                    benchmarks.setdefault(record["indicateur"], {})[scope] = rate
        return benchmarks

    async def crime_rates(self, codes: list[str], year: int) -> dict[str, float]:
        for code in codes:
            async with db_errors():
                records = await self._pool.fetch(_CRIME_YEAR, code, year)
            if records:
                return {
                    record["indicateur"]: float(record["taux_pour_mille"])
                    for record in records
                    if record["taux_pour_mille"] is not None
                }
        return {}

    async def property_tax_benchmarks(self, year: int, departement: str) -> dict[str, float]:
        medians: dict[str, float] = {}
        for scope, prefix in (("departement", departement), ("national", "")):
            records = await self._memo(("tax", year, prefix), _PROPERTY_TAX_BENCHMARK, year, prefix)
            if records and records[0]["mediane"] is not None:
                medians[scope] = round(float(records[0]["mediane"]), 2)
        return medians

    async def ips_benchmarks(self, departement: str) -> dict[str, dict[str, float]]:
        benchmarks: dict[str, dict[str, float]] = {}
        for scope, prefix in (("departement", departement), ("national", "")):
            for record in await self._memo(("ips", prefix), _IPS_BENCHMARK, prefix):
                average = round(float(record["ips_moyen"]), 1)
                benchmarks.setdefault(record["type_etablissement"], {})[scope] = average
        return benchmarks

    async def schools_nearby(
        self, lat: float, lon: float, radius_m: int, limit: int
    ) -> list[dict[str, Any]]:
        async with db_errors():
            records = await self._pool.fetch(_SCHOOLS, lon, lat, radius_m, limit)
        return [_jsonable(record) for record in records]

    async def permits_nearby(
        self, lat: float, lon: float, radius_m: int, max_age_days: int, limit: int
    ) -> list[dict[str, Any]]:
        async with db_errors():
            records = await self._pool.fetch(_PERMITS, lon, lat, radius_m, max_age_days, limit)
        return [_jsonable(record) for record in records]

    async def iris_housing(self, code_iris: str) -> dict[str, Any] | None:
        async with db_errors():
            record = await self._pool.fetchrow(_IRIS_HOUSING, code_iris)
        return _jsonable(record) if record is not None else None

    async def connectivity(self, codes: list[str]) -> dict[str, Any] | None:
        # Les statistiques ARCEP sont publiées à la commune : pour Paris, Lyon et Marseille,
        # le code d'arrondissement ne donne rien et c'est la commune qui répond.
        for code in codes:
            async with db_errors():
                record = await self._pool.fetchrow(_CONNECTIVITY, code)
            if record is not None:
                return _jsonable(record)
        return None

    async def noise_levels(self, lat: float, lon: float) -> list[dict[str, Any]]:
        """Classes de bruit au point, la plus forte d'abord."""
        async with db_errors():
            records = await self._pool.fetch(_NOISE_LEVELS, lon, lat)
        return [_jsonable(record) for record in records]

    async def noise_coverage(self, lat: float, lon: float) -> list[str]:
        """Types d'infrastructure cartographiés autour du point ; vide si rien n'est ingéré."""
        async with db_errors():
            records = await self._pool.fetch(_NOISE_COVERAGE, lon, lat, _NOISE_COVERAGE_DEG)
        return [str(record["infrastructure"]) for record in records]

    async def noise_levels_along(
        self, points: Sequence[tuple[float, float]]
    ) -> list[dict[str, Any]]:
        """Classes de bruit rencontrées sur des points (lon, lat), la plus forte d'abord.

        Chaque ligne porte `nb_exposes`, le nombre de points situés dans une zone de bruit.
        """
        lons, lats = [p[0] for p in points], [p[1] for p in points]
        async with db_errors():
            records = await self._pool.fetch(_NOISE_ALONG, lons, lats)
        return [_jsonable(record) for record in records]

    async def pois_nearby(
        self, lat: float, lon: float, radius_m: int, limit: int
    ) -> list[dict[str, Any]] | None:
        """Points d'intérêt par distance croissante ; None si le secteur n'est pas ingéré."""
        async with db_errors():
            records = await self._pool.fetch(_POIS, lon, lat, radius_m, limit)
            if records:
                return [_jsonable(record) for record in records]
            covered = await self._pool.fetchval(_POI_COVERAGE, lon, lat, _POI_COVERAGE_M)
        return [] if covered else None

    async def commune_schools(self, code: str) -> list[dict[str, Any]]:
        """Nombre d'établissements et IPS moyen par niveau dans la commune."""
        async with db_errors():
            records = await self._pool.fetch(_COMMUNE_SCHOOLS, code)
        return [_jsonable(record) for record in records]

    async def commune_housing(self, code: str) -> dict[str, Any] | None:
        """Occupation des logements de la commune (somme de ses quartiers IRIS)."""
        async with db_errors():
            record = await self._pool.fetchrow(_COMMUNE_HOUSING, code)
        return _jsonable(record) if record is not None and record["annee"] is not None else None
