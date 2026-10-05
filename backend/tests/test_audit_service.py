"""Orchestrateur : statuts, cache, flux. Dépendances remplacées par des doublures."""

import asyncio
from datetime import timedelta
from typing import Any

import pytest

from app.core.config import Settings
from app.core.errors import LocationNotFoundError, NoDataError, RepositoryError, SourceError
from app.schemas.audit import AuditQuery, Location
from app.services.audit_service import (
    AuditPolicy,
    AuditService,
    DoneEvent,
    LocationEvent,
    SourceEvent,
)
from app.services.providers.base import AuditContext, Provider, ProviderData

QUERY = AuditQuery(lat=48.862725, lon=2.337589, ban_id="75101_8909_00008")
POLICY = AuditPolicy(
    report_version=1,
    cache_ttl=timedelta(days=7),
    cache_partial_ttl=timedelta(minutes=15),
    provider_deadline_s=0.05,
)


class FakeGeocoder:
    def __init__(self, found: bool = True) -> None:
        self.found = found
        self.calls = 0

    async def reverse(self, lat: float, lon: float, ban_id: str) -> Location | None:
        self.calls += 1
        if not self.found:
            return None
        return Location(lat=lat, lon=lon, label="8 Rue de Rivoli", citycode="75101", ban_id=ban_id)


class FakeProvider:
    def __init__(self, name: str, outcome: Any, delay: float = 0.0) -> None:
        self.name = name
        self._outcome = outcome
        self._delay = delay

    async def fetch(self, ctx: AuditContext) -> ProviderData:
        await asyncio.sleep(self._delay)
        if isinstance(self._outcome, Exception):
            raise self._outcome
        if isinstance(self._outcome, ProviderData):
            return self._outcome
        return ProviderData(data=self._outcome)


class MemoryCache:
    def __init__(self, broken: bool = False) -> None:
        self.entries: dict[tuple[float, float, str, int], dict[str, Any]] = {}
        self.ttls: list[timedelta] = []
        self.broken = broken

    async def get(
        self, lat: float, lon: float, ban_id: str, report_version: int
    ) -> dict[str, Any] | None:
        if self.broken:
            raise RepositoryError("down")
        return self.entries.get((lat, lon, ban_id, report_version))

    async def put(
        self, *, lat: float, lon: float, ban_id: str, report_version: int, **kw: Any
    ) -> None:
        if self.broken:
            raise RepositoryError("down")
        self.entries[(lat, lon, ban_id, report_version)] = kw["payload"]
        self.ttls.append(kw["ttl"])


def make_service(
    providers: list[Provider],
    cache: MemoryCache | None = None,
    geocoder: FakeGeocoder | None = None,
) -> AuditService:
    return AuditService(
        geocoder=geocoder or FakeGeocoder(),
        providers=providers,
        cache=cache or MemoryCache(),
        policy=POLICY,
    )


async def test_each_failure_mode_maps_to_a_status_without_breaking_the_report() -> None:
    service = make_service(
        [
            FakeProvider("ok", {"valeur": 1}),
            FakeProvider("partielle", ProviderData(data={"a": 1}, missing=("b",))),
            FakeProvider("vide", NoDataError()),
            FakeProvider("lente", {"valeur": 1}, delay=1.0),
            FakeProvider("timeout_http", SourceError("timeout")),
            FakeProvider("coupee", SourceError("circuit_open")),
            FakeProvider("erreur_500", SourceError("http_error", "500")),
            FakeProvider("bug_parsing", KeyError("champ")),
        ]
    )

    report = await service.get_report(QUERY)

    statuses = {name: result.status for name, result in report.sources.items()}
    assert statuses == {
        "ok": "ok",
        "partielle": "partial",
        "vide": "empty",
        "lente": "timeout",
        "timeout_http": "timeout",
        "coupee": "unavailable",
        "erreur_500": "error",
        "bug_parsing": "error",
    }
    assert report.sources["partielle"].missing == ["b"]
    assert report.sources["erreur_500"].error == "La source a renvoyé une erreur."
    assert "500" not in str(report.sources["erreur_500"].error)
    assert report.meta.is_partial
    assert report.meta.failed_sources == [
        "partielle",
        "lente",
        "timeout_http",
        "coupee",
        "erreur_500",
        "bug_parsing",
    ]


async def test_complete_report_is_cached_and_second_call_skips_the_pipeline() -> None:
    cache, geocoder = MemoryCache(), FakeGeocoder()
    service = make_service(
        [FakeProvider("a", {"x": 1}), FakeProvider("b", NoDataError())], cache, geocoder
    )

    first = await service.get_report(QUERY)
    second = await service.get_report(QUERY)

    assert not first.meta.cached
    assert not first.meta.is_partial
    assert first.meta.failed_sources == []
    assert cache.ttls == [timedelta(days=7)]
    assert second.meta.cached
    assert second.sources == first.sources
    assert geocoder.calls == 1


async def test_partial_report_gets_short_ttl() -> None:
    cache = MemoryCache()
    service = make_service([FakeProvider("a", SourceError("timeout"))], cache)
    await service.get_report(QUERY)
    assert cache.ttls == [timedelta(minutes=15)]


async def test_cache_outage_does_not_block_the_audit() -> None:
    service = make_service([FakeProvider("a", {"x": 1})], MemoryCache(broken=True))
    report = await service.get_report(QUERY)
    assert report.sources["a"].status == "ok"


async def test_unknown_location_raises() -> None:
    service = make_service([FakeProvider("a", {"x": 1})], geocoder=FakeGeocoder(found=False))
    with pytest.raises(LocationNotFoundError):
        await service.get_report(QUERY)


async def test_stream_yields_sources_as_they_complete() -> None:
    service = make_service(
        [FakeProvider("lente", {"x": 1}, delay=0.03), FakeProvider("rapide", {"x": 2})]
    )

    events = [event async for event in service.stream(QUERY)]

    assert isinstance(events[0], LocationEvent)
    assert [event.name for event in events if isinstance(event, SourceEvent)] == ["rapide", "lente"]
    assert isinstance(events[-1], DoneEvent)


async def test_hanging_source_cannot_block_the_report() -> None:
    """Une source qui ne répond jamais est coupée au garde-fou : le rapport sort quand même."""

    class Hanging:
        name = "isochrones"

        async def fetch(self, ctx: AuditContext) -> ProviderData:
            await asyncio.Event().wait()
            raise AssertionError("inatteignable")

    service = make_service([Hanging(), FakeProvider("dvf", {"prix": 1})])

    report = await asyncio.wait_for(service.get_report(QUERY), timeout=2)

    assert report.sources["isochrones"].status == "timeout"
    assert report.sources["dvf"].status == "ok"
    assert report.meta.is_partial
    assert report.meta.failed_sources == ["isochrones"]


def test_default_timeouts_leave_room_for_slow_public_apis() -> None:
    settings = Settings(database_url="postgresql://u:p@h/d", supabase_jwt_secret="s")  # noqa: S106
    assert 8 <= settings.http_timeout_s <= 10
    assert settings.provider_deadline_s >= 2 * settings.http_timeout_s
