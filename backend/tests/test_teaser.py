"""Modèle « teaser » : masquage côté serveur et contrôle d'accès par jeton Supabase."""

import json
import time
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from typing import Any

import jwt
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
from app.core.config import get_settings
from app.core.errors import RepositoryError
from app.core.rate_limit import SlidingWindowRateLimiter
from app.core.security import InvalidTokenError, decode_access_token
from app.schemas.audit import AuditQuery, AuditReport, Location, ReportMeta, SourceResult
from app.services.audit_service import AuditEvent, DoneEvent, LocationEvent, SourceEvent
from app.services.teaser import LOCKED, mask_data, mask_report

USER_ID = "7c9e6679-7425-40de-944b-e07fc1f90ae7"
PARAMS = {"lat": 47.4706, "lon": -0.5517}
SOURCES = {
    "dvf": SourceResult(
        status="ok",
        data={
            "nb_ventes": 505,
            "rayon_m": 300,
            "prix_m2_median": 3859,
            "dispersion": {"min": 914, "q1": 3269, "q3": 4444, "max": 10000},
            "dernieres_ventes": [{"date": "2025-12-30", "prix": 170000, "prix_m2": 3864}],
        },
    ),
    "qualite_air": SourceResult(status="ok", data={"indice": 3, "qualificatif": "Dégradé"}),
    "reseau_mobile": SourceResult(
        status="ok", data={"nb_sites": 17, "operateurs": [{"nom": "Orange", "nb_sites": 8}]}
    ),
    "bruit": SourceResult(status="ok", data={"niveau_max_db": 70, "message": "Exposition forte"}),
    "cadastre": SourceResult(status="empty"),
}
REPORT = AuditReport(
    location=Location(
        lat=47.4706, lon=-0.5517, label="Angers", citycode="49007", adresse_id="49007_6120_00012"
    ),
    sources=SOURCES,
    meta=ReportMeta(
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        is_partial=False,
        report_version=5,
        duration_ms=5,
    ),
)
SENSITIVE = ("3859", "170000", "3864", "Orange", "Exposition forte", "4444")


def token(**overrides: Any) -> str:
    claims: dict[str, Any] = {
        "sub": USER_ID,
        "aud": "authenticated",
        "role": "authenticated",
        "email": "acheteur@example.com",
        "exp": int(time.time()) + 600,
    }
    claims.update(overrides)
    claims = {key: value for key, value in claims.items() if value is not None}
    return jwt.encode(claims, get_settings().supabase_jwt_secret.get_secret_value(), "HS256")


