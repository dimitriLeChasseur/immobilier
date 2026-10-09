"""Paiement : signature des évènements Stripe, attribution des droits, routes."""

import hashlib
import hmac
import json
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_billing_repository, get_billing_service, get_rate_limiter
from app.api.routers import billing
from app.core.errors import SourceError
from app.core.rate_limit import SlidingWindowRateLimiter
from app.core.security import AuthenticatedUser
from app.schemas.audit import Location
from app.services.billing import (
    OFFERS,
    BillingService,
    CheckoutTarget,
    InvalidSignatureError,
    checkout_params,
    verify_signature,
)

WEBHOOK_SECRET = "whsec_test"  # noqa: S105
USER = AuthenticatedUser(id="3f0c1f0e-6f1d-4b1e-9d59-0a1c2b3d4e5f", email="a@example.org")
TARGET = CheckoutTarget(48.86, 2.33, "75101_1234_00001", "1 rue de Rivoli 75001 Paris")
NOW = 1_800_000_000
# Identifiant résolu par le serveur, distinct de celui que le navigateur envoie.
RESOLVED_ID = "75101_8525_00001"


def sign(payload: bytes, *, secret: str = WEBHOOK_SECRET, timestamp: int = NOW) -> str:
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256)
    return f"t={timestamp},v1={digest.hexdigest()}"


class FakeRepository:
    def __init__(self) -> None:
        self.events: set[str] = set()
        self.purchases: list[dict[str, Any]] = []
        self.subscriptions: list[dict[str, Any]] = []
        self.credits = 0
        self.subscription_active = False
        self.unlocked: list[tuple[float, float]] = []
        self.unlocked_ids: list[str | None] = []
        self.customer: str | None = None
        self.already_unlocked = False
        self.refunds: list[dict[str, Any]] = []
        self.active_subscription: str | None = None

    def _is_new(self, event_id: str) -> bool:
        if event_id in self.events:
            return False
        self.events.add(event_id)
        return True

    async def fulfil_purchase(self, *, event_id: str, **purchase: Any) -> bool:
        if not self._is_new(event_id):
            return False
        self.purchases.append(purchase)
        self.credits += purchase["credits"]
        return True

    async def save_subscription(self, *, event_id: str, **subscription: Any) -> bool:
        if not self._is_new(event_id):
            return False
        self.subscriptions.append(subscription)
        return True

    async def account(self, user_id: str) -> dict[str, Any]:
        return {"credits": self.credits, "subscription_active": self.subscription_active}

    async def spend_credit(
        self, user_id: str, lat: float, lon: float, label: str, address_id: str | None
    ) -> bool:
        if self.credits == 0:
            return False
        self.credits -= 1
        self.unlocked.append((lat, lon))
        self.unlocked_ids.append(address_id)
        return True

    async def customer_id(self, user_id: str) -> str | None:
        return self.customer

    async def is_entitled(
        self, user_id: str, lat: float, lon: float, address_id: str | None
    ) -> bool:
        return self.already_unlocked

    async def is_recorded(self, event_id: str) -> bool:
        return event_id in self.events

    async def revoke_purchase(self, *, event_id: str, **refund: Any) -> bool:
        if not self._is_new(event_id):
            return False
        self.refunds.append(refund)
        self.credits = max(self.credits - refund["credits"], 0)
        return True

    async def subscription_id(self, user_id: str) -> str | None:
        return self.active_subscription

    async def record_event(self, event_id: str, event_type: str) -> bool:
        return self._is_new(event_id)


