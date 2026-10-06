"""Paiement : création des sessions Stripe Checkout et traitement des évènements signés.

Le navigateur ne peut pas ouvrir un droit : seul un évènement dont la signature Stripe est
vérifiée crée un droit, des crédits ou un abonnement.
"""

import hashlib
import hmac
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

from app.core.errors import SourceError
from app.core.http import HttpClient
from app.core.security import AuthenticatedUser
from app.repositories.billing import BillingRepository

logger = logging.getLogger(__name__)

_SIGNATURE_TOLERANCE_S = 300
_PAID_STATUSES = frozenset({"paid", "no_payment_required"})
_CHECKOUT_EVENTS = frozenset(
    {"checkout.session.completed", "checkout.session.async_payment_succeeded"}
)
# « created » est ignoré : il peut arriver après l'activation avec un statut provisoire.
_SUBSCRIPTION_EVENTS = frozenset({"customer.subscription.updated", "customer.subscription.deleted"})
_MAX_LABEL_LENGTH = 300


@dataclass(frozen=True, slots=True)
class Offer:
    id: str
    name: str
    amount_cents: int
    # "payment" : achat ponctuel ; "subscription" : abonnement mensuel.
    mode: str
    # Crédits ajoutés en plus de l'adresse débloquée par l'achat.
    extra_credits: int = 0


# Prix fixés ici, côté serveur : le navigateur ne transmet que l'identifiant de l'offre.
OFFERS: dict[str, Offer] = {
    "unit": Offer("unit", "Audit Contre-Visite (1 adresse)", 499, "payment"),
    "pack": Offer("pack", "Pack Investisseur (10 audits)", 2499, "payment", extra_credits=9),
    "pro": Offer("pro", "Abonnement Pro (audits illimités)", 4900, "subscription"),
}
# Sans adresse à débloquer, le pack crédite les dix audits.
_PACK_SIZE = 10


class BillingNotConfiguredError(Exception):
    """Les clés Stripe ne sont pas renseignées sur cet environnement."""


class AlreadySubscribedError(Exception):
    """L'utilisateur a déjà un abonnement en cours : pas de double facturation."""


class NoSubscriptionError(Exception):
    """Aucun abonnement à gérer pour cet utilisateur."""


class InvalidSignatureError(Exception):
    """L'évènement ne vient pas de Stripe, ou il est trop ancien."""


@dataclass(frozen=True, slots=True)
class CheckoutTarget:
    """Adresse que l'achat doit débloquer (absente pour un abonnement ou un pack seul)."""

    lat: float
    lon: float
    ban_id: str
    label: str


def verify_signature(
    payload: bytes,
    header: str,
    secret: str,
    *,
    now: Callable[[], float] | None = None,
) -> dict[str, Any]:
    """Contrôle l'en-tête Stripe-Signature et renvoie l'évènement décodé.

    Stripe signe « horodatage.corps » en HMAC-SHA256 ; l'horodatage borne le rejeu.
    """
    parts: dict[str, list[str]] = {}
    for item in header.split(","):
        key, _, value = item.strip().partition("=")
        parts.setdefault(key, []).append(value)
    timestamp = parts.get("t", [""])[0]
    current = time.time() if now is None else now()
    if not timestamp.isdigit() or abs(current - int(timestamp)) > _SIGNATURE_TOLERANCE_S:
        raise InvalidSignatureError("timestamp")
    expected = hmac.new(
        secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256
    ).hexdigest()
    if not any(hmac.compare_digest(expected, candidate) for candidate in parts.get("v1", [])):
        raise InvalidSignatureError("signature")
    try:
        event = json.loads(payload)
    except ValueError as exc:
        raise InvalidSignatureError("payload") from exc
    if not isinstance(event, dict):
        raise InvalidSignatureError("payload")
    return event


