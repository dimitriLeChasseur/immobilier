"""Export des fiches communales pour le référencement.

    docker compose exec -T backend python -m app.seo --limit 1000 > frontend/seo/communes.json

Le fichier produit est lu à la construction du frontend, qui en tire une page statique
par commune et le plan du site. Les communes sont prises par population décroissante.
"""

import argparse
import asyncio
import json
import logging
import sys

import aiohttp

from app.core.config import get_settings
from app.core.http import HttpClient
from app.repositories.db import create_pool
from app.repositories.reference import PostgresReferenceRepository
from app.services.communes import CommuneService

logger = logging.getLogger("seo")
_DIRECTORY_TIMEOUT_S = 60.0


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
        service = CommuneService(http, PostgresReferenceRepository(pool))
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
