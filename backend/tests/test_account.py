"""Espace client : audits débloqués et marque blanche réservée aux abonnés."""

import base64
from collections.abc import Iterator
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_account_repository, get_rate_limiter
from app.api.routers import account
from app.core.errors import RepositoryError
from app.core.rate_limit import SlidingWindowRateLimiter
from app.repositories.billing import BrandingDetails
from app.services.branding import MAX_LOGO_BYTES, InvalidLogoError, decode_logo, encode_logo

NO_DETAILS: dict[str, Any] = {
    "color": None,
    "phone": None,
    "email": None,
    "website": None,
    "address": None,
}
USER_ID = "3f0c1f0e-6f1d-4b1e-9d59-0a1c2b3d4e5f"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


def data_url(content: bytes, kind: str = "image/png") -> str:
    return f"data:{kind};base64,{base64.b64encode(content).decode()}"


def test_logo_is_accepted_from_its_real_content() -> None:
    assert decode_logo(data_url(PNG)) == (PNG, "image/png")
    assert decode_logo(data_url(JPEG, "image/jpeg")) == (JPEG, "image/jpeg")
    assert decode_logo(encode_logo(PNG, "image/png")) == (PNG, "image/png")


@pytest.mark.parametrize(
    "value",
    [
        "pas une url",
        data_url(b"<svg onload=alert(1)>", "image/svg+xml"),
        # Un script déguisé en PNG, puis un JPEG étiqueté PNG : l'étiquette ne fait pas foi.
        data_url(b"<script>alert(1)</script>"),
        data_url(JPEG, "image/png"),
        data_url(b""),
        data_url(b"\x89PNG\r\n\x1a\n" + b"\x00" * MAX_LOGO_BYTES),
        "data:image/png;base64,@@@",
    ],
)
def test_anything_else_is_refused(value: str) -> None:
    with pytest.raises(InvalidLogoError):
        decode_logo(value)


class Repository:
    def __init__(self, subscribed: bool = True, broken: bool = False) -> None:
        self.subscribed, self.broken = subscribed, broken
        self.stored: dict[str, Any] | None = None

    def _check(self) -> None:
        if self.broken:
            raise RepositoryError("down")

    async def account(self, user_id: str) -> dict[str, Any]:
        self._check()
        return {"credits": 0, "subscription_active": self.subscribed}

    async def audits(self, user_id: str, limit: int) -> list[dict[str, Any]]:
        self._check()
        assert user_id == USER_ID
        return [
            {
                "label": "10 Rue du Canal 49100 Angers",
                "lat": 47.4739,
                "lon": -0.55083,
                "ban_id": "49007_1350_00010",
                "origin": "unit",
                "granted_at": datetime(2026, 10, 6, tzinfo=UTC),
            }
        ]

    async def branding(self, user_id: str) -> dict[str, Any] | None:
        return self.stored

    async def set_branding(
        self,
        user_id: str,
        company: str,
        logo: bytes | None,
        logo_type: str | None,
        details: BrandingDetails,
    ) -> None:
        self.stored = {"company": company, "logo": logo, "logo_type": logo_type} | asdict(details)

    async def delete_branding(self, user_id: str) -> None:
        self.stored = None


def test_colour_and_contact_details_are_saved_and_blank_fields_ignored() -> None:
    repository = Repository()
    client = next(make_client(repository))
    body = {
        "company": "Cabinet Durand",
        "color": "#1E40AF",
        "phone": "02 41 00 00 00",
        "email": "contact@durand.example",
        "website": "https://durand.example",
        "address": "  ",
    }
    saved = client.put("/api/v1/account/branding", json=body, headers=AUTH)
    assert saved.status_code == 200
    expected = {
        "color": "#1e40af",
        "phone": "02 41 00 00 00",
        "email": "contact@durand.example",
        "website": "https://durand.example",
        "address": None,
    }
    assert saved.json() == {"company": "Cabinet Durand", "logo": None} | expected
    assert repository.stored is not None
    assert {key: repository.stored[key] for key in expected} == expected
    assert client.get("/api/v1/account/branding", headers=AUTH).json()["color"] == "#1e40af"