def checkout_params(
    offer: Offer,
    user: AuthenticatedUser,
    target: CheckoutTarget | None,
    *,
    site_url: str,
    tax_rate_id: str | None = None,
) -> dict[str, str]:
    """Paramètres de création d'une session Stripe Checkout (formulaire à clés imbriquées)."""
    item = "line_items[0]"
    params = {
        "mode": offer.mode,
        "locale": "fr",
        # Vente en nom propre : avec « Managed Payments » (Stripe revendeur), actif par défaut
        # sur les comptes récents, Stripe refuse un produit sans code fiscal.
        "managed_payments[enabled]": "false",
        "client_reference_id": user.id,
        f"{item}[quantity]": "1",
        f"{item}[price_data][currency]": "eur",
        f"{item}[price_data][unit_amount]": str(offer.amount_cents),
        f"{item}[price_data][product_data][name]": offer.name,
        "metadata[user_id]": user.id,
        "metadata[offer]": offer.id,
        "success_url": _return_url(site_url, target, "ok"),
        "cancel_url": f"{site_url.rstrip('/')}/tarifs?paiement=annule",
    }
    if user.email:
        params["customer_email"] = user.email
    if target is not None:
        params["metadata[lat]"] = str(target.lat)
        params["metadata[lon]"] = str(target.lon)
        params["metadata[label]"] = target.label[:_MAX_LABEL_LENGTH]
    if offer.mode == "subscription":
        params[f"{item}[price_data][recurring][interval]"] = "month"
        # Reporté sur l'abonnement : ses évènements futurs désignent ainsi l'utilisateur.
        params["subscription_data[metadata][user_id]"] = user.id
        if tax_rate_id:
            params[f"{item}[tax_rates][0]"] = tax_rate_id
    return params


def _return_url(site_url: str, target: CheckoutTarget | None, outcome: str) -> str:
    """Retour sur le frontend configuré côté serveur : jamais une adresse fournie par le client."""
    query: dict[str, str] = {"paiement": outcome}
    if target is not None:
        query = {"lat": str(target.lat), "lon": str(target.lon), "q": target.label, **query}
        if target.ban_id:
            query["ban_id"] = target.ban_id
    return f"{site_url.rstrip('/')}/?{urlencode(query)}"


def _period_end(subscription: dict[str, Any]) -> datetime | None:
    """Fin de période d'un abonnement ; selon la version de l'API, elle est sur l'élément."""
    value = subscription.get("current_period_end")
    if value is None:
        items = (subscription.get("items") or {}).get("data") or []
        value = items[0].get("current_period_end") if items else None
    return datetime.fromtimestamp(value, UTC) if isinstance(value, int | float) else None


