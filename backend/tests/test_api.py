"""Couche HTTP : validation des entrées, codes de retour, limitation de débit, SSE."""

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import (
    get_anonymous_limiter,
    get_audit_service,
    get_entitlements,
    get_rate_limiter,
)
from app.api.routers import audit
from app.core.errors import LocationNotFoundError
from app.core.rate_limit import SlidingWindowRateLimiter
from app.schemas.audit import AuditQuery, AuditReport, Location, ReportMeta, SourceResult
from app.services.audit_service import AuditEvent, DoneEvent, LocationEvent, SourceEvent

LOCATION = Location(lat=48.86, lon=2.33, label="Paris", citycode="75101")
META = ReportMeta(
    generated_at=datetime(2026, 1, 1, tzinfo=UTC), is_partial=False, report_version=1, duration_ms=5
)


class NoEntitlements:
    async def has_access(
        self, user_id: str, lat: float, lon: float, address_id: str | None = None
    ) -> bool:
        return False


class StubService:
    source_names = ["dvf"]

    def __init__(self) -> None:
        self.queries: list[AuditQuery] = []

    async def get_report(self, query: AuditQuery) -> AuditReport:
        self.queries.append(query)
        if query.lat == 0:
            raise LocationNotFoundError
        return AuditReport(
            location=LOCATION, sources={"dvf": SourceResult(status="empty")}, meta=META
        )

    async def stream(self, query: AuditQuery) -> AsyncIterator[AuditEvent]:
        if query.lat == 0:
            raise LocationNotFoundError
        yield LocationEvent(LOCATION)
        yield SourceEvent("dvf", SourceResult(status="empty"))
        yield DoneEvent(META)


@pytest.fixture
def service() -> StubService:
    return StubService()


@pytest.fixture
def client(service: StubService) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(audit.router)
    limiter = SlidingWindowRateLimiter(limit=3, window_s=60)
    anonymous = SlidingWindowRateLimiter(limit=100, window_s=3600)
    app.dependency_overrides[get_audit_service] = lambda: service
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    app.dependency_overrides[get_anonymous_limiter] = lambda: anonymous
    app.dependency_overrides[get_entitlements] = lambda: NoEntitlements()
    with TestClient(app) as test_client:
        yield test_client


def test_audit_returns_consolidated_report(client: TestClient, service: StubService) -> None:
    response = client.get("/api/v1/audit", params={"lat": 48.8627251234, "lon": 2.337589})
    assert response.status_code == 200
    body = response.json()
    assert body["location"]["citycode"] == "75101"
    assert body["sources"]["dvf"]["status"] == "empty"
    assert service.queries[0].lat == 48.862725, "coordonnées arrondies à 6 décimales"


@pytest.mark.parametrize(
    "params",
    [
        {"lat": 91, "lon": 2.3},
        {"lat": 48.8, "lon": 181},
        {"lat": "abc", "lon": 2.3},
        {"lon": 2.3},
        {"lat": 48.8, "lon": 2.3, "ban_id": "75101'; DROP TABLE x;--"},
        {"lat": 48.8, "lon": 2.3, "ban_id": "x" * 65},
        {"lat": 48.8, "lon": 2.3, "inconnu": "1"},
    ],
)
def test_invalid_input_is_rejected(client: TestClient, params: dict[str, Any]) -> None:
    assert client.get("/api/v1/audit", params=params).status_code == 422


def test_unknown_location_is_404(client: TestClient) -> None:
    assert client.get("/api/v1/audit", params={"lat": 0, "lon": 0}).status_code == 404


def test_rate_limit_returns_429_with_retry_after(client: TestClient) -> None:
    params = {"lat": 48.8, "lon": 2.3}
    assert [client.get("/api/v1/audit", params=params).status_code for _ in range(3)] == [200] * 3
    blocked = client.get("/api/v1/audit", params=params)
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0


def test_stream_emits_sse_events_in_order(client: TestClient) -> None:
    response = client.get("/api/v1/audit/stream", params={"lat": 48.8, "lon": 2.3})
    assert response.headers["content-type"].startswith("text/event-stream")
    events = [line[7:] for line in response.text.splitlines() if line.startswith("event: ")]
    assert events == ["location", "source", "done"]


def test_stream_reports_unknown_location_as_error_event(client: TestClient) -> None:
    response = client.get("/api/v1/audit/stream", params={"lat": 0, "lon": 0})
    assert "event: error" in response.text
    assert "location_not_found" in response.text


def test_sources_lists_provider_names(client: TestClient) -> None:
    assert client.get("/api/v1/sources").json() == {"sources": ["dvf"]}


def test_anonymous_visitors_have_an_hourly_quota_of_audits(service: StubService) -> None:
    app = FastAPI()
    app.include_router(audit.router)
    app.dependency_overrides[get_audit_service] = lambda: service
    app.dependency_overrides[get_rate_limiter] = lambda: SlidingWindowRateLimiter(100, 60)
    hourly = SlidingWindowRateLimiter(limit=2, window_s=3600)
    app.dependency_overrides[get_anonymous_limiter] = lambda: hourly
    app.dependency_overrides[get_entitlements] = lambda: NoEntitlements()
    params = {"lat": 48.8, "lon": 2.3}
    with TestClient(app) as client:
        assert [client.get("/api/v1/audit", params=params).status_code for _ in range(2)] == [
            200,
            200,
        ]
        blocked = client.get("/api/v1/audit/stream", params=params)
    assert blocked.status_code == 429
    assert "créez un compte" in blocked.json()["detail"]
    assert int(blocked.headers["Retry-After"]) > 0
