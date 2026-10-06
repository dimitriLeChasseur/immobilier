"""Accès aux référentiels statiques (SSMSI, DGFiP, IPS, SITADEL)."""

from datetime import date
from decimal import Decimal
from typing import Any, Protocol

import asyncpg

from app.repositories.db import db_errors

# Les requêtes ci-dessous n'interpolent que des fragments SQL constants (jamais de donnée
# utilisateur) : l'alerte S608 de ruff y est donc neutralisée.
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