class FakeHttp:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str], dict[str, str]]] = []
        self.deleted: list[str] = []
        self.fail = False

    async def delete(
        self, source: str, url: str, *, headers: Mapping[str, str] | None = None
    ) -> Any:
        if self.fail:
            raise SourceError("http_error", "500")
        self.deleted.append(url)
        return None

    async def post_form_json(
        self,
        source: str,
        url: str,
        *,
        data: Mapping[str, str],
        timeout_s: float | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        if self.fail:
            raise SourceError("http_error", "500")
        self.calls.append((url, dict(data), dict(headers or {})))
        return {"id": "cs_test_1", "url": "https://checkout.stripe.com/c/pay/cs_test_1"}


class FakeGeocoder:
    """Résout toujours la même adresse BAN, ou échoue comme une BAN indisponible."""

    def __init__(self) -> None:
        self.fail = False

    async def reverse(self, lat: float, lon: float, ban_id: str) -> Location | None:
        if self.fail:
            raise SourceError("timeout", "ban")
        return Location(lat=lat, lon=lon, label="x", citycode="75101", adresse_id=RESOLVED_ID)


GEOCODER = FakeGeocoder()


@pytest.fixture(autouse=True)
def _geocoder_is_up() -> None:
    GEOCODER.fail = False


@pytest.fixture
def repository() -> FakeRepository:
    return FakeRepository()


@pytest.fixture
def http() -> FakeHttp:
    return FakeHttp()


def make_service(
    repository: FakeRepository, http: FakeHttp, *, configured: bool = True
) -> BillingService:
    return BillingService(
        http=http,  # type: ignore[arg-type]
        repository=repository,
        geocoder=GEOCODER,
        secret_key="sk_test_x" if configured else None,
        webhook_secret=WEBHOOK_SECRET if configured else None,
        api_url="https://stripe.test",
        site_url="https://app.example.org/",
    )


@pytest.fixture
def service(repository: FakeRepository, http: FakeHttp) -> BillingService:
    return make_service(repository, http)


def checkout_event(
    offer: str, *, event_id: str = "evt_1", address: bool = True, **session: Any
) -> dict[str, Any]:
    metadata = {"user_id": USER.id, "offer": offer}
    if address:
        metadata |= {"lat": "48.86", "lon": "2.33", "label": TARGET.label, "ban_id": RESOLVED_ID}
    return {
        "id": event_id,
        "type": "checkout.session.completed",
        "created": NOW,
        "data": {
            "object": {"id": "cs_1", "payment_status": "paid", "metadata": metadata, **session}
        },
    }


# --- Signature


def test_signature_accepts_a_genuine_event() -> None:
    payload = b'{"id": "evt_1"}'
    assert verify_signature(payload, sign(payload), WEBHOOK_SECRET, now=lambda: NOW) == {
        "id": "evt_1"
    }


@pytest.mark.parametrize(
    "header",
    [
        "",
        "v1=abc",
        "t=abc,v1=abc",
        f"t={NOW},v1=" + "0" * 64,
        sign(b'{"id": "evt_1"}', secret="whsec_other"),  # noqa: S106,
        sign(b'{"id": "evt_2"}'),
    ],
)
def test_signature_rejects_forged_events(header: str) -> None:
    with pytest.raises(InvalidSignatureError):
        verify_signature(b'{"id": "evt_1"}', header, WEBHOOK_SECRET, now=lambda: NOW)


def test_signature_rejects_replayed_events() -> None:
    payload = b'{"id": "evt_1"}'
    with pytest.raises(InvalidSignatureError):
        verify_signature(payload, sign(payload), WEBHOOK_SECRET, now=lambda: NOW + 301)


# --- Session de paiement


def test_checkout_params_fix_the_price_server_side() -> None:
    params = checkout_params(OFFERS["unit"], USER, TARGET, site_url="https://app.example.org/")
    assert params["mode"] == "payment"
    assert params["managed_payments[enabled]"] == "false"
    assert params["line_items[0][price_data][unit_amount]"] == "499"
    assert params["line_items[0][price_data][currency]"] == "eur"
    assert params["metadata[user_id]"] == USER.id
    assert params["metadata[lat]"] == "48.86"
    assert params["customer_email"] == "a@example.org"
    assert params["success_url"].startswith("https://app.example.org/?lat=48.86&lon=2.33&q=1+rue")
    assert "paiement=ok" in params["success_url"]
    assert params["cancel_url"] == "https://app.example.org/tarifs?paiement=annule"


def test_subscription_checkout_is_recurring_and_carries_the_user() -> None:
    params = checkout_params(
        OFFERS["pro"], USER, None, site_url="https://app.example.org", tax_rate_id="txr_1"
    )
    assert params["mode"] == "subscription"
    assert params["line_items[0][price_data][unit_amount]"] == "4900"
    assert params["line_items[0][price_data][recurring][interval]"] == "month"
    assert params["line_items[0][tax_rates][0]"] == "txr_1"
    assert params["subscription_data[metadata][user_id]"] == USER.id
    assert params["success_url"] == "https://app.example.org/?paiement=ok"


# --- Évènements


async def test_unit_purchase_unlocks_the_address(
    service: BillingService, repository: FakeRepository
) -> None:
    assert await service.handle_event(checkout_event("unit")) == "fulfilled"
    assert repository.purchases == [
        {
            "event_type": "checkout.session.completed",
            "user_id": USER.id,
            "lat": 48.86,
            "lon": 2.33,
            "label": TARGET.label,
            "address_id": RESOLVED_ID,
            "origin": "unit",
            "credits": 0,
        }
    ]


async def test_pack_unlocks_the_address_and_credits_the_rest(
    service: BillingService, repository: FakeRepository
) -> None:
    await service.handle_event(checkout_event("pack"))
    assert repository.purchases[0]["credits"] == 9
    assert repository.purchases[0]["lat"] == 48.86


async def test_pack_without_address_credits_ten_audits(
    service: BillingService, repository: FakeRepository
) -> None:
    await service.handle_event(checkout_event("pack", address=False))
    assert repository.purchases[0]["credits"] == 10
    assert repository.purchases[0]["lat"] is None


async def test_event_delivered_twice_is_applied_once(
    service: BillingService, repository: FakeRepository
) -> None:
    await service.handle_event(checkout_event("pack"))
    assert await service.handle_event(checkout_event("pack")) == "duplicate"
    assert repository.credits == 9


async def test_unpaid_session_grants_nothing(
    service: BillingService, repository: FakeRepository
) -> None:
    event = checkout_event("unit", payment_status="unpaid")
    assert await service.handle_event(event) == "pending"
    assert repository.purchases == []


@pytest.mark.parametrize(
    "event",
    [
        {"id": "evt_1", "type": "payment_intent.succeeded", "data": {"object": {}}},
        {"id": "evt_1", "type": "checkout.session.completed", "data": {"object": {"metadata": {}}}},
        {"type": "checkout.session.completed"},
        checkout_event("gold"),
    ],
)
async def test_unknown_events_are_ignored(
    service: BillingService, repository: FakeRepository, event: dict[str, Any]
) -> None:
    assert await service.handle_event(event) == "ignored"
    assert repository.purchases == []


async def test_subscription_lifecycle(service: BillingService, repository: FakeRepository) -> None:
    activation = checkout_event("pro", address=False, subscription="sub_1", customer="cus_1")
    assert await service.handle_event(activation) == "subscribed"
    assert repository.subscriptions[0]["status"] == "active"
    assert repository.subscriptions[0]["activation"] is True

    def subscription_event(event_id: str, kind: str, status: str) -> dict[str, Any]:
        return {
            "id": event_id,
            "type": f"customer.subscription.{kind}",
            "created": NOW + 60,
            "data": {
                "object": {
                    "id": "sub_1",
                    "status": status,
                    "customer": "cus_1",
                    "metadata": {"user_id": USER.id},
                    "items": {"data": [{"current_period_end": NOW + 86_400}]},
                }
            },
        }

    await service.handle_event(subscription_event("evt_2", "updated", "past_due"))
    await service.handle_event(subscription_event("evt_3", "deleted", "active"))
    assert [item["status"] for item in repository.subscriptions] == [
        "active",
        "past_due",
        "canceled",
    ]
    assert repository.subscriptions[1]["period_end"] == datetime.fromtimestamp(NOW + 86_400, UTC)
    assert repository.subscriptions[1]["activation"] is False
    # « created » peut suivre l'activation avec un statut provisoire : il n'est pas appliqué.
    assert await service.handle_event(subscription_event("evt_4", "created", "incomplete")) == (
        "ignored"
    )


# --- Routes


def token(secret: str = "test") -> str:  # noqa: S107
    claims = {
        "sub": USER.id,
        "email": USER.email,
        "role": "authenticated",
        "aud": "authenticated",
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    return jwt.encode(claims, secret, algorithm="HS256")


AUTH = {"Authorization": f"Bearer {token()}"}
ADDRESS = {"lat": 48.86, "lon": 2.33, "ban_id": TARGET.ban_id, "label": TARGET.label}


def make_client(service: BillingService, repository: FakeRepository) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(billing.router)
    limiter = SlidingWindowRateLimiter(limit=20, window_s=60)
    app.dependency_overrides[get_billing_service] = lambda: service
    app.dependency_overrides[get_billing_repository] = lambda: repository
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def client(service: BillingService, repository: FakeRepository) -> Iterator[TestClient]:
    yield from make_client(service, repository)


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/v1/account"),
        ("post", "/api/v1/checkout"),
        ("post", "/api/v1/unlock"),
        ("post", "/api/v1/billing/portal"),
    ],
)
def test_payment_routes_require_a_session(client: TestClient, method: str, path: str) -> None:
    assert client.request(method, path, json={"offer": "pack"}).status_code == 401
    forged = {"Authorization": f"Bearer {token('other-secret')}"}
    assert client.request(method, path, json={"offer": "pack"}, headers=forged).status_code == 401


