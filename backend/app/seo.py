"""Export des fiches communales pour le référencement.

    docker compose exec -T backend python -m app.seo --limit 1000 > frontend/seo/communes.json

Le fichier produit est lu à la construction du frontend, qui en tire une page statique
par commune et le plan du site. Les communes sont prises par population décroissante.
"""

import argparse
import asyncio
import csv
import io
import json
import logging
import sys

import aiohttp

from app.container import rent_resources
from app.core.config import get_settings
from app.core.http import HttpClient
from app.repositories.db import create_pool
from app.repositories.reference import PostgresReferenceRepository
from app.services.communes import CommuneService, StaticRents

logger = logging.getLogger("seo")
_DIRECTORY_TIMEOUT_S = 60.0
_DATASET_URL = "https://www.data.gouv.fr/api/1/datasets/r"


def parse_rents(content: bytes) -> dict[str, float]:
    """Loyer au m² par code de commune, d'après un fichier de la carte des loyers.

    Fichier séparé par des points-virgules, décimales à la virgule.
    """
    reader = csv.DictReader(io.StringIO(content.decode("utf-8", errors="replace")), delimiter=";")
    rents: dict[str, float] = {}
    for row in reader:
        code, value = row.get("INSEE_C"), (row.get("loypredm2") or "").replace(",", ".")
        try:
            rents[str(code)] = round(float(value), 1)
        except ValueError:
            continue
    return rents


async def download_rents(
    session: aiohttp.ClientSession, resources: dict[str, str]
) -> dict[str, dict[str, float]]:
    by_commune: dict[str, dict[str, float]] = {}
    timeout = aiohttp.ClientTimeout(total=_DIRECTORY_TIMEOUT_S)
    for kind, resource in resources.items():
        try:
            async with session.get(f"{_DATASET_URL}/{resource}", timeout=timeout) as response:
                response.raise_for_status()
                content = await response.read()
        except (aiohttp.ClientError, TimeoutError):
            logger.warning("Loyers « %s » indisponibles : fiches exportées sans cette valeur", kind)
            continue
        for code, rent in parse_rents(content).items():
            by_commune.setdefault(code, {})[kind] = rent
    return by_commune


async def export(limit: int) -> list[dict[str, object]]:
    settings = get_settings()
    pool = await create_pool(settings.database_url.get_secret_value())
    session = aiohttp.ClientSession(headers={"User-Agent": settings.http_user_agent})
    try:
        http = HttpClient(
            session,
            timeout_s=_DIRECTORY_TIMEOUT_S,
            failure_threshold=settings.breaker_failure_threshold,
            reset_after_s=settings.breaker_reset_after_s,
        )
        # Quatre fichiers lus une fois, plutôt que quatre appels par commune.
        rents = StaticRents(await download_rents(session, rent_resources(settings)))
        service = CommuneService(http, PostgresReferenceRepository(pool), rents)
        communes = (await service.directory())[:limit]
        profiles = []
        for commune in communes:
            profiles.append((await service.profile(commune)).model_dump(mode="json"))
        return profiles
    finally:
        await session.close()
        await pool.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--limit", type=int, default=1000, help="nombre de communes exportées")
    arguments = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    profiles = asyncio.run(export(arguments.limit))
    json.dump(profiles, sys.stdout, ensure_ascii=False, separators=(",", ":"))
    logger.info("%d fiches communales exportées", len(profiles))
    return 0


if __name__ == "__main__":
    sys.exit(main())
