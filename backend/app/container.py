"""Racine de composition : assemble les dépendances concrètes de l'application."""

from datetime import timedelta

import aiohttp
import asyncpg
from pydantic import SecretStr

from app.core.config import Settings
from app.core.http import HttpClient
from app.repositories.billing import BillingRepository
from app.repositories.reference import PostgresReferenceRepository
from app.repositories.report_cache import PostgresReportCache, ReportCache
from app.services.audit_service import AuditPolicy, AuditService
from app.services.billing import BillingService
from app.services.communes import CommuneService, TabularRents
from app.services.geocoding import BanGeocoder
from app.services.providers.apicarto import CadastreProvider, UrbanismeProvider
from app.services.providers.base import Provider
from app.services.providers.building import BuildingProvider
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
from app.services.street import BanStreetResolver


def build_audit_service(
    settings: Settings,
    pool: asyncpg.Pool,
    session: aiohttp.ClientSession,
    cache: ReportCache | None = None,
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
        BuildingProvider(http),
        PoiProvider(http, repository=reference, ors_api_key=ors_key),
        AirQualityProvider(http),
        SunlightProvider(http),
        RentsProvider(
            http,
            resource_id=settings.loyers_resource_id,
            typology_resources={
                "t1_t2": settings.loyers_t1_t2_resource_id,
                "t3_plus": settings.loyers_t3_plus_resource_id,
                "maison": settings.loyers_maison_resource_id,
            },
            millesime=settings.loyers_millesime,
        ),
        CrimeProvider(reference),
        PropertyTaxProvider(reference),
        SchoolsProvider(reference),
        PermitsProvider(reference),
        RentalMarketProvider(http, reference, abc_resource_id=settings.zonage_abc_resource_id),
        ConnectivityProvider(reference),
        CondoChargesProvider(),
        MobileNetworkProvider(http),
        NoiseProvider(reference),
    ]
    return AuditService(
        geocoder=BanGeocoder(http),
        streets=BanStreetResolver(http),
        providers=providers,
        cache=cache or PostgresReportCache(pool),
        policy=AuditPolicy(
            report_version=settings.report_version,
            cache_ttl=timedelta(hours=settings.cache_ttl_hours),
            cache_partial_ttl=timedelta(minutes=settings.cache_partial_ttl_minutes),
            provider_deadline_s=settings.provider_deadline_s,
            # L'indice de l'air est celui du jour : il ne vaut pas sept jours.
            source_ttls={"qualite_air": timedelta(hours=settings.air_quality_ttl_hours)},
        ),
    )


def build_billing_service(
    settings: Settings, repository: BillingRepository, session: aiohttp.ClientSession
) -> BillingService:
    def secret(value: SecretStr | None) -> str | None:
        return value.get_secret_value() if value else None

    # Client dédié : son coupe-circuit est indépendant de ceux des sources d'audit.
    http = HttpClient(
        session,
        timeout_s=settings.http_timeout_s,
        failure_threshold=settings.breaker_failure_threshold,
        reset_after_s=settings.breaker_reset_after_s,
    )
    return BillingService(
        http=http,
        repository=repository,
        geocoder=BanGeocoder(http),
        secret_key=secret(settings.stripe_secret_key),
        webhook_secret=secret(settings.stripe_webhook_secret),
        api_url=settings.stripe_api_url,
        site_url=settings.site_url,
        pro_tax_rate_id=settings.stripe_pro_tax_rate_id,
    )


def build_commune_service(
    settings: Settings, pool: asyncpg.Pool, session: aiohttp.ClientSession
) -> CommuneService:
    http = HttpClient(
        session,
        timeout_s=settings.http_timeout_s,
        failure_threshold=settings.breaker_failure_threshold,
        reset_after_s=settings.breaker_reset_after_s,
    )
    return CommuneService(
        http, PostgresReferenceRepository(pool), TabularRents(http, rent_resources(settings))
    )


def rent_resources(settings: Settings) -> dict[str, str]:
    """Ressources de la carte des loyers, par type de bien."""
    return {
        "appartement": settings.loyers_resource_id,
        "t1_t2": settings.loyers_t1_t2_resource_id,
        "t3_plus": settings.loyers_t3_plus_resource_id,
        "maison": settings.loyers_maison_resource_id,
    }