def test_checkout_returns_the_stripe_url(client: TestClient, http: FakeHttp) -> None:
    response = client.post(
        "/api/v1/checkout", json={"offer": "unit", "address": ADDRESS}, headers=AUTH
    )
    assert response.status_code == 200
    assert response.json() == {"url": "https://checkout.stripe.com/c/pay/cs_test_1"}
    url, data, headers = http.calls[0]
    assert url == "https://stripe.test/v1/checkout/sessions"
    assert headers == {"Authorization": "Bearer sk_test_x"}
    assert data["metadata[user_id]"] == USER.id
    # L'identifiant d'adresse vient du géocodage serveur, pas du ban_id envoyé par le client.
    assert data["metadata[ban_id]"] == RESOLVED_ID


def test_checkout_survives_a_geocoder_outage(client: TestClient, http: FakeHttp) -> None:
    GEOCODER.fail = True
    response = client.post(
        "/api/v1/checkout", json={"offer": "unit", "address": ADDRESS}, headers=AUTH
    )
    assert response.status_code == 200
    assert "metadata[ban_id]" not in http.calls[0][1]


@pytest.mark.parametrize(
    "body",
    [
        {"offer": "unit"},
        {"offer": "gold", "address": ADDRESS},
        {"offer": "unit", "address": ADDRESS, "amount": 1},
        {"offer": "unit", "address": ADDRESS | {"lat": 120}},
        {"offer": "unit", "address": ADDRESS | {"success_url": "https://evil.example"}},
    ],
)
def test_checkout_rejects_invalid_requests(
    client: TestClient, http: FakeHttp, body: dict[str, Any]
) -> None:
    assert client.post("/api/v1/checkout", json=body, headers=AUTH).status_code == 422
    assert http.calls == []


