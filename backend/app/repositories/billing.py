"""Écritures liées au paiement : droits, crédits, abonnements, évènements Stripe traités."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

import asyncpg

from app.repositories.db import db_errors

_GEOHASH = "ST_GeoHash(ST_SetSRID(ST_MakePoint($2, $3), 4326), 9)"

_RECORD_EVENT = """
    INSERT INTO stripe_events (event_id, type) VALUES ($1, $2)
    ON CONFLICT (event_id) DO NOTHING
    RETURNING event_id
"""

_GRANT = f"""
    INSERT INTO audit_entitlements (user_id, geohash, origin, label, ban_id)
    VALUES ($1::uuid, {_GEOHASH}, $4, $5, $6)
    ON CONFLICT (user_id, geohash) DO UPDATE SET
        ban_id = COALESCE(audit_entitlements.ban_id, EXCLUDED.ban_id)
    RETURNING geohash
"""  # noqa: S608

_ADD_CREDITS = """
    INSERT INTO user_credits (user_id, credits) VALUES ($1::uuid, $2)
    ON CONFLICT (user_id) DO UPDATE SET
        credits = user_credits.credits + EXCLUDED.credits,
        updated_at = now()
"""

_SPEND_CREDIT = """
    UPDATE user_credits SET credits = credits - 1, updated_at = now()
    WHERE user_id = $1::uuid AND credits > 0
    RETURNING credits
"""

# $7 (activation) : l'abonnement qui vient d'être payé remplace le précédent. Sinon, seul
# l'abonnement enregistré est mis à jour, et jamais par un évènement plus ancien que le dernier.
_UPSERT_SUBSCRIPTION = """
    INSERT INTO user_subscriptions AS current
        (user_id, stripe_customer_id, stripe_subscription_id, status, current_period_end,
         last_event_at)
    VALUES ($1::uuid, $2, $3, $4, $5, $6)
    ON CONFLICT (user_id) DO UPDATE SET
        stripe_customer_id = COALESCE(EXCLUDED.stripe_customer_id, current.stripe_customer_id),
        stripe_subscription_id = EXCLUDED.stripe_subscription_id,
        status = EXCLUDED.status,
        current_period_end = COALESCE(EXCLUDED.current_period_end, current.current_period_end),
        last_event_at = EXCLUDED.last_event_at,
        updated_at = now()
    WHERE ($7 OR current.stripe_subscription_id = EXCLUDED.stripe_subscription_id)
      AND current.last_event_at <= EXCLUDED.last_event_at
"""

_CUSTOMER = "SELECT stripe_customer_id FROM user_subscriptions WHERE user_id = $1::uuid"

_ACCOUNT = """
    SELECT
        COALESCE((SELECT credits FROM user_credits WHERE user_id = $1::uuid), 0) AS credits,
        EXISTS (
            SELECT 1 FROM user_subscriptions
            WHERE user_id = $1::uuid
              AND status IN ('active', 'trialing')
              AND (current_period_end IS NULL OR current_period_end > now() - interval '3 days')
        ) AS subscription_active
"""

# Le point restitué est le centre de la cellule achetée (précision ~2 m) : il retombe dans la
# même cellule, donc sur le même droit et le même rapport en cache.
_AUDITS = """
    SELECT label, ban_id, origin, granted_at,
           ST_X(ST_PointFromGeoHash(geohash, 4326)) AS lon,
           ST_Y(ST_PointFromGeoHash(geohash, 4326)) AS lat
    FROM audit_entitlements
    WHERE user_id = $1::uuid
    ORDER BY granted_at DESC
    LIMIT $2
"""

_BRANDING = """
    SELECT company, logo, logo_type, color, phone, email, website, address
    FROM user_branding WHERE user_id = $1::uuid
"""

_SET_BRANDING = """
    INSERT INTO user_branding
        (user_id, company, logo, logo_type, color, phone, email, website, address)
    VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9)
    ON CONFLICT (user_id) DO UPDATE SET
        company = EXCLUDED.company, logo = EXCLUDED.logo, logo_type = EXCLUDED.logo_type,
        color = EXCLUDED.color, phone = EXCLUDED.phone, email = EXCLUDED.email,
        website = EXCLUDED.website, address = EXCLUDED.address,
        updated_at = now()
"""

_DELETE_BRANDING = "DELETE FROM user_branding WHERE user_id = $1::uuid"

_IS_ENTITLED = f"""
    SELECT EXISTS (
        SELECT 1 FROM audit_entitlements
        WHERE user_id = $1::uuid AND (geohash = {_GEOHASH} OR ban_id = $4::text)
    )
