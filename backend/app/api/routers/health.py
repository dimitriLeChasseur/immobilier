"""Sondes de santé."""

import asyncpg
from fastapi import APIRouter, HTTPException, Request, status

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Sonde de vivacité : le processus répond."""
    return {"status": "ok"}


@router.get("/api/health/ready")
async def ready(request: Request) -> dict[str, str]:
    """Sonde de disponibilité : la base et PostGIS sont joignables."""
    pool: asyncpg.Pool = request.app.state.db_pool
    try:
        # La version n'est pas renvoyée : une sonde publique n'a pas à décrire le serveur.
        await pool.fetchval("SELECT postgis_lib_version()")
    except (asyncpg.PostgresError, OSError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database unavailable",
        ) from exc
    return {"status": "ready"}
