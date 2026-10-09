"""Espace client : audits débloqués et marque blanche des rapports (offre Pro)."""

import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.deps import (
    AccountDeleterDep,
    AccountRepositoryDep,
    BillingServiceDep,
    RequiredUserDep,
    enforce_rate_limit,
)
from app.core.errors import RepositoryError, SourceError
from app.repositories.billing import BrandingDetails
from app.services.accounts import AccountDeletionUnavailableError
from app.services.branding import InvalidLogoError, decode_logo, encode_logo

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/account", tags=["compte"], dependencies=[Depends(enforce_rate_limit)]
)

_MAX_AUDITS = 200
_MAX_HISTORY = 100
# Une URL « data: » en base64 pèse un tiers de plus que le fichier.
_MAX_LOGO_CHARS = 300_000
_UNAVAILABLE = "Compte indisponible."
_PRO_ONLY = "La marque blanche est réservée à l'offre Pro."


class UnlockedAudit(BaseModel):
    label: str | None
    lat: float
    lon: float
    ban_id: str | None
    origin: str
    granted_at: datetime


class BrandingFields(BaseModel):
    """Champs communs à la lecture et à l'écriture de la marque blanche."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    company: str = Field(min_length=1, max_length=80)
    # Couleur du bandeau et des titres, « #rrggbb ».
    color: Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")] | None = None
    phone: Annotated[str, Field(max_length=30, pattern=r"^[0-9+(). -]+$")] | None = None
    email: Annotated[str, Field(max_length=120, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")] | None = (
        None
    )
    website: Annotated[str, Field(max_length=120, pattern=r"^https?://[^\s]+$")] | None = None
    address: Annotated[str, Field(max_length=160)] | None = None

    @field_validator("color", "phone", "email", "website", "address", mode="before")
    @classmethod
    def _blank_is_unset(cls, value: object) -> object:
        """Un champ de formulaire laissé vide vaut « non renseigné »."""
        return None if isinstance(value, str) and not value.strip() else value

    def details(self) -> BrandingDetails:
        return BrandingDetails(
            color=self.color.lower() if self.color else None,
            phone=self.phone,
            email=self.email,
            website=self.website,
            address=self.address,
        )


class ViewedAudit(BaseModel):
    label: str | None
    lat: float
    lon: float
    ban_id: str | None
    viewed_at: datetime


class Branding(BrandingFields):
    # URL « data: » du logo, prête à être insérée dans le PDF ; None sans logo.
    logo: str | None = None


class BrandingUpdate(BrandingFields):
    logo: str | None = Field(default=None, max_length=_MAX_LOGO_CHARS)


def _unavailable(exc: RepositoryError) -> HTTPException:
    logger.warning("Espace client indisponible : %s", exc)
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, _UNAVAILABLE)


async def _require_subscription(user_id: str, repository: AccountRepositoryDep) -> None:
    account = await repository.account(user_id)
    if not account["subscription_active"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, _PRO_ONLY)


@router.get("/audits")
async def list_audits(
    user: RequiredUserDep, repository: AccountRepositoryDep
) -> list[UnlockedAudit]:
    """Adresses que l'utilisateur a débloquées, la plus récente d'abord."""
    try:
        rows = await repository.audits(user.id, _MAX_AUDITS)
    except RepositoryError as exc:
        raise _unavailable(exc) from exc
    return [UnlockedAudit(**row) for row in rows]


@router.get("/history")
async def list_history(
    user: RequiredUserDep, repository: AccountRepositoryDep
) -> list[ViewedAudit]:
    """Rapports complets consultés par l'utilisateur, le plus récent d'abord."""
    try:
        rows = await repository.history(user.id, _MAX_HISTORY)
    except RepositoryError as exc:
        raise _unavailable(exc) from exc
    return [ViewedAudit(**row) for row in rows]


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    user: RequiredUserDep, billing: BillingServiceDep, accounts: AccountDeleterDep
) -> Response:
    """Supprime le compte et tout ce qui lui est rattaché ; l'abonnement est arrêté d'abord."""
    try:
        await billing.cancel_subscription(user.id)
        await accounts.delete(user.id)
    except AccountDeletionUnavailableError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "La suppression en ligne n'est pas disponible : écrivez-nous.",
        ) from exc
    except (SourceError, RepositoryError) as exc:
        logger.warning("Suppression de compte impossible : %s", exc)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "La suppression a échoué, réessayez dans un instant."
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/branding")
async def get_branding(user: RequiredUserDep, repository: AccountRepositoryDep) -> Branding | None:
    """Marque blanche de l'abonné ; rien pour un compte sans abonnement actif."""
    try:
        account = await repository.account(user.id)
        row = await repository.branding(user.id) if account["subscription_active"] else None
    except RepositoryError as exc:
        raise _unavailable(exc) from exc
    if row is None:
        return None
    logo = encode_logo(bytes(row["logo"]), row["logo_type"]) if row["logo"] is not None else None
    fields = {name: row.get(name) for name in ("color", "phone", "email", "website", "address")}
    return Branding(company=row["company"], logo=logo, **fields)


@router.put("/branding")
async def set_branding(
    body: BrandingUpdate, user: RequiredUserDep, repository: AccountRepositoryDep
) -> Branding:
    """Enregistre le nom et le logo repris en tête des rapports PDF."""
    try:
        content, kind = decode_logo(body.logo) if body.logo else (None, None)
    except InvalidLogoError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    try:
        await _require_subscription(user.id, repository)
        await repository.set_branding(user.id, body.company, content, kind, body.details())
    except RepositoryError as exc:
        raise _unavailable(exc) from exc
    return Branding(**body.model_dump() | {"color": body.details().color})


@router.delete("/branding", status_code=status.HTTP_204_NO_CONTENT)
async def delete_branding(user: RequiredUserDep, repository: AccountRepositoryDep) -> Response:
    try:
        await repository.delete_branding(user.id)
    except RepositoryError as exc:
        raise _unavailable(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
