"""Chargement des référentiels statiques.

    python -m app.ingestion all
    python -m app.ingestion sitadel ips --departements 49,75

Idempotent : chaque exécution met à jour les lignes existantes.
"""

import argparse
import asyncio
import logging
import sys
import time
from collections.abc import Awaitable, Callable

import aiohttp

from app.core.config import get_settings
from app.core.errors import RepositoryError
from app.ingestion.common import Downloader, IngestionOptions
from app.ingestion.datasets import (
    ingest_connectivity,
    ingest_crime,
    ingest_iris_housing,
    ingest_property_tax,
    ingest_schools,
)
from app.ingestion.sitadel import ALL_DEPARTEMENTS, ingest_permits
from app.repositories.db import create_pool
from app.repositories.ingestion import IngestionRepository

logger = logging.getLogger("app.ingestion")

Ingester = Callable[[Downloader, IngestionRepository, IngestionOptions], Awaitable[int]]

DATASETS: dict[str, Ingester] = {
    "ssmsi": ingest_crime,
    "dgfip": ingest_property_tax,
    "ips": ingest_schools,
    "iris": ingest_iris_housing,
    "arcep": ingest_connectivity,
    "sitadel": ingest_permits,
}
_DOWNLOAD_TIMEOUT_S = 900


def parse_departements(value: str) -> frozenset[str]:
    codes = frozenset(code.strip().upper() for code in value.split(",") if code.strip())
    unknown = sorted(codes - set(ALL_DEPARTEMENTS))
    if unknown or not codes:
        raise argparse.ArgumentTypeError(f"départements inconnus : {', '.join(unknown) or value}")
    return codes


def parse_arguments(argv: list[str]) -> tuple[list[str], IngestionOptions]:
    parser = argparse.ArgumentParser(prog="python -m app.ingestion", description=__doc__)
    parser.add_argument("datasets", nargs="+", choices=[*DATASETS, "all"])
    parser.add_argument(
        "--departements",
        type=parse_departements,
        default=None,
        help="codes séparés par des virgules (ex. 49,75,2A) ; par défaut France entière",
    )
    parser.add_argument("--annees-delinquance", type=int, default=3, choices=range(1, 11))
    parser.add_argument("--annees-permis", type=int, default=5, choices=range(1, 14))
    arguments = parser.parse_args(argv)
    selected = list(DATASETS) if "all" in arguments.datasets else arguments.datasets
    options = IngestionOptions(
        departements=arguments.departements,
        crime_years=arguments.annees_delinquance,
        permit_years=arguments.annees_permis,
    )
    return list(dict.fromkeys(selected)), options


async def run(selected: list[str], options: IngestionOptions) -> bool:
    settings = get_settings()
    pool = await create_pool(settings.database_url.get_secret_value())
    session = aiohttp.ClientSession(
        headers={"User-Agent": settings.http_user_agent},
        timeout=aiohttp.ClientTimeout(total=_DOWNLOAD_TIMEOUT_S),
    )
    repository = IngestionRepository(pool)
    succeeded = True
    try:
        for name in selected:
            started = time.monotonic()
            try:
                count = await DATASETS[name](Downloader(session), repository, options)
            except (aiohttp.ClientError, TimeoutError, RepositoryError, ValueError) as exc:
                logger.exception("%s : échec (%s)", name, type(exc).__name__)
                succeeded = False
                continue
            logger.info("%s : %d lignes en %.0f s", name, count, time.monotonic() - started)
        await repository.clear_report_cache()
        logger.info("Cache des rapports vidé (référentiels mis à jour)")
    finally:
        await session.close()
        await pool.close()
    return succeeded


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    selected, options = parse_arguments(sys.argv[1:])
    return 0 if asyncio.run(run(selected, options)) else 1


if __name__ == "__main__":
    sys.exit(main())
