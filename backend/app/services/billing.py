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
from app.core.mailer import Mailer
from app.core.security import AuthenticatedUser
from app.repositories.billing import BillingRepository
from app.services.emails import receipt_email
from app.services.geocoding import Geocoder

logger = logging.getLogger(__name__)

_SIGNATURE_TOLERANCE_S = 300
_PAID_STATUSES = frozenset({"paid", "no_payment_required"})
_CHECKOUT_EVENTS = frozenset(
    {"checkout.session.completed", "checkout.session.async_payment_succeeded"}
)
# « created » est ignoré : il peut arriver après l'activation avec un statut provisoire.
_SUBSCRIPTION_EVENTS = frozenset({"customer.subscription.updated", "customer.subscription.deleted"})
_INVOICE_EVENTS = frozenset({"invoice.paid"})
_REFUND_EVENTS = frozenset({"charge.refunded"})
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


class AlreadyUnlockedError(Exception):
    """L'adresse est déjà ouverte à cet utilisateur : rien à lui revendre."""


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
    address_id: str | None = None,
    grant_address: bool = True,
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
    # `grant_address` faux : le retour ramène bien à l'adresse, mais l'achat ne la débloque pas
    # (elle l'est déjà) ; un pack crédite alors ses dix audits.
    if target is not None and grant_address:
        params["metadata[lat]"] = str(target.lat)
        params["metadata[lon]"] = str(target.lon)
        params["metadata[label]"] = target.label[:_MAX_LABEL_LENGTH]
        if address_id:
            params["metadata[ban_id]"] = address_id
    if offer.mode == "payment":
        # Reportées sur le paiement lui-même : un remboursement désigne ainsi ce qu'il annule.
        for key in ("user_id", "offer", "lat", "lon", "ban_id"):
            if f"metadata[{key}]" in params:
                params[f"payment_intent_data[metadata][{key}]"] = params[f"metadata[{key}]"]
        # Une facture est émise pour chaque achat : son paiement déclenche l'envoi du reçu.
        params["invoice_creation[enabled]"] = "true"
        params["invoice_creation[invoice_data][description]"] = offer.name
        if target is not None:
            params["invoice_creation[invoice_data][metadata][label]"] = target.label[
                :_MAX_LABEL_LENGTH
            ]
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
        geocoder: Geocoder,
        secret_key: str | None,
        webhook_secret: str | None,
        api_url: str,
        site_url: str,
        pro_tax_rate_id: str | None = None,
        mailer: Mailer | None = None,
    ) -> None:
        self._http = http
        self._repository = repository
        self._geocoder = geocoder
        self._secret_key = secret_key
        self._webhook_secret = webhook_secret
        self._api_url = api_url.rstrip("/")
        self._site_url = site_url
        self._pro_tax_rate_id = pro_tax_rate_id
        self._mailer = mailer

    async def start_checkout(
        self, user: AuthenticatedUser, offer_id: str, target: CheckoutTarget | None
    ) -> str:
        """URL de la page de paiement Stripe pour cette offre."""
        if not self._secret_key:
            raise BillingNotConfiguredError
        offer = OFFERS[offer_id]
        account = await self._repository.account(user.id)
        if offer.mode == "subscription" and account["subscription_active"]:
            raise AlreadySubscribedError
        address_id = await self.address_id(target) if target else None
        # Le client ne paie pas deux fois ce qu'il a déjà : une adresse déjà ouverte, par un
        # achat ou par son abonnement, n'est ni revendue ni décomptée d'un pack.
        owned = target is not None and (
            account["subscription_active"]
            or await self._repository.is_entitled(user.id, target.lat, target.lon, address_id)
        )
        if owned and offer.id == "unit":
            raise AlreadyUnlockedError
        session = await self._http.post_form_json(
            "stripe",
            f"{self._api_url}/v1/checkout/sessions",
            data=checkout_params(
                offer,
                user,
                target,
                site_url=self._site_url,
                tax_rate_id=self._pro_tax_rate_id,
                address_id=address_id,
                grant_address=not owned,
            ),
            headers={"Authorization": f"Bearer {self._secret_key}"},
        )
        return _session_url(session)

    async def address_id(self, target: CheckoutTarget) -> str | None:
        """Identifiant BAN de l'adresse achetée, résolu ici et jamais repris du navigateur.

        Sans réponse du géocodeur, le droit reste attaché au seul point acheté.
        """
        try:
            location = await self._geocoder.reverse(target.lat, target.lon, target.ban_id)
        except SourceError:
            return None
        return location.adresse_id if location else None

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
        if event_type in _INVOICE_EVENTS:
            return await self._send_receipt(event_id, str(event_type), payload)
        if event_type in _REFUND_EVENTS:
            return await self._on_refund(event_id, str(event_type), payload)
        return "ignored"

    async def _on_refund(self, event_id: str, event_type: str, charge: dict[str, Any]) -> str:
        """Retire ce qu'un achat intégralement remboursé avait ouvert.

        Un remboursement partiel est un geste commercial : il ne retire rien. Pour un pack,
        l'adresse débloquée à l'achat et les crédits encore disponibles sont repris ; les
        adresses déjà débloquées avec des crédits restent acquises.
        """
        metadata = charge.get("metadata") or {}
        user_id, offer = metadata.get("user_id"), OFFERS.get(str(metadata.get("offer")))
        if not charge.get("refunded") or not isinstance(user_id, str) or offer is None:
            return "ignored"
        lat, lon = _coordinate(metadata.get("lat")), _coordinate(metadata.get("lon"))
        has_address = lat is not None and lon is not None
        credits = offer.extra_credits if has_address else (_PACK_SIZE if offer.id == "pack" else 0)
        applied = await self._repository.revoke_purchase(
            event_id=event_id,
            event_type=event_type,
            user_id=user_id,
            lat=lat if has_address else None,
            lon=lon if has_address else None,
            address_id=metadata.get("ban_id") if has_address else None,
            credits=credits,
        )
        return "refunded" if applied else "duplicate"

    async def cancel_subscription(self, user_id: str) -> None:
        """Arrête l'abonnement en cours, pour qu'un compte supprimé ne soit plus facturé."""
        subscription_id = await self._repository.subscription_id(user_id)
        if subscription_id is None or not self._secret_key:
            return
        try:
            await self._http.delete(
                "stripe",
                f"{self._api_url}/v1/subscriptions/{subscription_id}",
                headers={"Authorization": f"Bearer {self._secret_key}"},
            )
        except SourceError as exc:
            # Déjà résilié ou inconnu de Stripe : rien à arrêter.
            if exc.kind != "not_found":
                raise

    async def _send_receipt(self, event_id: str, event_type: str, invoice: dict[str, Any]) -> str:
        """Envoie le reçu d'une facture payée, une seule fois.

        Le message part avant que l'évènement soit noté comme traité : si l'envoi échoue,
        l'erreur remonte et Stripe représentera l'évènement plus tard.
        """
        if self._mailer is None:
            return "email_disabled"
        if await self._repository.is_recorded(event_id):
            return "duplicate"
        email = receipt_email(invoice, site_url=self._site_url)
        if email is None:
            return "ignored"
        await self._mailer.send(email)
        await self._repository.record_event(event_id, event_type)
        return "receipt_sent"

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
            address_id=metadata.get("ban_id") if has_address else None,
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