def token() -> str:
    claims = {
        "sub": USER_ID,
        "email": "a@example.org",
        "role": "authenticated",
        "aud": "authenticated",
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    return jwt.encode(claims, "test", algorithm="HS256")


AUTH = {"Authorization": f"Bearer {token()}"}


def make_client(repository: Repository) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(account.router)
    limiter = SlidingWindowRateLimiter(limit=30, window_s=60)
    app.dependency_overrides[get_account_repository] = lambda: repository
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    with TestClient(app) as client:
        yield client


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/v1/account/audits"),
        ("get", "/api/v1/account/branding"),
        ("put", "/api/v1/account/branding"),
        ("delete", "/api/v1/account/branding"),
    ],
)
def test_client_area_requires_a_session(method: str, path: str) -> None:
    client = next(make_client(Repository()))
    assert client.request(method, path, json={"company": "x"}).status_code == 401


def test_unlocked_audits_are_listed_with_what_is_needed_to_reopen_them() -> None:
    client = next(make_client(Repository()))
    response = client.get("/api/v1/account/audits", headers=AUTH)
    assert response.status_code == 200
    assert response.json() == [
        {
            "label": "10 Rue du Canal 49100 Angers",
            "lat": 47.4739,
            "lon": -0.55083,
            "ban_id": "49007_1350_00010",
            "origin": "unit",
            "granted_at": "2026-10-06T00:00:00Z",
        }
    ]
    down = next(make_client(Repository(broken=True)))
    assert down.get("/api/v1/account/audits", headers=AUTH).status_code == 503


def test_subscriber_saves_reads_and_removes_the_branding() -> None:
    repository = Repository()
    client = next(make_client(repository))
    assert client.get("/api/v1/account/branding", headers=AUTH).json() is None

    body = {"company": "  Cabinet Durand  ", "logo": data_url(PNG)}
    saved = client.put("/api/v1/account/branding", json=body, headers=AUTH)
    assert saved.status_code == 200
    assert (
        repository.stored
        == {
            "company": "Cabinet Durand",
            "logo": PNG,
            "logo_type": "image/png",
        }
        | NO_DETAILS
    )

    read = client.get("/api/v1/account/branding", headers=AUTH).json()
    assert read == {"company": "Cabinet Durand", "logo": data_url(PNG)} | NO_DETAILS

    without_logo = client.put(
        "/api/v1/account/branding", json={"company": "Cabinet Durand"}, headers=AUTH
    )
    assert without_logo.json() == {"company": "Cabinet Durand", "logo": None} | NO_DETAILS

    assert client.delete("/api/v1/account/branding", headers=AUTH).status_code == 204
    assert repository.stored is None


def test_branding_is_reserved_to_active_subscribers() -> None:
    repository = Repository(subscribed=False)
    repository.stored = {"company": "Ancien abonné", "logo": None, "logo_type": None} | NO_DETAILS
    client = next(make_client(repository))

    refused = client.put("/api/v1/account/branding", json={"company": "x"}, headers=AUTH)
    assert refused.status_code == 403
    # Abonnement terminé : la marque enregistrée n'est plus servie.
    assert client.get("/api/v1/account/branding", headers=AUTH).json() is None


@pytest.mark.parametrize(
    "body",
    [
        {"company": ""},
        {"company": "x" * 81},
        {"company": "ok", "logo": data_url(b"<script>alert(1)</script>")},
        {"company": "ok", "logo": data_url(JPEG, "image/png")},
        {"company": "ok", "logo": "x" * 400_000},
        {"company": "ok", "couleur": "#000"},
        {"company": "ok", "color": "rouge"},
        {"company": "ok", "color": "#12345"},
        {"company": "ok", "phone": "appelez-moi"},
        {"company": "ok", "email": "pas-une-adresse"},
        {"company": "ok", "website": "javascript:alert(1)"},
        {"company": "ok", "address": "x" * 161},
    ],
)
def test_invalid_branding_is_rejected_before_being_stored(body: dict[str, Any]) -> None:
    repository = Repository()
    client = next(make_client(repository))
    assert client.put("/api/v1/account/branding", json=body, headers=AUTH).status_code == 422
    assert repository.stored is None