def test_checkout_refuses_a_second_subscription(
    client: TestClient, repository: FakeRepository, http: FakeHttp
) -> None:
    repository.subscription_active = True
    assert client.post("/api/v1/checkout", json={"offer": "pro"}, headers=AUTH).status_code == 409
    assert http.calls == []


def test_an_address_already_unlocked_is_not_sold_again(
    client: TestClient, repository: FakeRepository, http: FakeHttp
) -> None:
    repository.already_unlocked = True
    unit = client.post("/api/v1/checkout", json={"offer": "unit", "address": ADDRESS}, headers=AUTH)
    assert unit.status_code == 409
    assert unit.json()["detail"] == "Cette adresse est déjà débloquée sur votre compte."
    assert http.calls == []

    # Le pack reste achetable, mais il ne « dépense » pas un audit sur cette adresse : sans
    # adresse à débloquer, le paiement crédite les dix audits.
    pack = client.post("/api/v1/checkout", json={"offer": "pack", "address": ADDRESS}, headers=AUTH)
    assert pack.status_code == 200
    data = http.calls[0][1]
    assert "metadata[lat]" not in data
    assert "metadata[ban_id]" not in data
    # Le retour après paiement ramène tout de même à l'adresse consultée.
    assert "lat=48.86" in data["success_url"]


def test_a_subscriber_is_not_sold_a_single_address(
    client: TestClient, repository: FakeRepository, http: FakeHttp
) -> None:
    repository.subscription_active = True
    response = client.post(
        "/api/v1/checkout", json={"offer": "unit", "address": ADDRESS}, headers=AUTH
    )
    assert response.status_code == 409
    assert http.calls == []


def test_checkout_reports_stripe_failures(client: TestClient, http: FakeHttp) -> None:
    http.fail = True
    assert client.post("/api/v1/checkout", json={"offer": "pack"}, headers=AUTH).status_code == 502


def test_payment_is_closed_without_keys(repository: FakeRepository, http: FakeHttp) -> None:
    service = make_service(repository, http, configured=False)
    client = next(make_client(service, repository))
    assert client.post("/api/v1/checkout", json={"offer": "pack"}, headers=AUTH).status_code == 503
    payload = json.dumps(checkout_event("unit")).encode()
    response = client.post(
        "/api/v1/stripe/webhook", content=payload, headers={"Stripe-Signature": sign(payload)}
    )
    assert response.status_code == 503
    assert repository.purchases == []