def bearer(value: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {value}"}


class FullService:
    source_names = list(SOURCES)

    async def get_report(self, query: AuditQuery) -> AuditReport:
        return REPORT

    async def stream(self, query: AuditQuery) -> AsyncIterator[AuditEvent]:
        yield LocationEvent(REPORT.location)
        for name, result in SOURCES.items():
            yield SourceEvent(name, result)
        yield DoneEvent(REPORT.meta)


class Entitlements:
    def __init__(
        self, granted: bool = False, broken: bool = False, usage: int | None = None
    ) -> None:
        self.granted, self.broken, self.usage = granted, broken, usage
        self.checked: list[tuple[str, float, float, str | None]] = []
        self.viewed: list[tuple[str, str]] = []

    async def has_access(
        self, user_id: str, lat: float, lon: float, address_id: str | None = None
    ) -> bool:
        self.checked.append((user_id, lat, lon, address_id))
        if self.broken:
            raise RepositoryError("down")
        return self.granted

    async def record_view(
        self, user_id: str, lat: float, lon: float, label: str, address_id: str | None
    ) -> None:
        self.viewed.append((user_id, label))

    async def subscription_usage(
        self, user_id: str, lat: float, lon: float, address_id: str | None = None
    ) -> int | None:
        return self.usage


def make_client(entitlements: Entitlements) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(audit.router)
    app.dependency_overrides[get_audit_service] = lambda: FullService()
    app.dependency_overrides[get_rate_limiter] = lambda: SlidingWindowRateLimiter(100, 60)
    app.dependency_overrides[get_anonymous_limiter] = lambda: SlidingWindowRateLimiter(100, 60)
    app.dependency_overrides[get_entitlements] = lambda: entitlements
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def entitlements() -> Entitlements:
    return Entitlements()


@pytest.fixture
def client(entitlements: Entitlements) -> Iterator[TestClient]:
    yield from make_client(entitlements)


def assert_teaser(body: dict[str, Any], raw: str) -> None:
    assert body["meta"]["access"] == "teaser"
    dvf = body["sources"]["dvf"]["data"]
    assert dvf["prix_m2_median"] == LOCKED
    assert dvf["dispersion"] == LOCKED
    assert dvf["dernieres_ventes"] == LOCKED
    assert body["sources"]["reseau_mobile"]["data"]["operateurs"] == LOCKED
    assert body["sources"]["bruit"]["data"] == {"niveau_max_db": LOCKED, "message": LOCKED}
    for value in SENSITIVE:
        assert value not in raw, f"{value} ne doit pas quitter le serveur"


def test_anonymous_visitor_gets_locked_values_and_clear_hooks(client: TestClient) -> None:
    response = client.get("/api/v1/audit", params=PARAMS)
    assert response.status_code == 200
    body = response.json()
    assert_teaser(body, response.text)
    # Accroches lisibles : elles prouvent que l'analyse a eu lieu.
    assert body["sources"]["dvf"]["data"]["nb_ventes"] == 505
    assert body["sources"]["qualite_air"]["data"] == {"indice": 3, "qualificatif": "Dégradé"}
    assert body["sources"]["reseau_mobile"]["data"]["nb_sites"] == 17
    assert body["location"]["label"] == "Angers"
    assert body["sources"]["cadastre"] == SOURCES["cadastre"].model_dump()


def test_logged_in_user_without_purchase_still_gets_the_teaser(
    client: TestClient, entitlements: Entitlements
) -> None:
    response = client.get("/api/v1/audit", params=PARAMS, headers=bearer(token()))
    assert_teaser(response.json(), response.text)
    # Le droit est vérifié sur l'adresse résolue par le serveur, pas sur un identifiant client.
    assert entitlements.checked == [(USER_ID, 47.4706, -0.5517, "49007_6120_00012")]


def test_buyer_of_this_address_gets_the_full_report() -> None:
    entitlements = Entitlements(granted=True)
    client = next(make_client(entitlements))
    body = client.get("/api/v1/audit", params=PARAMS, headers=bearer(token())).json()
    assert body["meta"]["access"] == "full"
    # Le rapport complet servi entre dans l'historique de l'utilisateur.
    assert entitlements.viewed == [(USER_ID, "Angers")]
    assert body["sources"]["dvf"]["data"]["prix_m2_median"] == 3859
    assert LOCKED not in json.dumps(body)


def test_a_teaser_view_leaves_no_trace_in_the_history(
    client: TestClient, entitlements: Entitlements
) -> None:
    client.get("/api/v1/audit", params=PARAMS, headers=bearer(token()))
    assert entitlements.viewed == []


def test_stream_is_masked_like_the_json_endpoint(client: TestClient) -> None:
    text = client.get("/api/v1/audit/stream", params=PARAMS).text
    assert '"access": "teaser"' in text
    assert LOCKED in text
    assert '"nb_ventes": 505' in text
    for value in SENSITIVE:
        assert value not in text


def test_stream_is_complete_for_a_buyer() -> None:
    client = next(make_client(Entitlements(granted=True)))
    text = client.get("/api/v1/audit/stream", params=PARAMS, headers=bearer(token())).text
    assert '"prix_m2_median": 3859' in text
    assert LOCKED not in text


def test_access_is_refused_by_default_when_the_check_fails() -> None:
    client = next(make_client(Entitlements(granted=True, broken=True)))
    response = client.get("/api/v1/audit", params=PARAMS, headers=bearer(token()))
    assert_teaser(response.json(), response.text)


@pytest.mark.parametrize(
    "header",
    [
        bearer("pas.un.jeton"),
        bearer(token(exp=int(time.time()) - 10)),
        bearer(token(aud="autre")),
        # La clé « anon » de Supabase : signée avec le bon secret, mais sans utilisateur.
        bearer(token(sub=None, role="anon", aud=None)),
        bearer(token(role="service_role")),
        {"Authorization": "Basic abc"},
        {"Authorization": "Bearer "},
    ],
)
def test_invalid_session_is_rejected_not_downgraded(
    client: TestClient, header: dict[str, str]
) -> None:
    response = client.get("/api/v1/audit", params=PARAMS, headers=header)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_token_signed_with_another_secret_is_rejected() -> None:
    forged = jwt.encode(
        {"sub": USER_ID, "aud": "authenticated", "role": "authenticated", "exp": time.time() + 60},
        "un-autre-secret",
        "HS256",
    )
    with pytest.raises(InvalidTokenError):
        decode_access_token(forged, "le-vrai-secret")

    unsigned = jwt.encode({"sub": USER_ID, "aud": "authenticated"}, "", algorithm="none")
    with pytest.raises(InvalidTokenError):
        decode_access_token(unsigned, "le-vrai-secret")


def test_masking_is_an_allowlist_new_fields_are_locked_by_default() -> None:
    masked = mask_data("dvf", {"nb_ventes": 12, "champ_ajoute_plus_tard": 99})
    assert masked == {"nb_ventes": 12, "champ_ajoute_plus_tard": LOCKED}
    assert mask_data("source_inconnue", {"a": 1, "b": [1, 2]}) == {"a": LOCKED, "b": LOCKED}


def test_nearby_counts_stay_visible_but_not_the_nearest_place() -> None:
    masked = mask_data(
        "proximite",
        {
            "rayon_m": 500,
            "categories": {
                "transports": {"nb": 35, "plus_proche": {"nom": "Ralliement", "distance_m": 33}},
                "sante": {"nb": 0, "plus_proche": None},
            },
        },
    )
    assert masked["categories"] == {
        "transports": {"nb": 35, "plus_proche": LOCKED},
        "sante": {"nb": 0, "plus_proche": LOCKED},
    }
    assert "Ralliement" not in json.dumps(masked)


def test_masking_does_not_alter_the_cached_report() -> None:
    mask_report(REPORT)
    assert REPORT.sources["dvf"].data is not None
    assert REPORT.sources["dvf"].data["prix_m2_median"] == 3859
    assert REPORT.meta.access == "full"


def test_commune_figures_published_on_commune_pages_are_not_masked() -> None:
    rents = {"loyer_m2": 12.4, "fourchette": {"bas": 10.1, "haut": 14.9}}
    assert mask_data("loyers", rents) == rents
    for source in ("taxe_fonciere", "delinquance", "connectivite"):
        assert mask_data(source, {"valeur": 1, "ajout": [2]}) == {"valeur": 1, "ajout": [2]}


def test_subscriber_over_the_daily_limit_is_stopped_not_downgraded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRO_DAILY_ADDRESS_LIMIT", "3")
    get_settings.cache_clear()
    try:
        entitlements = Entitlements(granted=True, usage=3)
        client = next(make_client(entitlements))
        response = client.get("/api/v1/audit", params=PARAMS, headers=bearer(token()))
        assert response.status_code == 429
        assert "plafond quotidien" in response.json()["detail"]
        assert entitlements.viewed == []
        stream = client.get("/api/v1/audit/stream", params=PARAMS, headers=bearer(token())).text
        assert "daily_limit_reached" in stream
        assert "3859" not in stream

        # Sous le plafond, ou pour une adresse achetée ou déjà comptée (usage None) : accès entier.
        for usage in (2, None):
            allowed = next(make_client(Entitlements(granted=True, usage=usage)))
            body = allowed.get("/api/v1/audit", params=PARAMS, headers=bearer(token())).json()
            assert body["meta"]["access"] == "full"
    finally:
        get_settings.cache_clear()


def test_demo_address_is_open_to_everyone_and_flagged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_ADDRESS_ID", "49007_6120_00012")
    get_settings.cache_clear()
    try:
        entitlements = Entitlements()
        client = next(make_client(entitlements))
        body = client.get("/api/v1/audit", params=PARAMS).json()
        assert body["meta"]["access"] == "demo"
        assert body["sources"]["dvf"]["data"]["prix_m2_median"] == 3859
        assert entitlements.checked == [] and entitlements.viewed == []
        stream = client.get("/api/v1/audit/stream", params=PARAMS).text
        assert '"access": "demo"' in stream
        assert LOCKED not in stream
    finally:
        get_settings.cache_clear()


def test_another_address_stays_masked_when_a_demo_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEMO_ADDRESS_ID", "75101_0001_00001")
    get_settings.cache_clear()
    try:
        client = next(make_client(Entitlements()))
        response = client.get("/api/v1/audit", params=PARAMS)
        assert_teaser(response.json(), response.text)
    finally:
        get_settings.cache_clear()
