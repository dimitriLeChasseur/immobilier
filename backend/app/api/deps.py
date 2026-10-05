"""Dépendances FastAPI (injection par Depends)."""

import math
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from app.core.rate_limit import SlidingWindowRateLimiter
from app.services.audit_service import AuditService


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


AuditServiceDep = Annotated[AuditService, Depends(get_audit_service)]