def test_unlock_spends_one_credit(client: TestClient, repository: FakeRepository) -> None:
    repository.credits = 2
    response = client.post("/api/v1/unlock", json=ADDRESS, headers=AUTH)
    assert response.status_code == 200
    assert response.json() == {"email": USER.email, "credits": 1, "subscription_active": False}
    assert repository.unlocked == [(48.86, 2.33)]
    assert repository.unlocked_ids == [RESOLVED_ID]


def test_unlock_without_credit_is_402(client: TestClient) -> None:
    assert client.post("/api/v1/unlock", json=ADDRESS, headers=AUTH).status_code == 402


def test_portal_needs_a_subscription(
    client: TestClient, repository: FakeRepository, http: FakeHttp
) -> None:
    assert client.post("/api/v1/billing/portal", headers=AUTH).status_code == 404
    repository.customer = "cus_1"
    assert client.post("/api/v1/billing/portal", headers=AUTH).status_code == 200
    assert http.calls[0][1] == {
        "customer": "cus_1",
        "return_url": "https://app.example.org/tarifs",
    }


def test_webhook_applies_signed_events_only(
    client: TestClient, repository: FakeRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.services.billing.time.time", lambda: NOW)
    payload = json.dumps(checkout_event("unit")).encode()

    unsigned = client.post("/api/v1/stripe/webhook", content=payload)
    forged = client.post(
        "/api/v1/stripe/webhook",
        content=payload,
        headers={"Stripe-Signature": sign(payload, secret="whsec_guess")},  # noqa: S106
    )
    assert (unsigned.status_code, forged.status_code) == (400, 400)
    assert repository.purchases == []

    genuine = client.post(
        "/api/v1/stripe/webhook", content=payload, headers={"Stripe-Signature": sign(payload)}
    )
    assert genuine.status_code == 200
    assert genuine.json() == {"status": "fulfilled"}
    assert len(repository.purchases) == 1


def refund_event(offer: str, *, refunded: bool = True, address: bool = True) -> dict[str, Any]:
    metadata = {"user_id": USER.id, "offer": offer}
    if address:
        metadata |= {"lat": "48.86", "lon": "2.33", "ban_id": RESOLVED_ID}
    charge = {"id": "ch_1", "refunded": refunded, "metadata": metadata}
    return {"id": f"evt_refund_{offer}", "type": "charge.refunded", "data": {"object": charge}}


async def test_a_full_refund_takes_back_the_address_and_the_unused_credits(
    service: BillingService, repository: FakeRepository
) -> None:
    repository.credits = 9
    assert await service.handle_event(refund_event("pack")) == "refunded"
    assert repository.refunds == [
        {
            "event_type": "charge.refunded",
            "user_id": USER.id,
            "lat": 48.86,
            "lon": 2.33,
            "address_id": RESOLVED_ID,
            "credits": 9,
        }
    ]
    assert repository.credits == 0
    assert await service.handle_event(refund_event("pack")) == "duplicate"

    await service.handle_event(refund_event("unit"))
    assert repository.refunds[-1]["credits"] == 0


async def test_partial_refunds_and_unknown_charges_take_nothing_back(
    service: BillingService, repository: FakeRepository
) -> None:
    assert await service.handle_event(refund_event("unit", refunded=False)) == "ignored"
    # Paiement antérieur à l'ajout des métadonnées : rien ne permet de savoir quoi retirer.
    legacy = {"id": "evt_x", "type": "charge.refunded", "data": {"object": {"refunded": True}}}
    assert await service.handle_event(legacy) == "ignored"
    assert repository.refunds == []


def test_payment_carries_what_a_refund_needs_to_identify_the_purchase() -> None:
    params = checkout_params(
        OFFERS["unit"], USER, TARGET, site_url="https://a.fr", address_id="x_1"
    )
    assert params["payment_intent_data[metadata][user_id]"] == USER.id
    assert params["payment_intent_data[metadata][offer]"] == "unit"
    assert params["payment_intent_data[metadata][lat]"] == "48.86"
    assert params["payment_intent_data[metadata][ban_id]"] == "x_1"
    pro = checkout_params(OFFERS["pro"], USER, None, site_url="https://a.fr")
    assert not any(key.startswith("payment_intent_data") for key in pro)


async def test_deleting_an_account_stops_its_subscription_first(
    service: BillingService, repository: FakeRepository, http: FakeHttp
) -> None:
    await service.cancel_subscription(USER.id)
    assert http.deleted == []
    repository.active_subscription = "sub_1"
    await service.cancel_subscription(USER.id)
    assert http.deleted == ["https://stripe.test/v1/subscriptions/sub_1"]
