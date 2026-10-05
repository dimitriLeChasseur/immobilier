"""Accès à la table immo.api_reports_cache."""

from datetime import timedelta
from typing import Any, Protocol

import asyncpg

from app.repositories.db import db_errors

# Les requêtes ci-dessous n'interpolent que des fragments SQL constants (jamais de donnée
# utilisateur) : l'alerte S608 de ruff y est donc neutralisée.
_POINT = "ST_SetSRID(ST_MakePoint($1, $2), 4326)"

_SELECT = f"""
    SELECT payload
    FROM api_reports_cache
    WHERE geohash = ST_GeoHash({_POINT}, 9)
      AND ban_id = $3
      AND report_version = $4
      AND expires_at > now()
"""  # noqa: S608

_UPSERT = f"""
    INSERT INTO api_reports_cache
        (ban_id, report_version, geom, code_insee, label, payload, is_partial, expires_at)
    VALUES ($3, $4, {_POINT}, $5, $6, $7, $8, now() + $9::interval)
    ON CONFLICT (geohash, ban_id, report_version) DO UPDATE SET
        geom = EXCLUDED.geom,
        code_insee = EXCLUDED.code_insee,
        label = EXCLUDED.label,
        payload = EXCLUDED.payload,
        is_partial = EXCLUDED.is_partial,
        created_at = now(),
        expires_at = EXCLUDED.expires_at
"""  # noqa: S608


class ReportCache(Protocol):
    async def get(
        self, lat: float, lon: float, ban_id: str, report_version: int
    ) -> dict[str, Any] | None: ...

    async def put(
        self,
        *,
        lat: float,
        lon: float,
        ban_id: str,
        report_version: int,
        citycode: str,
        label: str,
        payload: dict[str, Any],
        is_partial: bool,
        ttl: timedelta,
    ) -> None: ...


class PostgresReportCache:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get(
        self, lat: float, lon: float, ban_id: str, report_version: int
    ) -> dict[str, Any] | None:
        async with db_errors():
            payload = await self._pool.fetchval(_SELECT, lon, lat, ban_id, report_version)
        return payload if isinstance(payload, dict) else None

    async def put(
        self,
        *,
        lat: float,
        lon: float,
        ban_id: str,
        report_version: int,
        citycode: str,
        label: str,
        payload: dict[str, Any],
        is_partial: bool,
        ttl: timedelta,
    ) -> None:
        async with db_errors():
            await self._pool.execute(
                _UPSERT,
                lon,
                lat,
                ban_id,
                report_version,
                citycode,
                label[:300],
                payload,
                is_partial,
                ttl,
            )
