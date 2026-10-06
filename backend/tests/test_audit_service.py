"""Orchestrateur : statuts, cache, flux. Dépendances remplacées par des doublures."""

import asyncio
from datetime import UTC, datetime, timedelta
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
from app.services.street import Street

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


class CountingProvider:
    """Source dont le résultat change à chaque appel, pour repérer les réinterrogations."""

    def __init__(self, name: str, outcomes: list[Any]) -> None:
        self.name = name
        self._outcomes = outcomes
        self.calls = 0

    async def fetch(self, ctx: AuditContext) -> ProviderData:
        outcome = self._outcomes[min(self.calls, len(self._outcomes) - 1)]
        self.calls += 1
        if isinstance(outcome, Exception):
            raise outcome
        return ProviderData(data=outcome)


def age_cache(cache: MemoryCache, source: str, age: timedelta) -> None:
    """Vieillit une source du rapport en cache, comme si le temps avait passé."""
    payload = next(iter(cache.entries.values()))
    payload["sources"][source]["fetched_at"] = (datetime.now(UTC) - age).isoformat()


async def test_only_the_failed_source_is_fetched_again_once_its_retry_delay_has_passed() -> None:
    cache = MemoryCache()
    healthy = CountingProvider("saine", [{"x": 1}])
    flaky = CountingProvider("fragile", [SourceError("timeout"), {"y": 2}])
    geocoder = FakeGeocoder()
    service = make_service([healthy, flaky], cache, geocoder)

    first = await service.get_report(QUERY)
    assert first.meta.is_partial
    # L'entrée vit la durée longue : la fraîcheur se juge source par source.
    assert cache.ttls == [timedelta(days=7)]

    # Dans le quart d'heure : rien n'est rejoué, pour ne pas marteler une source en panne.
    soon = await service.get_report(QUERY)
    assert soon.meta.cached and soon.meta.is_partial
    assert (healthy.calls, flaky.calls) == (1, 1)

    age_cache(cache, "fragile", timedelta(minutes=16))
    repaired = await service.get_report(QUERY)
    assert (healthy.calls, flaky.calls) == (1, 2)
    assert repaired.sources["fragile"].data == {"y": 2}
    assert repaired.sources["saine"] == first.sources["saine"]
    assert not repaired.meta.is_partial
    assert not repaired.meta.cached
    assert geocoder.calls == 1
    assert list(repaired.sources) == ["saine", "fragile"]

    again = await service.get_report(QUERY)
    assert again.meta.cached
    assert flaky.calls == 2


async def test_each_source_expires_on_its_own_schedule() -> None:
    cache = MemoryCache()
    air = CountingProvider("qualite_air", [{"indice": 3}, {"indice": 1}])
    prices = CountingProvider("dvf", [{"prix": 3750}])
    policy = AuditPolicy(
        report_version=1,
        cache_ttl=timedelta(days=7),
        cache_partial_ttl=timedelta(minutes=15),
        provider_deadline_s=0.05,
        source_ttls={"qualite_air": timedelta(hours=12)},
    )
    service = AuditService(
        geocoder=FakeGeocoder(), providers=[prices, air], cache=cache, policy=policy
    )
    await service.get_report(QUERY)
    age_cache(cache, "qualite_air", timedelta(hours=13))
    age_cache(cache, "dvf", timedelta(hours=13))

    report = await service.get_report(QUERY)
    assert (prices.calls, air.calls) == (1, 2)
    assert report.sources["qualite_air"].data == {"indice": 1}

    age_cache(cache, "dvf", timedelta(days=8))
    await service.get_report(QUERY)
    assert prices.calls == 2


async def test_entries_cached_before_per_source_dates_use_the_report_date() -> None:
    cache = MemoryCache()
    provider = CountingProvider("a", [{"x": 1}])
    service = make_service([provider], cache)
    await service.get_report(QUERY)
    payload = next(iter(cache.entries.values()))
    del payload["sources"]["a"]["fetched_at"]

    await service.get_report(QUERY)
    assert provider.calls == 1
    payload["meta"]["generated_at"] = (datetime.now(UTC) - timedelta(days=8)).isoformat()
    await service.get_report(QUERY)
    assert provider.calls == 2


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


class FakeStreets:
    async def resolve(self, ban_id: str, lat: float, lon: float) -> Street | None:
        if ban_id != "49007_7050":
            return None
        return Street(
            id=ban_id, name="Rue Saint-Aubin", points=((-0.554, 47.4699), (-0.551, 47.4678))
        )


class ContextProbe:
    name = "sonde"

    def __init__(self) -> None:
        self.contexts: list[AuditContext] = []

    async def fetch(self, ctx: AuditContext) -> ProviderData:
        self.contexts.append(ctx)
        return ProviderData(data={})


async def test_street_identifier_switches_the_audit_to_street_mode() -> None:
    probe = ContextProbe()
    service = AuditService(
        geocoder=FakeGeocoder(),
        streets=FakeStreets(),
        providers=[probe],
        cache=MemoryCache(),
        policy=POLICY,
    )
    street = await service.get_report(AuditQuery(lat=47.469, lon=-0.5529, ban_id="49007_7050"))
    assert street.location.label == "Rue Saint-Aubin"
    assert street.location.rue is not None
    assert street.location.rue.nb_numeros == 2
    assert probe.contexts[0].street is not None

    address = await service.get_report(AuditQuery(lat=47.47, lon=-0.55, ban_id="49007_7050_00012"))
    assert address.location.rue is None
    assert address.location.label == "8 Rue de Rivoli"
    assert probe.contexts[1].street is None
