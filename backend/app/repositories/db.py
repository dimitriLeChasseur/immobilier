"""Pool asyncpg et traduction des erreurs de base de données."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg

from app.core.errors import RepositoryError


async def _init_connection(connection: asyncpg.Connection) -> None:
    await connection.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )


async def create_pool(dsn: str) -> asyncpg.Pool:
    return await asyncpg.create_pool(
        dsn=dsn, min_size=1, max_size=10, command_timeout=5, init=_init_connection
    )


@asynccontextmanager
async def db_errors() -> AsyncIterator[None]:
    """Convertit les erreurs asyncpg/réseau (dont TimeoutError, sous-classe d'OSError)."""
    try:
        yield
    except (asyncpg.PostgresError, asyncpg.InterfaceError, OSError) as exc:
        raise RepositoryError(type(exc).__name__) from exc
