"""Droits d'accès aux audits complets (table immo.audit_entitlements)."""

from typing import Protocol

import asyncpg

from app.repositories.db import db_errors

# Même clé spatiale que le cache des rapports : un droit vaut pour une adresse précise.
_GEOHASH = "ST_GeoHash(ST_SetSRID(ST_MakePoint($2, $3), 4326), 9)"

# Un droit vaut pour le point acheté, ou pour la même adresse BAN ($4, résolue par le serveur).
# Un abonnement en cours ouvre toutes les adresses ; quelques jours de tolérance couvrent
# le délai entre l'échéance et la confirmation du renouvellement par Stripe.
_HAS_ACCESS = f"""
    SELECT EXISTS (
        SELECT 1 FROM audit_entitlements
        WHERE user_id = $1::uuid AND (geohash = {_GEOHASH} OR ban_id = $4::text)
    ) OR EXISTS (
        SELECT 1 FROM user_subscriptions
        WHERE user_id = $1::uuid
          AND status IN ('active', 'trialing')
          AND (current_period_end IS NULL OR current_period_end > now() - interval '3 days')
    )
"""  # noqa: S608


# Usage d'un abonné : nombre d'AUTRES adresses consultées sur 24 heures glissantes. NULL quand
# l'adresse demandée a été achetée ou déjà consultée dans la période : elle ne compte pas.
_SUBSCRIPTION_USAGE = f"""
    SELECT CASE
        WHEN EXISTS (
            SELECT 1 FROM audit_entitlements
            WHERE user_id = $1::uuid AND (geohash = {_GEOHASH} OR ban_id = $4::text)
        ) OR EXISTS (
            SELECT 1 FROM audit_history
            WHERE user_id = $1::uuid AND geohash = {_GEOHASH}
              AND viewed_at > now() - interval '24 hours'
        ) THEN NULL
        ELSE (
            SELECT count(*) FROM audit_history
            WHERE user_id = $1::uuid AND viewed_at > now() - interval '24 hours'
        )
    END
"""  # noqa: S608

_RECORD_VIEW = f"""
    INSERT INTO audit_history (user_id, geohash, label, ban_id)
    VALUES ($1::uuid, {_GEOHASH}, $4, $5)
    ON CONFLICT (user_id, geohash) DO UPDATE SET
        label = EXCLUDED.label, ban_id = EXCLUDED.ban_id, viewed_at = now()
"""  # noqa: S608


class EntitlementRepository(Protocol):
    async def has_access(
        self, user_id: str, lat: float, lon: float, address_id: str | None = None
    ) -> bool: ...

    async def record_view(
        self, user_id: str, lat: float, lon: float, label: str, address_id: str | None
    ) -> None: ...

    async def subscription_usage(
        self, user_id: str, lat: float, lon: float, address_id: str | None = None
    ) -> int | None: ...


class PostgresEntitlementRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def has_access(
        self, user_id: str, lat: float, lon: float, address_id: str | None = None
    ) -> bool:
        async with db_errors():
            return bool(await self._pool.fetchval(_HAS_ACCESS, user_id, lon, lat, address_id))

    async def record_view(
        self, user_id: str, lat: float, lon: float, label: str, address_id: str | None
    ) -> None:
        """Note la consultation d'un rapport complet dans l'historique de l'utilisateur."""
        async with db_errors():
            await self._pool.execute(_RECORD_VIEW, user_id, lon, lat, label[:300], address_id)

    async def subscription_usage(
        self, user_id: str, lat: float, lon: float, address_id: str | None = None
    ) -> int | None:
        """Autres adresses vues en 24 h ; None si celle-ci est achetée ou déjà comptée."""
        async with db_errors():
            value: int | None = await self._pool.fetchval(
                _SUBSCRIPTION_USAGE, user_id, lon, lat, address_id
            )
        return value
