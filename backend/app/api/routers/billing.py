"""Routes de paiement : compte, session de paiement, crédits, évènements Stripe."""

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.api.deps import (
    BillingRepositoryDep,
    BillingServiceDep,
    RequiredUserDep,
    enforce_rate_limit,
)
from app.core.errors import RepositoryError, SourceError
from app.services.billing import (
    AlreadySubscribedError,
    BillingNotConfiguredError,
    CheckoutTarget,
    InvalidSignatureError,
    NoSubscriptionError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["paiement"])

_NOT_CONFIGURED = "Le paiement en ligne n'est pas encore ouvert."
_BAN_ID_PATTERN = r"^$|^[0-9][0-9AB][0-9]{3}(_[0-9A-Za-z]{1,12}){0,3}$"


class Address(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    ban_id: str = Field(default="", max_length=64, pattern=_BAN_ID_PATTERN)
    label: str = Field(min_length=1, max_length=300)

    def to_target(self) -> CheckoutTarget:
        return CheckoutTarget(round(self.lat, 6), round(self.lon, 6), self.ban_id, self.label)


class CheckoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    offer: Literal["unit", "pack", "pro"]
    address: Address | None = None

    @model_validator(mode="after")
    def _unit_needs_an_address(self) -> "CheckoutRequest":
        if self.offer == "unit" and self.address is None:
            raise ValueError("l'offre à l'unité débloque une adresse précise")
        return self


class Account(BaseModel):
    email: str | None
    credits: int
    subscription_active: bool


@router.get("/account")
async def get_account(user: RequiredUserDep, repository: BillingRepositoryDep) -> Account:
    """Crédits restants et état de l'abonnement de l'utilisateur connecté."""
    try:
        account = await repository.account(user.id)
    except RepositoryError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Compte indisponible.") from exc
    return Account(email=user.email, **account)


@router.post("/checkout", dependencies=[Depends(enforce_rate_limit)])
async def create_checkout(
    body: CheckoutRequest, user: RequiredUserDep, billing: BillingServiceDep
) -> dict[str, str]:
    """Crée une session Stripe Checkout et renvoie l'adresse de la page de paiement."""
    target = body.address.to_target() if body.address else None
    try:
        return {"url": await billing.start_checkout(user, body.offer, target)}
    except AlreadySubscribedError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Votre abonnement Pro est déjà actif."
        ) from exc
    except (BillingNotConfiguredError, SourceError, RepositoryError) as exc:
        raise _payment_error(exc) from exc


@router.post("/billing/portal", dependencies=[Depends(enforce_rate_limit)])
async def open_billing_portal(user: RequiredUserDep, billing: BillingServiceDep) -> dict[str, str]:
    """Adresse du portail Stripe où l'abonné gère ou résilie son abonnement."""
    try:
        return {"url": await billing.portal_url(user)}
    except NoSubscriptionError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aucun abonnement à gérer.") from exc
    except (BillingNotConfiguredError, SourceError, RepositoryError) as exc:
        raise _payment_error(exc) from exc


def _payment_error(exc: Exception) -> HTTPException:
    if isinstance(exc, BillingNotConfiguredError):
        return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, _NOT_CONFIGURED)
    logger.warning("Appel au service de paiement impossible : %s", exc)
    return HTTPException(
        status.HTTP_502_BAD_GATEWAY, "Le service de paiement ne répond pas, réessayez."
    )


@router.post("/unlock", dependencies=[Depends(enforce_rate_limit)])
async def unlock_with_credit(
    body: Address, user: RequiredUserDep, repository: BillingRepositoryDep
) -> Account:
    """Débloque une adresse avec un crédit du Pack Investisseur."""
    target = body.to_target()
    try:
        unlocked = await repository.spend_credit(user.id, target.lat, target.lon, target.label)
        account = await repository.account(user.id)
    except RepositoryError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Compte indisponible.") from exc
    if not unlocked:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, "Aucun crédit disponible.")
    return Account(email=user.email, **account)


@router.post("/stripe/webhook", include_in_schema=False)
async def stripe_webhook(
    request: Request,
    billing: BillingServiceDep,
    stripe_signature: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    """Évènements envoyés par Stripe. Seule une signature valide est prise en compte."""
    payload = await request.body()
    try:
        event = billing.parse_event(payload, stripe_signature or "")
    except BillingNotConfiguredError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, _NOT_CONFIGURED) from exc
    except InvalidSignatureError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Signature invalide.") from exc
    try:
        outcome = await billing.handle_event(event)
    except RepositoryError as exc:
        # 500 : Stripe renverra l'évènement plus tard, rien n'est perdu.
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Traitement différé.") from exc
    logger.info("Évènement Stripe %s (%s) : %s", event.get("id"), event.get("type"), outcome)
    return {"status": outcome}
