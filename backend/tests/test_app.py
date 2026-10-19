"""Point d'entrée de l'API : sondes de santé, documentation selon l'environnement, cycle de vie.

La sonde de disponibilité est celle qu'interroge le script de déploiement : elle doit dire
« prête » quand la base répond, et 503 sinon, sans rien révéler du serveur.
"""

from collections.abc import Iterator

import asyncpg
import pytest
from fastapi.testclient import TestClient

import app.main
from app.core.config import get_settings
from app.main import create_app


class FakePool:
    """Pool PostgreSQL réduit à ce que l'API touche hors des requêtes métier."""

    def __init__(self, failure: Exception | None = None) -> None:
        self.failure = failure
        self.closed = False

    async def fetchval(self, query: str) -> str:
        if self.failure is not None:
            raise self.failure
        return "3.5 USE_GEOS=1"

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
def environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[pytest.MonkeyPatch]:
    get_settings.cache_clear()
    yield monkeypatch
    get_settings.cache_clear()


def client_with_pool(pool: FakePool) -> TestClient:
    application = create_app()
    application.state.db_pool = pool
    return TestClient(application)


def test_liveness_probe_answers_without_touching_the_database() -> None:
    response = client_with_pool(FakePool(OSError("base injoignable"))).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_probe_is_ready_when_postgis_answers() -> None:
    response = client_with_pool(FakePool()).get("/api/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


@pytest.mark.parametrize(
    "failure",
    [asyncpg.PostgresError("extension absente"), OSError("connexion refusée")],
    ids=["erreur PostgreSQL", "base injoignable"],
)
def test_readiness_probe_reports_an_unavailable_database_without_details(
    failure: Exception,
) -> None:
    response = client_with_pool(FakePool(failure)).get("/api/health/ready")
    assert response.status_code == 503
    assert response.json() == {"detail": "database unavailable"}
    assert "3.5" not in response.text


def test_api_documentation_is_hidden_in_production(environment: pytest.MonkeyPatch) -> None:
    environment.setenv("APP_ENV", "production")
    client = client_with_pool(FakePool())
    assert client.get("/api/docs").status_code == 404
    assert client.get("/api/openapi.json").status_code == 404


def test_api_documentation_is_served_in_development(environment: pytest.MonkeyPatch) -> None:
    environment.setenv("APP_ENV", "development")
    client = client_with_pool(FakePool())
    assert client.get("/api/docs").status_code == 200
    assert "/api/health/ready" in client.get("/api/openapi.json").json()["paths"]


def test_only_configured_origins_may_call_the_api(environment: pytest.MonkeyPatch) -> None:
    environment.setenv("CORS_ALLOWED_ORIGINS", "https://audit-immobilier.fr")
    client = client_with_pool(FakePool())
    allowed = client.get("/health", headers={"Origin": "https://audit-immobilier.fr"})
    foreign = client.get("/health", headers={"Origin": "https://ailleurs.example"})
    assert allowed.headers["access-control-allow-origin"] == "https://audit-immobilier.fr"
    assert "access-control-allow-origin" not in foreign.headers


def test_startup_opens_shared_resources_and_shutdown_releases_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = FakePool()

    async def create_pool(dsn: str) -> FakePool:
        return pool

    monkeypatch.setattr(app.main, "create_pool", create_pool)
    application = create_app()
    with TestClient(application) as client:
        assert client.get("/api/health/ready").json() == {"status": "ready"}
        assert not pool.closed
    assert pool.closed
