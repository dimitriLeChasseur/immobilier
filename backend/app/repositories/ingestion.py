"""Écriture des référentiels statiques (upserts idempotents)."""

from collections.abc import Sequence
from datetime import date
from typing import Any

import asyncpg

from app.repositories.db import db_errors

Row = tuple[Any, ...]

# Les requêtes ci-dessous n'interpolent que des fragments SQL constants (jamais de donnée
# utilisateur) : l'alerte S608 de ruff y est donc neutralisée.
_POINT = "ST_SetSRID(ST_MakePoint(${lon}, ${lat}), 4326)"

_UPSERT_CRIME = """
    INSERT INTO insee_ssmsi
        (code_insee, indicateur, annee, unite_de_compte, est_diffuse, nombre,
         taux_pour_mille, population)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
    ON CONFLICT (code_insee, indicateur, annee) DO UPDATE SET
        unite_de_compte = EXCLUDED.unite_de_compte,
        est_diffuse = EXCLUDED.est_diffuse,
        nombre = EXCLUDED.nombre,
        taux_pour_mille = EXCLUDED.taux_pour_mille,
        population = EXCLUDED.population,
        imported_at = now()
"""

_UPSERT_PROPERTY_TAX = """
    INSERT INTO insee_dgfip
        (code_insee, annee, libelle_commune, taux_tfb_commune, taux_tfb_epci,
         taux_tfb_total, taux_teom)
    VALUES ($1, $2, $3, $4, $5, $6, $7)
    ON CONFLICT (code_insee, annee) DO UPDATE SET
        libelle_commune = EXCLUDED.libelle_commune,
        taux_tfb_commune = EXCLUDED.taux_tfb_commune,
        taux_tfb_epci = EXCLUDED.taux_tfb_epci,
        taux_tfb_total = EXCLUDED.taux_tfb_total,
        taux_teom = EXCLUDED.taux_teom,
        imported_at = now()
"""

_UPSERT_SCHOOL = f"""
    INSERT INTO geo_ips_ecoles
        (uai, rentree_scolaire, nom, type_etablissement, secteur, code_insee, ips,
         ecart_type_ips, geom)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, {_POINT.format(lon=9, lat=10)})
    ON CONFLICT (uai, rentree_scolaire) DO UPDATE SET
        nom = EXCLUDED.nom,
        type_etablissement = EXCLUDED.type_etablissement,
        secteur = EXCLUDED.secteur,
        code_insee = EXCLUDED.code_insee,
        ips = EXCLUDED.ips,
        ecart_type_ips = EXCLUDED.ecart_type_ips,
        geom = EXCLUDED.geom,
        imported_at = now()
"""  # noqa: S608

_UPSERT_PERMIT = f"""
    INSERT INTO geo_sitadel
        (num_permis, type_autorisation, etat, date_autorisation, date_ouverture_chantier,
         date_achevement, code_insee, adresse, nature_projet, destination, nb_logements,
         nb_niveaux, surface_plancher_m2, precision_geocodage, geom)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14,
            {_POINT.format(lon=15, lat=16)})
    ON CONFLICT (num_permis) DO UPDATE SET
        type_autorisation = EXCLUDED.type_autorisation,
        etat = EXCLUDED.etat,
        date_autorisation = EXCLUDED.date_autorisation,
        date_ouverture_chantier = EXCLUDED.date_ouverture_chantier,
        date_achevement = EXCLUDED.date_achevement,
        code_insee = EXCLUDED.code_insee,
        adresse = EXCLUDED.adresse,
        nature_projet = EXCLUDED.nature_projet,
        destination = EXCLUDED.destination,
        nb_logements = EXCLUDED.nb_logements,
        nb_niveaux = EXCLUDED.nb_niveaux,
        surface_plancher_m2 = EXCLUDED.surface_plancher_m2,
        precision_geocodage = EXCLUDED.precision_geocodage,
        geom = EXCLUDED.geom,
        imported_at = now()
"""  # noqa: S608


_UPSERT_IRIS_HOUSING = """
    INSERT INTO insee_iris_logement
        (code_iris, annee, code_insee, logements, residences_principales,
         residences_secondaires, logements_vacants, proprietaires, locataires, locataires_hlm)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
    ON CONFLICT (code_iris) DO UPDATE SET
        annee = EXCLUDED.annee,
        code_insee = EXCLUDED.code_insee,
        logements = EXCLUDED.logements,
        residences_principales = EXCLUDED.residences_principales,
        residences_secondaires = EXCLUDED.residences_secondaires,
        logements_vacants = EXCLUDED.logements_vacants,
        proprietaires = EXCLUDED.proprietaires,
        locataires = EXCLUDED.locataires,
        locataires_hlm = EXCLUDED.locataires_hlm,
        imported_at = now()
"""

_UPSERT_CONNECTIVITY = """
    INSERT INTO arcep_connectivite
        (code_insee, date_donnees, nb_locaux, eligibles_fibre, eligibles_cable, eligibles_4g_fixe)
    VALUES ($1, $2, $3, $4, $5, $6)
    ON CONFLICT (code_insee) DO UPDATE SET
        date_donnees = EXCLUDED.date_donnees,
        nb_locaux = EXCLUDED.nb_locaux,
        eligibles_fibre = EXCLUDED.eligibles_fibre,
        eligibles_cable = EXCLUDED.eligibles_cable,
        eligibles_4g_fixe = EXCLUDED.eligibles_4g_fixe,
        imported_at = now()
"""


class IngestionRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def _executemany(self, statement: str, rows: Sequence[Row]) -> None:
        if not rows:
            return
        async with db_errors(), self._pool.acquire() as connection:
            await connection.executemany(statement, rows, timeout=300)

    async def upsert_crime(self, rows: Sequence[Row]) -> None:
        await self._executemany(_UPSERT_CRIME, rows)

    async def upsert_property_tax(self, rows: Sequence[Row]) -> None:
        await self._executemany(_UPSERT_PROPERTY_TAX, rows)

    async def upsert_schools(self, rows: Sequence[Row]) -> None:
        await self._executemany(_UPSERT_SCHOOL, rows)

    async def upsert_permits(self, rows: Sequence[Row]) -> None:
        await self._executemany(_UPSERT_PERMIT, rows)

    async def upsert_iris_housing(self, rows: Sequence[Row]) -> None:
        await self._executemany(_UPSERT_IRIS_HOUSING, rows)

    async def upsert_connectivity(self, rows: Sequence[Row]) -> None:
        await self._executemany(_UPSERT_CONNECTIVITY, rows)

    async def purge_permits_before(self, cutoff: date) -> None:
        async with db_errors():
            await self._pool.execute(
                "DELETE FROM geo_sitadel WHERE date_autorisation < $1", cutoff, timeout=300
            )

    async def clear_report_cache(self) -> None:
        """Les rapports en cache ont été calculés avec les anciens référentiels."""
        async with db_errors():
            await self._pool.execute("DELETE FROM api_reports_cache")
