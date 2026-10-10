"""SQL du paiement exécuté sur une vraie base : droits, crédits, abonnements, plafond Pro.

Les tests de test_billing.py simulent le dépôt ; ceux-ci vérifient les requêtes elles-mêmes,
leurs transactions et leurs contraintes. Ils sont ignorés sans les deux accès :

    IMMO_TEST_DATABASE_URL=postgresql://immo_app:<mot de passe>@127.0.0.1:5433/postgres \\
    IMMO_TEST_ADMIN_DATABASE_URL=postgresql://supabase_admin:<mdp>@127.0.0.1:5433/postgres \\
        uv run pytest tests/test_integration_billing_sql.py

L'accès d'administration ne sert qu'à créer puis supprimer les comptes de test dans auth.users,
que le rôle applicatif ne peut pas écrire. La suppression emporte leurs lignes par cascade.
"""

import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import asyncpg
import pytest

from app.core.errors import RepositoryError
from app.repositories.billing import BrandingDetails, PostgresBillingRepository
from app.repositories.db import create_pool
from app.repositories.entitlements import PostgresEntitlementRepository

DSN = os.environ.get("IMMO_TEST_DATABASE_URL")
ADMIN_DSN = os.environ.get("IMMO_TEST_ADMIN_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    DSN is None or ADMIN_DSN is None,
    reason="IMMO_TEST_DATABASE_URL ou IMMO_TEST_ADMIN_DATABASE_URL non défini",
)

EMAIL_DOMAIN = "@test-integration.invalid"
EVENT_PREFIX = "evt_test_integration_"
# Loin de toute donnée réelle ; deux points distants de plus d'une cellule de geohash.
LAT, LON = 0.5, 0.5
OTHER_LAT, OTHER_LON = 0.6, 0.6
BAN_ID = "00999_0001_00001"
NOW = datetime(2026, 10, 1, tzinfo=UTC)


async def _clean(admin: asyncpg.Connection, pool: asyncpg.Pool) -> None:
    await admin.execute("DELETE FROM auth.users WHERE email LIKE $1", f"%{EMAIL_DOMAIN}")
    await pool.execute("DELETE FROM stripe_events WHERE event_id LIKE $1", f"{EVENT_PREFIX}%")


@pytest.fixture
async def pool() -> AsyncIterator[asyncpg.Pool]:
    assert DSN is not None
    database = await create_pool(DSN)
    try:
        yield database
    finally:
        await database.close()


@pytest.fixture
async def user_id(pool: asyncpg.Pool) -> AsyncIterator[str]:
    assert ADMIN_DSN is not None
    admin = await asyncpg.connect(ADMIN_DSN)
    await _clean(admin, pool)
    identifier = str(uuid.uuid4())
    await admin.execute(
        "INSERT INTO auth.users (id, email) VALUES ($1::uuid, $2)",
        identifier,
        f"{identifier}{EMAIL_DOMAIN}",
    )
    try:
        yield identifier
    finally:
        await _clean(admin, pool)
        await admin.close()


@pytest.fixture
def billing(pool: asyncpg.Pool) -> PostgresBillingRepository:
    return PostgresBillingRepository(pool)


@pytest.fixture
def entitlements(pool: asyncpg.Pool) -> PostgresEntitlementRepository:
    return PostgresEntitlementRepository(pool)


def event(name: str) -> str:
    return f"{EVENT_PREFIX}{name}_{uuid.uuid4().hex[:8]}"


async def buy_unit(
    billing: PostgresBillingRepository, user_id: str, event_id: str, *, credits: int = 0
) -> bool:
    return await billing.fulfil_purchase(
        event_id=event_id,
        event_type="checkout.session.completed",
        user_id=user_id,
        lat=LAT,
        lon=LON,
        label="1 rue du Test",
        address_id=BAN_ID,
        origin="unit",
        credits=credits,
    )


async def subscribe(
    billing: PostgresBillingRepository,
    user_id: str,
    *,
    subscription: str,
    status: str = "active",
    period_end: datetime | None = None,
    occurred_at: datetime = NOW,
    activation: bool = False,
) -> bool:
    return await billing.save_subscription(
        event_id=event("sub"),
        event_type="customer.subscription.updated",
        user_id=user_id,
        customer_id="cus_test",
        subscription_id=subscription,
        status=status,
        period_end=period_end,
        occurred_at=occurred_at,
        activation=activation,
    )


