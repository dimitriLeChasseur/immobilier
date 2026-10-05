"""Racine de composition : assemble les dépendances concrètes de l'application."""

from datetime import timedelta

import aiohttp
import asyncpg

from app.core.config import Settings
from app.core.http import HttpClient
from app.repositories.reference import PostgresReferenceRepository
from app.repositories.report_cache import PostgresReportCache
from app.services.audit_service import AuditPolicy, AuditService
from app.services.geocoding import BanGeocoder
from app.services.providers.apicarto import CadastreProvider, UrbanismeProvider
from app.services.providers.base import Provider
from app.services.providers.dpe import DpeProvider
from app.services.providers.dvf import DvfProvider
from app.services.providers.environment import AirQualityProvider, SunlightProvider
from app.services.providers.georisques import GeorisquesProvider
from app.services.providers.housing import (
    CondoChargesProvider,
    ConnectivityProvider,
    MobileNetworkProvider,
    NoiseProvider,
    RentalMarketProvider,
)
from app.services.providers.market import RentsProvider
from app.services.providers.poi import PoiProvider
from app.services.providers.reference import (
    CrimeProvider,
    PermitsProvider,
    PropertyTaxProvider,
    SchoolsProvider,
)


def build_audit_service(
    settings: Settings, pool: asyncpg.Pool, session: aiohttp.ClientSession
) -> AuditService:
    http = HttpClient(
        session,
        timeout_s=settings.http_timeout_s,
        failure_threshold=settings.breaker_failure_threshold,
        reset_after_s=settings.breaker_reset_after_s,
    )
    reference = PostgresReferenceRepository(pool)
    ors_key = settings.ors_api_key.get_secret_value() if settings.ors_api_key else None
    providers: list[Provider] = [
        GeorisquesProvider(http),
        CadastreProvider(http),
        UrbanismeProvider(http),
        DvfProvider(http),
        DpeProvider(http),
        PoiProvider(http, ors_api_key=ors_key),
        AirQualityProvider(http),
        SunlightProvider(http),
        RentsProvider(
            http,
            resource_id=settings.loyers_resource_id,
            millesime=settings.loyers_millesime,
        ),
        CrimeProvider(reference),
        PropertyTaxProvider(reference),
        SchoolsProvider(reference),
        PermitsProvider(reference),
        RentalMarketProvider(http, reference),
        ConnectivityProvider(reference),
        CondoChargesProvider(),
        MobileNetworkProvider(http),
        NoiseProvider(reference),
    ]
    return AuditService(
        geocoder=BanGeocoder(http),
        providers=providers,
        cache=PostgresReportCache(pool),
        policy=AuditPolicy(
            report_version=settings.report_version,
            cache_ttl=timedelta(hours=settings.cache_ttl_hours),
            cache_partial_ttl=timedelta(minutes=settings.cache_partial_ttl_minutes),
            provider_deadline_s=settings.provider_deadline_s,
        ),
    )