def _coordinate(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _session_url(session: Any) -> str:
    url = session.get("url") if isinstance(session, dict) else None
    if not isinstance(url, str):
        raise SourceError("invalid_response", "session url", transient=False)
    return url


def _occurred_at(event: dict[str, Any]) -> datetime:
    created = event.get("created")
    return datetime.fromtimestamp(created if isinstance(created, int | float) else 0, UTC)


class BillingService:
    def __init__(
        self,
        *,
        http: HttpClient,
        repository: BillingRepository,
        secret_key: str | None,
        webhook_secret: str | None,
        api_url: str,
        site_url: str,
        pro_tax_rate_id: str | None = None,
    ) -> None:
        self._http = http
        self._repository = repository
        self._secret_key = secret_key
        self._webhook_secret = webhook_secret
        self._api_url = api_url.rstrip("/")
        self._site_url = site_url
        self._pro_tax_rate_id = pro_tax_rate_id

    async def start_checkout(
        self, user: AuthenticatedUser, offer_id: str, target: CheckoutTarget | None
    ) -> str:
        """URL de la page de paiement Stripe pour cette offre."""
        if not self._secret_key:
            raise BillingNotConfiguredError
        offer = OFFERS[offer_id]
        if offer.mode == "subscription":
            account = await self._repository.account(user.id)
            if account["subscription_active"]:
                raise AlreadySubscribedError
        session = await self._http.post_form_json(
            "stripe",
            f"{self._api_url}/v1/checkout/sessions",
            data=checkout_params(
                offer, user, target, site_url=self._site_url, tax_rate_id=self._pro_tax_rate_id
            ),
            headers={"Authorization": f"Bearer {self._secret_key}"},
        )
        return _session_url(session)

    async def portal_url(self, user: AuthenticatedUser) -> str:
        """URL du portail client Stripe : factures, moyen de paiement, résiliation."""
        if not self._secret_key:
            raise BillingNotConfiguredError
        customer_id = await self._repository.customer_id(user.id)
        if customer_id is None:
            raise NoSubscriptionError
        session = await self._http.post_form_json(
            "stripe",
            f"{self._api_url}/v1/billing_portal/sessions",
            data={"customer": customer_id, "return_url": f"{self._site_url.rstrip('/')}/tarifs"},
            headers={"Authorization": f"Bearer {self._secret_key}"},
        )
        return _session_url(session)

    def parse_event(self, payload: bytes, signature: str) -> dict[str, Any]:
        if not self._webhook_secret:
            raise BillingNotConfiguredError
        return verify_signature(payload, signature, self._webhook_secret)

    async def handle_event(self, event: dict[str, Any]) -> str:
        """Applique un évènement vérifié. Renvoie ce qui en a été fait (pour le journal)."""
        event_id, event_type = event.get("id"), event.get("type")
        payload = (event.get("data") or {}).get("object")
        if not isinstance(event_id, str) or not isinstance(payload, dict):
            return "ignored"
        if event_type in _CHECKOUT_EVENTS:
            return await self._on_checkout(event, payload)
        if event_type in _SUBSCRIPTION_EVENTS:
            return await self._on_subscription(event, payload)
        return "ignored"

    async def _on_checkout(self, event: dict[str, Any], session: dict[str, Any]) -> str:
        event_id, event_type = str(event["id"]), str(event["type"])
        metadata = session.get("metadata") or {}
        user_id, offer = metadata.get("user_id"), OFFERS.get(str(metadata.get("offer")))
        if not isinstance(user_id, str) or offer is None:
            logger.warning("Session Stripe %s sans utilisateur ou offre connue", session.get("id"))
            return "ignored"
        if offer.mode == "subscription":
            return await self._activate_subscription(event, user_id, session)
        if session.get("payment_status") not in _PAID_STATUSES:
            # Paiement différé (virement, SEPA) : le droit sera ouvert à sa confirmation.
            return "pending"
        lat, lon = _coordinate(metadata.get("lat")), _coordinate(metadata.get("lon"))
        has_address = lat is not None and lon is not None
        credits = offer.extra_credits if has_address else (_PACK_SIZE if offer.id == "pack" else 0)
        applied = await self._repository.fulfil_purchase(
            event_id=event_id,
            event_type=event_type,
            user_id=user_id,
            lat=lat if has_address else None,
            lon=lon if has_address else None,
            label=metadata.get("label"),
            origin=offer.id,
            credits=credits,
        )
        return "fulfilled" if applied else "duplicate"

    async def _activate_subscription(
        self, event: dict[str, Any], user_id: str, session: dict[str, Any]
    ) -> str:
        subscription_id = session.get("subscription")
        if not isinstance(subscription_id, str):
            return "ignored"
        applied = await self._repository.save_subscription(
            event_id=str(event["id"]),
            event_type=str(event["type"]),
            user_id=user_id,
            customer_id=session.get("customer"),
            subscription_id=subscription_id,
            status="active",
            period_end=None,
            occurred_at=_occurred_at(event),
            activation=True,
        )
        return "subscribed" if applied else "duplicate"

    async def _on_subscription(self, event: dict[str, Any], subscription: dict[str, Any]) -> str:
        event_id, event_type = str(event["id"]), str(event["type"])
        user_id = (subscription.get("metadata") or {}).get("user_id")
        subscription_id = subscription.get("id")
        if not isinstance(user_id, str) or not isinstance(subscription_id, str):
            return "ignored"
        status = "canceled" if event_type.endswith(".deleted") else str(subscription.get("status"))
        applied = await self._repository.save_subscription(
            event_id=event_id,
            event_type=event_type,
            user_id=user_id,
            customer_id=subscription.get("customer"),
            subscription_id=subscription_id,
            status=status,
            period_end=_period_end(subscription),
            occurred_at=_occurred_at(event),
            activation=False,
        )
        return "subscription_updated" if applied else "duplicate"