async def test_a_purchase_opens_the_address_and_only_that_one(
    billing: PostgresBillingRepository, entitlements: PostgresEntitlementRepository, user_id: str
) -> None:
    assert not await entitlements.has_access(user_id, LAT, LON, BAN_ID)

    assert await buy_unit(billing, user_id, event("unit"))

    assert await entitlements.has_access(user_id, LAT, LON, BAN_ID)
    assert await billing.is_entitled(user_id, LAT, LON, None), "le point acheté suffit"
    # La BAN a déplacé le point : le droit suit l'identifiant de l'adresse.
    assert await entitlements.has_access(user_id, OTHER_LAT, OTHER_LON, BAN_ID)
    assert not await entitlements.has_access(user_id, OTHER_LAT, OTHER_LON, "00999_0002_00001")
    stranger = str(uuid.uuid4())
    assert not await entitlements.has_access(stranger, LAT, LON, BAN_ID)

    [audit] = await billing.audits(user_id, 10)
    assert (audit["label"], audit["ban_id"], audit["origin"]) == ("1 rue du Test", BAN_ID, "unit")
    # Le point restitué retombe dans la cellule achetée.
    assert await billing.is_entitled(user_id, audit["lat"], audit["lon"], None)


async def test_an_event_delivered_twice_is_applied_once(
    billing: PostgresBillingRepository, user_id: str
) -> None:
    event_id = event("pack")
    for expected in (True, False):
        applied = await billing.fulfil_purchase(
            event_id=event_id,
            event_type="checkout.session.completed",
            user_id=user_id,
            lat=None,
            lon=None,
            label=None,
            address_id=None,
            origin="pack",
            credits=10,
        )
        assert applied is expected
    assert (await billing.account(user_id))["credits"] == 10
    assert await billing.is_recorded(event_id)
    assert not await billing.record_event(event_id, "x")


async def test_a_failed_purchase_leaves_the_event_replayable(
    billing: PostgresBillingRepository,
) -> None:
    # Compte inexistant : la clé étrangère rejette les crédits, la transaction est annulée
    # et l'évènement n'est pas noté comme traité. Stripe pourra le renvoyer.
    event_id = event("orphan")
    with pytest.raises(RepositoryError):
        await billing.fulfil_purchase(
            event_id=event_id,
            event_type="checkout.session.completed",
            user_id=str(uuid.uuid4()),
            lat=None,
            lon=None,
            label=None,
            address_id=None,
            origin="pack",
            credits=10,
        )
    assert not await billing.is_recorded(event_id)


async def test_a_credit_unlocks_one_address_and_is_never_spent_twice(
    billing: PostgresBillingRepository, user_id: str
) -> None:
    assert not await billing.spend_credit(user_id, LAT, LON, "1 rue du Test", BAN_ID), (
        "aucun crédit"
    )
    await billing.fulfil_purchase(
        event_id=event("pack"),
        event_type="checkout.session.completed",
        user_id=user_id,
        lat=None,
        lon=None,
        label=None,
        address_id=None,
        origin="pack",
        credits=2,
    )

    assert await billing.spend_credit(user_id, LAT, LON, "1 rue du Test", BAN_ID)
    assert (await billing.account(user_id))["credits"] == 1
    # Adresse déjà débloquée, par son point ou son identifiant : rien n'est consommé.
    assert await billing.spend_credit(user_id, LAT, LON, "1 rue du Test", None)
    assert await billing.spend_credit(user_id, OTHER_LAT, OTHER_LON, "1 rue du Test", BAN_ID)
    assert (await billing.account(user_id))["credits"] == 1

    assert await billing.spend_credit(user_id, OTHER_LAT, OTHER_LON, "2 rue du Test", "00999_2")
    assert (await billing.account(user_id))["credits"] == 0
    assert not await billing.spend_credit(user_id, 0.7, 0.7, "3 rue du Test", "00999_3")
    assert [audit["origin"] for audit in await billing.audits(user_id, 10)] == ["pack", "pack"]


async def test_a_refund_revokes_the_address_and_the_unused_credits(
    billing: PostgresBillingRepository, entitlements: PostgresEntitlementRepository, user_id: str
) -> None:
    await buy_unit(billing, user_id, event("unit"), credits=3)
    refund = event("refund")
    for expected in (True, False):
        revoked = await billing.revoke_purchase(
            event_id=refund,
            event_type="charge.refunded",
            user_id=user_id,
            lat=LAT,
            lon=LON,
            address_id=BAN_ID,
            credits=10,
        )
        assert revoked is expected
    assert not await entitlements.has_access(user_id, LAT, LON, BAN_ID)
    # Plus de crédits retirés qu'il n'en reste : le solde s'arrête à zéro.
    assert (await billing.account(user_id))["credits"] == 0


async def test_a_subscription_opens_every_address_while_it_lasts(
    billing: PostgresBillingRepository, entitlements: PostgresEntitlementRepository, user_id: str
) -> None:
    soon = datetime.now(UTC) + timedelta(days=20)
    assert await subscribe(billing, user_id, subscription="sub_a", period_end=soon, activation=True)

    assert await entitlements.has_access(user_id, OTHER_LAT, OTHER_LON, None)
    assert (await billing.account(user_id))["subscription_active"] is True
    assert await billing.subscription_id(user_id) == "sub_a"
    assert await billing.customer_id(user_id) == "cus_test"

    # Échéance dépassée depuis moins de trois jours : tolérance le temps du renouvellement.
    late = datetime.now(UTC) - timedelta(days=1)
    await subscribe(
        billing, user_id, subscription="sub_a", period_end=late, occurred_at=NOW + timedelta(1)
    )
    assert await entitlements.has_access(user_id, LAT, LON, None)

    expired = datetime.now(UTC) - timedelta(days=4)
    await subscribe(
        billing, user_id, subscription="sub_a", period_end=expired, occurred_at=NOW + timedelta(2)
    )
    assert not await entitlements.has_access(user_id, LAT, LON, None)
    assert (await billing.account(user_id))["subscription_active"] is False


