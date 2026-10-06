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


class EntitlementRepository(Protocol):
    async def has_access(
        self, user_id: str, lat: float, lon: float, address_id: str | None = None
    ) -> bool: ...


class PostgresEntitlementRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def has_access(
        self, user_id: str, lat: float, lon: float, address_id: str | None = None
    ) -> bool:
        async with db_errors():
            return bool(await self._pool.fetchval(_HAS_ACCESS, user_id, lon, lat, address_id))
