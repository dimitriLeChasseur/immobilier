"""Point d'entrée FastAPI : cycle de vie des ressources partagées et montage des routes."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import aiohttp
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import account, audit, billing, communes, emails, health
from app.container import build_audit_service, build_billing_service, build_commune_service
from app.core.config import get_settings
from app.core.rate_limit import SlidingWindowRateLimiter
from app.repositories.billing import PostgresBillingRepository
from app.repositories.db import create_pool
from app.repositories.entitlements import PostgresEntitlementRepository


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    pool = await create_pool(settings.database_url.get_secret_value())
    session = aiohttp.ClientSession(
        headers={"User-Agent": settings.http_user_agent},
        connector=aiohttp.TCPConnector(limit=100, limit_per_host=20),
    )
    app.state.db_pool = pool
    app.state.audit_service = build_audit_service(settings, pool, session)
    app.state.entitlements = PostgresEntitlementRepository(pool)
    app.state.commune_service = build_commune_service(settings, pool, session)
    app.state.billing_repository = PostgresBillingRepository(pool)
    app.state.billing_service = build_billing_service(
        settings, app.state.billing_repository, session
    )
    app.state.rate_limiter = SlidingWindowRateLimiter(
        settings.rate_limit_requests, settings.rate_limit_window_s
    )
    try:
        yield
    finally:
        await session.close()
        await pool.close()


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    is_dev = settings.app_env != "production"
    app = FastAPI(
        title="Audit Immobilier API",
        version="0.2.0",
        lifespan=lifespan,
        docs_url="/api/docs" if is_dev else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if is_dev else None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.include_router(health.router)
    app.include_router(audit.router)
    app.include_router(billing.router)
    app.include_router(account.router)
    app.include_router(emails.router)
    app.include_router(communes.router)
    return app


app = create_app()