async def test_late_or_foreign_subscription_events_do_not_overwrite_the_current_one(
    billing: PostgresBillingRepository, user_id: str, pool: asyncpg.Pool
) -> None:
    await subscribe(billing, user_id, subscription="sub_a", activation=True)

    async def status() -> tuple[str, str]:
        row = await pool.fetchrow(
            "SELECT stripe_subscription_id, status FROM user_subscriptions"
            " WHERE user_id = $1::uuid",
            user_id,
        )
        assert row is not None
        return row["stripe_subscription_id"], row["status"]

    # Évènement plus ancien que le dernier appliqué, livré en retard.
    await subscribe(
        billing,
        user_id,
        subscription="sub_a",
        status="canceled",
        occurred_at=NOW - timedelta(hours=1),
    )
    assert await status() == ("sub_a", "active")

    # Évènement d'un autre abonnement, sans activation : il ne concerne pas l'abonnement suivi.
    await subscribe(
        billing,
        user_id,
        subscription="sub_b",
        status="canceled",
        occurred_at=NOW + timedelta(hours=1),
    )
    assert await status() == ("sub_a", "active")

    # Nouvel abonnement payé : il remplace le précédent.
    await subscribe(
        billing,
        user_id,
        subscription="sub_b",
        occurred_at=NOW + timedelta(hours=2),
        activation=True,
    )
    assert await status() == ("sub_b", "active")

    await subscribe(
        billing,
        user_id,
        subscription="sub_b",
        status="canceled",
        occurred_at=NOW + timedelta(hours=3),
    )
    assert await status() == ("sub_b", "canceled")
    assert await billing.subscription_id(user_id) is None


async def test_views_are_kept_once_per_address_most_recent_first(
    billing: PostgresBillingRepository, entitlements: PostgresEntitlementRepository, user_id: str
) -> None:
    await entitlements.record_view(user_id, LAT, LON, "1 rue du Test", BAN_ID)
    await entitlements.record_view(user_id, OTHER_LAT, OTHER_LON, "2 rue du Test", None)
    await entitlements.record_view(user_id, LAT, LON, "1 rue du Test (bis)", BAN_ID)

    history = await billing.history(user_id, 10)
    assert [view["label"] for view in history] == ["1 rue du Test (bis)", "2 rue du Test"]
    assert len(await billing.history(user_id, 1)) == 1


async def test_subscriber_usage_counts_other_addresses_seen_in_the_last_day(
    billing: PostgresBillingRepository,
    entitlements: PostgresEntitlementRepository,
    user_id: str,
    pool: asyncpg.Pool,
) -> None:
    assert await entitlements.subscription_usage(user_id, LAT, LON, None) == 0

    await entitlements.record_view(user_id, OTHER_LAT, OTHER_LON, "2 rue du Test", None)
    await entitlements.record_view(user_id, 0.7, 0.7, "3 rue du Test", None)
    assert await entitlements.subscription_usage(user_id, LAT, LON, None) == 2
    # Adresse déjà comptée aujourd'hui : la revoir ne consomme rien.
    assert await entitlements.subscription_usage(user_id, 0.7, 0.7, None) is None

    # Une consultation de plus de 24 heures ne compte plus.
    await pool.execute(
        "UPDATE audit_history SET viewed_at = now() - interval '25 hours'"
        " WHERE user_id = $1::uuid AND label = '3 rue du Test'",
        user_id,
    )
    assert await entitlements.subscription_usage(user_id, LAT, LON, None) == 1
    assert await entitlements.subscription_usage(user_id, 0.7, 0.7, None) == 1

    # Adresse achetée : hors plafond, quel que soit l'usage.
    await buy_unit(billing, user_id, event("unit"))
    assert await entitlements.subscription_usage(user_id, LAT, LON, BAN_ID) is None


async def test_branding_is_saved_replaced_and_deleted(
    billing: PostgresBillingRepository, user_id: str
) -> None:
    assert await billing.branding(user_id) is None
    await billing.set_branding(user_id, "Agence Test", None, None, BrandingDetails())
    await billing.set_branding(
        user_id, "Agence Test 2", b"\x89PNG", "image/png", BrandingDetails(color="#0a0b0c")
    )
    saved = await billing.branding(user_id)
    assert saved is not None
    assert (saved["company"], saved["logo"], saved["color"]) == (
        "Agence Test 2",
        b"\x89PNG",
        "#0a0b0c",
    )
    await billing.delete_branding(user_id)
    assert await billing.branding(user_id) is None
