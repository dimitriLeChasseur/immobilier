"""Orchestration de l'audit : cache, géocodage, exécution concurrente des sources."""

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.core.errors import LocationNotFoundError, NoDataError, RepositoryError, SourceError
from app.repositories.report_cache import ReportCache
from app.schemas.audit import (
    FAILED_STATUSES,
    AuditQuery,
    AuditReport,
    Location,
    ReportMeta,
    SourceResult,
    SourceStatus,
    StreetInfo,
)
from app.services.geocoding import Geocoder
from app.services.providers.base import AuditContext, Provider
from app.services.street import Street, StreetResolver

logger = logging.getLogger(__name__)

_STATUS_BY_ERROR_KIND: dict[str, SourceStatus] = {
    "timeout": "timeout",
    "circuit_open": "unavailable",
}
# Erreurs de programmation probables face à une réponse de forme inattendue.
_PARSING_ERRORS = (KeyError, TypeError, ValueError, AttributeError, IndexError)


@dataclass(frozen=True, slots=True)
class LocationEvent:
    location: Location


@dataclass(frozen=True, slots=True)
class SourceEvent:
    name: str
    result: SourceResult


@dataclass(frozen=True, slots=True)
class DoneEvent:
    meta: ReportMeta


AuditEvent = LocationEvent | SourceEvent | DoneEvent


@dataclass(frozen=True, slots=True)
class AuditPolicy:
    report_version: int
    cache_ttl: timedelta
    cache_partial_ttl: timedelta
    provider_deadline_s: float


_MAP_POINTS = 60


def _street_location(location: Location, street: Street) -> Location:
    """Localisation d'une voie : son nom remplace l'adresse la plus proche du point."""
    place = " ".join(part for part in (location.postcode, location.city) if part)
    return location.model_copy(
        update={
            "label": f"{street.name} {place}".strip(),
            "rue": StreetInfo(
                id=street.id,
                nom=street.name,
                nb_numeros=len(street.points),
                longueur_m=street.length_m,
                points=street.sample(_MAP_POINTS),
            ),
        }
    )


