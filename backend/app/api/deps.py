"""Dépendances FastAPI (injection par Depends)."""

import logging
import math
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status

from app.core.config import get_settings
from app.core.errors import RepositoryError
from app.core.rate_limit import SlidingWindowRateLimiter
from app.core.security import AuthenticatedUser, InvalidTokenError, decode_access_token
from app.repositories.billing import AccountRepository, BillingRepository
from app.repositories.entitlements import EntitlementRepository
from app.schemas.audit import Location
from app.services.accounts import AccountDeleter
from app.services.audit_service import AuditService
from app.services.billing import BillingService

logger = logging.getLogger(__name__)


def get_audit_service(request: Request) -> AuditService:
    service: AuditService = request.app.state.audit_service
    return service


def get_rate_limiter(request: Request) -> SlidingWindowRateLimiter:
    limiter: SlidingWindowRateLimiter = request.app.state.rate_limiter
    return limiter


def enforce_rate_limit(
    request: Request,
    limiter: Annotated[SlidingWindowRateLimiter, Depends(get_rate_limiter)],
) -> None:
    # Derrière Caddy, uvicorn (--proxy-headers) restitue l'adresse du client réel.
    client_ip = request.client.host if request.client else "unknown"
    retry_after = limiter.check(client_ip)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Trop de requêtes, réessayez dans un instant.",
            headers={"Retry-After": str(math.ceil(retry_after))},
        )


def get_entitlements(request: Request) -> EntitlementRepository:
    repository: EntitlementRepository = request.app.state.entitlements
    return repository


def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
) -> AuthenticatedUser | None:
    """Utilisateur connecté, ou None pour un visiteur anonyme.

    Un jeton présent mais invalide ou expiré est refusé (401) plutôt qu'ignoré : le client
    doit le renouveler, et non recevoir en silence la version restreinte.
    """
    if authorization is None:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _unauthorized()
    try:
        return decode_access_token(token, get_settings().supabase_jwt_secret.get_secret_value())
    except InvalidTokenError as exc:
        raise _unauthorized() from exc


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Session invalide ou expirée, reconnectez-vous.",
        headers={"WWW-Authenticate": "Bearer"},
    )


class AccessCheck:
    """Décide si le demandeur reçoit le rapport complet d'une localisation."""

    def __init__(self, user: AuthenticatedUser | None, entitlements: EntitlementRepository) -> None:
        self._user = user
        self._entitlements = entitlements

    async def allows(self, location: Location) -> bool:
        """Vrai si l'utilisateur a acheté l'audit de cette adresse (ou est abonné).

        Refus par défaut : sans utilisateur, sans droit, ou si la vérification échoue.
        """
        if self._user is None:
            return False
        try:
            allowed = await self._entitlements.has_access(
                self._user.id, location.lat, location.lon, location.adresse_id
            )
        except RepositoryError:
            logger.warning("Vérification des droits impossible : accès restreint par défaut")
            return False
        if allowed:
            await self._remember(location)
        return allowed

    async def _remember(self, location: Location) -> None:
        """Garde la trace du rapport complet servi ; un échec ici ne retire pas l'accès."""
        if self._user is None:
            return
        try:
            await self._entitlements.record_view(
                self._user.id, location.lat, location.lon, location.label, location.adresse_id
            )
        except RepositoryError:
            logger.warning("Historique des consultations indisponible")


def get_access_check(
    user: Annotated[AuthenticatedUser | None, Depends(get_current_user)],
    entitlements: Annotated[EntitlementRepository, Depends(get_entitlements)],
) -> AccessCheck:
    return AccessCheck(user, entitlements)


def require_user(
    user: Annotated[AuthenticatedUser | None, Depends(get_current_user)],
) -> AuthenticatedUser:
    if user is None:
        raise _unauthorized()
    return user


def get_billing_service(request: Request) -> BillingService:
    service: BillingService = request.app.state.billing_service
    return service


def get_account_repository(request: Request) -> AccountRepository:
    # Même dépôt que la facturation : crédits, abonnement, audits et marque blanche.
    repository: AccountRepository = request.app.state.billing_repository
    return repository


def get_account_deleter(request: Request) -> AccountDeleter:
    deleter: AccountDeleter = request.app.state.account_deleter
    return deleter


def get_billing_repository(request: Request) -> BillingRepository:
    repository: BillingRepository = request.app.state.billing_repository
    return repository


AuditServiceDep = Annotated[AuditService, Depends(get_audit_service)]
RequiredUserDep = Annotated[AuthenticatedUser, Depends(require_user)]
BillingServiceDep = Annotated[BillingService, Depends(get_billing_service)]
BillingRepositoryDep = Annotated[BillingRepository, Depends(get_billing_repository)]
AccountRepositoryDep = Annotated[AccountRepository, Depends(get_account_repository)]
AccountDeleterDep = Annotated[AccountDeleter, Depends(get_account_deleter)]
AccessCheckDep = Annotated[AccessCheck, Depends(get_access_check)]
