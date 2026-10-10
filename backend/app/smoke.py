"""Test de fumée : interroge les vraies sources sur des adresses de référence.

    docker compose exec -T backend python -m app.smoke

Les tests unitaires simulent toutes les API ; celui-ci détecte ce qu'ils ne voient pas :
une source arrêtée, déplacée, ou dont la réponse a changé de forme. Le cache est contourné.
Une anomalie n'est signalée que si elle persiste au second essai, quelques minutes plus tard :
un délai dépassé isolé chez un fournisseur ne réveille personne.
Code de retour : 0 si tout répond comme attendu, 1 sinon.
"""

import asyncio
import logging
import sys
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import aiohttp

from app.container import build_audit_service
from app.core.config import get_settings
from app.repositories.db import create_pool
from app.schemas.audit import AuditQuery, AuditReport, SourceResult
from app.services.audit_service import AuditService

logger = logging.getLogger("smoke")

# Délai avant de rejouer un cas en anomalie : assez long pour laisser passer un incident bref.
RETRY_DELAY_S = 180

# Champs qu'une source en bonne santé renvoie pour l'adresse de référence. Leur absence
# signale un changement de format côté fournisseur.
EXPECTED_KEYS: dict[str, tuple[str, ...]] = {
    "georisques": (
        "risques",
        "inondation",
        "argiles",
        "sismicite",
        "radon",
        "seveso",
        "plans_prevention",
        "anciens_sites_industriels",
        "cavites",
    ),
    "cadastre": ("identifiant", "section"),
    "urbanisme": ("zones", "servitudes", "prescriptions"),
    "dvf": ("nb_ventes", "prix_m2_median", "dernieres_ventes"),
    "dpe": ("nb_dpe_analyses", "repartition_dpe"),
    "batiment": ("annee_construction", "nb_logements", "dpe", "monument_historique"),
    "proximite": ("categories",),
    "qualite_air": ("indice", "qualificatif"),
    "ensoleillement": ("score", "masque_relief_deg"),
    "loyers": ("loyer_m2_charges_comprises", "par_typologie"),
    "delinquance": ("indicateurs",),
    "taxe_fonciere": ("taux_tfb_total",),
    "ecoles": ("etablissements", "superieur"),
    "permis_construire": ("nb_permis",),
    "marche_locatif": ("occupation", "encadrement_loyers", "zonage_abc"),
    "quartier": ("revenus", "quartier_prioritaire", "population"),
    "connectivite": ("part_fibre_pct",),
    "copropriete": ("charges_m2_an",),
    "reseau_mobile": ("nb_sites", "operateurs"),
    "bruit": ("niveau_max_db", "infrastructures_couvertes"),
}


@dataclass(frozen=True, slots=True)
class Case:
    label: str
    query: AuditQuery
    # Sources pour lesquelles « aucune donnée » est la réponse normale à cet endroit.
    may_be_empty: frozenset[str] = frozenset()
    # Champs supplémentaires attendus (ex. mode « rue »).
    extra_keys: dict[str, tuple[str, ...]] = field(default_factory=dict)


CASES = (
    Case(
        "adresse : 8 Rue du Canal, Angers",
        AuditQuery(lat=47.47408, lon=-0.55107, ban_id="49007_1350_00008"),
    ),
    Case(
        "rue : Rue Saint-Aubin, Angers",
        AuditQuery(lat=47.469077, lon=-0.5529, ban_id="49007_7050"),
        may_be_empty=frozenset({"cadastre", "batiment"}),
        extra_keys={"dvf": ("comparaison",), "dpe": ("par_numero",)},
    ),
)


class NoCache:
    """Cache neutralisé : chaque exécution interroge réellement les sources."""

    async def get(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def put(self, **kwargs: Any) -> None:
        return None


def check_source(name: str, result: SourceResult | None, case: Case) -> str | None:
    """Anomalie constatée sur une source, None si elle répond comme attendu."""
    if result is None:
        return "source absente du rapport"
    if result.status == "empty":
        return None if name in case.may_be_empty else "aucune donnée pour l'adresse de référence"
    if result.status not in ("ok", "partial"):
        return f"{result.status} ({result.error})"
    data = result.data or {}
    expected = EXPECTED_KEYS.get(name, ()) + case.extra_keys.get(name, ())
    missing = [key for key in expected if key not in data]
    # Une réponse partielle explique des champs absents : seul un « ok » incomplet est un écart.
    if missing and result.status == "ok":
        return f"champs absents : {', '.join(missing)}"
    if result.status == "partial":
        return f"réponse partielle, sans : {', '.join(result.missing)}"
    return None


def check_report(report: AuditReport, case: Case, source_names: list[str]) -> list[str]:
    problems = []
    for name in source_names:
        problem = check_source(name, report.sources.get(name), case)
        if problem is not None:
            problems.append(f"{name} : {problem}")
    if case.extra_keys and report.location.rue is None:
        problems.append("localisation : la voie n'a pas été reconnue (mode rue inactif)")
    return problems


def persistent(first: list[str], second: list[str]) -> list[str]:
    """Anomalies du second essai déjà vues au premier, sur la même source."""
    seen = {problem.split(" : ", 1)[0] for problem in first}
    return [problem for problem in second if problem.split(" : ", 1)[0] in seen]


async def _check_case(service: AuditService, case: Case, attempt: str) -> list[str]:
    report = await service.get_report(case.query)
    problems = check_report(report, case, service.source_names)
    took = timedelta(milliseconds=report.meta.duration_ms).total_seconds()
    verdict = "OK" if not problems else f"{len(problems)} anomalie(s)"
    logger.info("%s (%s) : %s en %.1f s", case.label, attempt, verdict, took)
    return problems


async def run(retry_delay_s: float = RETRY_DELAY_S) -> int:
    settings = get_settings()
    pool = await create_pool(settings.database_url.get_secret_value())
    session = aiohttp.ClientSession(headers={"User-Agent": settings.http_user_agent})
    failures = 0
    try:
        service = build_audit_service(settings, pool, session, cache=NoCache())
        for case in CASES:
            problems = await _check_case(service, case, "premier essai")
            if problems:
                for problem in problems:
                    logger.warning("  à confirmer : %s", problem)
                await asyncio.sleep(retry_delay_s)
                problems = persistent(problems, await _check_case(service, case, "second essai"))
            failures += len(problems)
            for problem in problems:
                logger.error("  %s", problem)
    finally:
        await session.close()
        await pool.close()
    return 1 if failures else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # Les journaux détaillés des sources noieraient le verdict.
    logging.getLogger("app").setLevel(logging.ERROR)
    sys.exit(asyncio.run(run()))