class AuditService:
    def __init__(
        self,
        *,
        geocoder: Geocoder,
        streets: StreetResolver | None = None,
        providers: Sequence[Provider],
        cache: ReportCache,
        policy: AuditPolicy,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._geocoder = geocoder
        self._streets = streets
        self._providers = tuple(providers)
        self._cache = cache
        self._policy = policy
        self._monotonic = monotonic

    @property
    def source_names(self) -> list[str]:
        return [provider.name for provider in self._providers]

    async def get_report(self, query: AuditQuery) -> AuditReport:
        """Rapport consolidé (attend la fin de toutes les sources)."""
        location: Location | None = None
        sources: dict[str, SourceResult] = {}
        meta: ReportMeta | None = None
        async for event in self.stream(query):
            if isinstance(event, LocationEvent):
                location = event.location
            elif isinstance(event, SourceEvent):
                sources[event.name] = event.result
            else:
                meta = event.meta
        if location is None or meta is None:
            raise RuntimeError("audit stream ended without location or meta")
        ordered = {name: sources[name] for name in self.source_names if name in sources}
        return AuditReport(location=location, sources=ordered, meta=meta)

    async def stream(self, query: AuditQuery) -> AsyncIterator[AuditEvent]:
        """Émet la localisation, puis chaque source dès qu'elle répond, puis les métadonnées."""
        started = self._monotonic()
        cached = await self._read_cache(query)
        if cached is not None:
            yield LocationEvent(cached.location)
            for name, result in cached.sources.items():
                yield SourceEvent(name, result)
            yield DoneEvent(
                cached.meta.model_copy(
                    update={"cached": True, "duration_ms": self._elapsed_ms(started)}
                )
            )
            return

        location = await self._geocoder.reverse(query.lat, query.lon, query.ban_id)
        if location is None:
            raise LocationNotFoundError
        street = await self._resolve_street(query)
        if street is not None:
            location = _street_location(location, street)
        yield LocationEvent(location)

        context = AuditContext(
            lat=location.lat,
            lon=location.lon,
            citycode=location.citycode,
            postcode=location.postcode,
            region=location.region,
            street=street,
        )
        sources: dict[str, SourceResult] = {}
        tasks = [asyncio.create_task(self._run_provider(p, context)) for p in self._providers]
        try:
            for completed in asyncio.as_completed(tasks):
                name, result = await completed
                sources[name] = result
                yield SourceEvent(name, result)
        finally:
            # Client déconnecté en cours de flux : on n'achève pas les appels restants.
            for task in tasks:
                task.cancel()

        failed = [
            name
            for name in self.source_names
            if name in sources and sources[name].status in FAILED_STATUSES
        ]
        if failed:
            logger.warning(
                "Rapport partiel pour %s : %d source(s) en échec (%s)",
                location.citycode,
                len(failed),
                ", ".join(failed),
            )
        meta = ReportMeta(
            generated_at=datetime.now(UTC),
            is_partial=bool(failed),
            failed_sources=failed,
            report_version=self._policy.report_version,
            duration_ms=self._elapsed_ms(started),
        )
        await self._write_cache(query, AuditReport(location=location, sources=sources, meta=meta))
        yield DoneEvent(meta)

    async def _resolve_street(self, query: AuditQuery) -> Street | None:
        if self._streets is None:
            return None
        return await self._streets.resolve(query.ban_id, query.lat, query.lon)

    def _elapsed_ms(self, started: float) -> int:
        return round((self._monotonic() - started) * 1000)

    async def _run_provider(
        self, provider: Provider, context: AuditContext
    ) -> tuple[str, SourceResult]:
        started = self._monotonic()
        try:
            async with asyncio.timeout(self._policy.provider_deadline_s):
                output = await provider.fetch(context)
            if output.missing:
                logger.warning(
                    "Source %s partielle, sans réponse : %s", provider.name, output.missing
                )
            result = SourceResult(
                status="partial" if output.missing else "ok",
                data=output.data,
                missing=list(output.missing),
            )
        except NoDataError:
            result = SourceResult(status="empty")
        except TimeoutError:
            result = SourceResult(status="timeout", error=SourceError("timeout").public_message)
        except SourceError as exc:
            logger.warning("Source %s en échec : %s", provider.name, exc)
            result = SourceResult(
                status=_STATUS_BY_ERROR_KIND.get(exc.kind, "error"), error=exc.public_message
            )
        except _PARSING_ERRORS:
            logger.exception("Réponse inattendue de la source %s", provider.name)
            result = SourceResult(
                status="error", error=SourceError("invalid_response").public_message
            )
        result.duration_ms = self._elapsed_ms(started)
        return provider.name, result

    async def _read_cache(self, query: AuditQuery) -> AuditReport | None:
        """Le cache est une optimisation : son indisponibilité ne bloque pas l'audit."""
        try:
            payload = await self._cache.get(
                query.lat, query.lon, query.ban_id, self._policy.report_version
            )
        except RepositoryError:
            logger.warning("Cache des rapports indisponible en lecture")
            return None
        if payload is None:
            return None
        try:
            return AuditReport.model_validate(payload)
        except ValueError:
            logger.warning("Entrée de cache illisible, ignorée")
            return None

    async def _write_cache(self, query: AuditQuery, report: AuditReport) -> None:
        ttl = self._policy.cache_partial_ttl if report.meta.is_partial else self._policy.cache_ttl
        try:
            await self._cache.put(
                lat=query.lat,
                lon=query.lon,
                ban_id=query.ban_id,
                report_version=self._policy.report_version,
                citycode=report.location.citycode,
                label=report.location.label,
                payload=report.model_dump(mode="json"),
                is_partial=report.meta.is_partial,
                ttl=ttl,
            )
        except RepositoryError:
            logger.warning("Cache des rapports indisponible en écriture")