"""  # noqa: S608


@dataclass(frozen=True, slots=True)
class BrandingDetails:
    """Personnalisation facultative : couleur du bandeau et coordonnées du professionnel."""

    color: str | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    address: str | None = None


class BillingRepository(Protocol):
    async def fulfil_purchase(
        self,
        *,
        event_id: str,
        event_type: str,
        user_id: str,
        lat: float | None,
        lon: float | None,
        label: str | None,
        address_id: str | None,
        origin: str,
        credits: int,
    ) -> bool: ...

    async def save_subscription(
        self,
        *,
        event_id: str,
        event_type: str,
        user_id: str,
        customer_id: str | None,
        subscription_id: str,
        status: str,
        period_end: datetime | None,
        occurred_at: datetime,
        activation: bool,
    ) -> bool: ...

    async def account(self, user_id: str) -> dict[str, Any]: ...

    async def spend_credit(
        self, user_id: str, lat: float, lon: float, label: str, address_id: str | None
    ) -> bool: ...

    async def customer_id(self, user_id: str) -> str | None: ...

    async def is_entitled(
        self, user_id: str, lat: float, lon: float, address_id: str | None
    ) -> bool: ...


class AccountRepository(Protocol):
    """Lectures et écritures de l'espace client."""

    async def account(self, user_id: str) -> dict[str, Any]: ...

    async def audits(self, user_id: str, limit: int) -> list[dict[str, Any]]: ...

    async def branding(self, user_id: str) -> dict[str, Any] | None: ...

    async def set_branding(
        self,
        user_id: str,
        company: str,
        logo: bytes | None,
        logo_type: str | None,
        details: BrandingDetails,
    ) -> None: ...

    async def delete_branding(self, user_id: str) -> None: ...


class PostgresBillingRepository:
    """Chaque évènement Stripe est appliqué dans une transaction, une seule fois."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def fulfil_purchase(
        self,
        *,
        event_id: str,
        event_type: str,
        user_id: str,
        lat: float | None,
        lon: float | None,
        label: str | None,
        address_id: str | None,
        origin: str,
        credits: int,
    ) -> bool:
        """Applique un achat ponctuel. Renvoie False si l'évènement était déjà traité."""
        async with db_errors(), self._pool.acquire() as connection, connection.transaction():
            if await connection.fetchval(_RECORD_EVENT, event_id, event_type) is None:
                return False
            if lat is not None and lon is not None:
                await connection.execute(_GRANT, user_id, lon, lat, origin, label, address_id)
            if credits > 0:
                await connection.execute(_ADD_CREDITS, user_id, credits)
            return True

    async def save_subscription(
        self,
        *,
        event_id: str,
        event_type: str,
        user_id: str,
        customer_id: str | None,
        subscription_id: str,
        status: str,
        period_end: datetime | None,
        occurred_at: datetime,
        activation: bool,
    ) -> bool:
        async with db_errors(), self._pool.acquire() as connection, connection.transaction():
            if await connection.fetchval(_RECORD_EVENT, event_id, event_type) is None:
                return False
            await connection.execute(
                _UPSERT_SUBSCRIPTION,
                user_id,
                customer_id,
                subscription_id,
                status,
                period_end,
                occurred_at,
                activation,
            )
            return True

    async def account(self, user_id: str) -> dict[str, Any]:
        async with db_errors():
            record = await self._pool.fetchrow(_ACCOUNT, user_id)
        return dict(record) if record is not None else {"credits": 0, "subscription_active": False}

    async def is_entitled(
        self, user_id: str, lat: float, lon: float, address_id: str | None
    ) -> bool:
        """Vrai si l'utilisateur a déjà débloqué cette adresse (point ou identifiant)."""
        async with db_errors():
            return bool(await self._pool.fetchval(_IS_ENTITLED, user_id, lon, lat, address_id))

    async def customer_id(self, user_id: str) -> str | None:
        async with db_errors():
            value: str | None = await self._pool.fetchval(_CUSTOMER, user_id)
        return value

    async def spend_credit(
        self, user_id: str, lat: float, lon: float, label: str, address_id: str | None
    ) -> bool:
        """Débloque une adresse avec un crédit. Renvoie False s'il n'en reste aucun.

        Une adresse déjà débloquée ne consomme rien.
        """
        async with db_errors(), self._pool.acquire() as connection, connection.transaction():
            if await connection.fetchval(_IS_ENTITLED, user_id, lon, lat, address_id):
                return True
            if await connection.fetchval(_SPEND_CREDIT, user_id) is None:
                return False
            await connection.execute(_GRANT, user_id, lon, lat, "pack", label, address_id)
            return True

    async def audits(self, user_id: str, limit: int) -> list[dict[str, Any]]:
        """Adresses débloquées par l'utilisateur, la plus récente d'abord."""
        async with db_errors():
            records = await self._pool.fetch(_AUDITS, user_id, limit)
        return [dict(record) for record in records]

    async def branding(self, user_id: str) -> dict[str, Any] | None:
        async with db_errors():
            record = await self._pool.fetchrow(_BRANDING, user_id)
        return dict(record) if record is not None else None

    async def set_branding(
        self,
        user_id: str,
        company: str,
        logo: bytes | None,
        logo_type: str | None,
        details: BrandingDetails,
    ) -> None:
        async with db_errors():
            await self._pool.execute(
                _SET_BRANDING,
                user_id,
                company,
                logo,
                logo_type,
                details.color,
                details.phone,
                details.email,
                details.website,
                details.address,
            )

    async def delete_branding(self, user_id: str) -> None:
        async with db_errors():
            await self._pool.execute(_DELETE_BRANDING, user_id)
