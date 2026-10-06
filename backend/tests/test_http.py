"""Client HTTP contre un vrai serveur local : timeouts, codes d'erreur, circuit-breaker."""

import asyncio
from collections.abc import AsyncIterator

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from app.core.errors import SourceError
from app.core.http import HttpClient

BIG_PAYLOAD_ITEMS = 200_000


async def _ok(_: web.Request) -> web.Response:
    return web.json_response({"ok": True})


async def _big(_: web.Request) -> web.Response:
    return web.json_response({"items": list(range(BIG_PAYLOAD_ITEMS))})


async def _empty(_: web.Request) -> web.Response:
    return web.Response(status=200, body=b"")


async def _slow(_: web.Request) -> web.Response:
    await asyncio.sleep(1)
    return web.json_response({})


async def _status(request: web.Request) -> web.Response:
    return web.Response(status=int(request.match_info["code"]), text="<html>erreur</html>")


HITS: dict[str, int] = {}


async def _flaky(request: web.Request) -> web.Response:
    """Échoue en 502 à la première demande, répond ensuite."""
    HITS["flaky"] = HITS.get("flaky", 0) + 1
    if HITS["flaky"] == 1:
        return web.Response(status=502)
    return web.json_response({"essai": HITS["flaky"]})


async def _counted(request: web.Request) -> web.Response:
    key = request.match_info["key"]
    HITS[key] = HITS.get(key, 0) + 1
    if key == "lent":
        await asyncio.sleep(1)
    return web.Response(status=404 if key == "absent" else 503)


async def _html(_: web.Request) -> web.Response:
    return web.Response(text="<html>pas du JSON</html>")


@pytest.fixture
async def server() -> AsyncIterator[TestServer]:
    app = web.Application()
    app.add_routes(
        [
            web.get("/ok", _ok),
            web.get("/big", _big),
            web.get("/empty", _empty),
            web.get("/slow", _slow),
            web.get("/status/{code}", _status),
            web.get("/html", _html),
            web.get("/flaky", _flaky),
            web.post("/flaky", _flaky),
            web.get("/counted/{key}", _counted),
        ]
    )
    HITS.clear()
    test_server = TestServer(app)
    await test_server.start_server()
    try:
        yield test_server
    finally:
        await test_server.close()


@pytest.fixture
async def client() -> AsyncIterator[HttpClient]:
    async with aiohttp.ClientSession() as session:
        yield HttpClient(session, timeout_s=0.1, failure_threshold=2, reset_after_s=60)


async def test_reads_json_bodies_of_any_size(client: HttpClient, server: TestServer) -> None:
    assert await client.get_json("s", str(server.make_url("/ok"))) == {"ok": True}
    big = await client.get_json("s", str(server.make_url("/big")))
    assert len(big["items"]) == BIG_PAYLOAD_ITEMS
    assert await client.get_json("s", str(server.make_url("/empty"))) is None


@pytest.mark.parametrize(
    ("path", "kind"),
    [
        ("/slow", "timeout"),
        ("/status/404", "not_found"),
        ("/status/500", "http_error"),
        ("/status/429", "http_error"),
        ("/status/400", "http_error"),
        ("/html", "invalid_response"),
    ],
)
async def test_failures_become_typed_errors(
    client: HttpClient, server: TestServer, path: str, kind: str
) -> None:
    url = str(server.make_url(path))
    with pytest.raises(SourceError) as error:
        await client.get_json("s", url)
    assert error.value.kind == kind


async def test_connection_refused_is_an_http_error(client: HttpClient) -> None:
    with pytest.raises(SourceError) as error:
        await client.get_json("s", "http://127.0.0.1:1/")
    assert error.value.kind == "http_error"


async def test_breaker_opens_per_source_after_repeated_server_errors(
    client: HttpClient, server: TestServer
) -> None:
    failing = str(server.make_url("/status/500"))
    for _ in range(2):
        with pytest.raises(SourceError):
            await client.get_json("fragile", failing)

    healthy = str(server.make_url("/ok"))
    with pytest.raises(SourceError) as error:
        await client.get_json("fragile", healthy)
    assert error.value.kind == "circuit_open"
    assert await client.get_json("autre", healthy) == {"ok": True}


async def test_client_errors_do_not_trip_the_breaker(
    client: HttpClient, server: TestServer
) -> None:
    missing = str(server.make_url("/status/404"))
    for _ in range(5):
        with pytest.raises(SourceError):
            await client.get_json("s", missing)
    assert await client.get_json("s", str(server.make_url("/ok"))) == {"ok": True}


async def test_per_call_timeout_overrides_the_default(server: TestServer) -> None:
    async with aiohttp.ClientSession() as session:
        patient = HttpClient(session, timeout_s=5, failure_threshold=5, reset_after_s=60)
        url = str(server.make_url("/slow"))
        with pytest.raises(SourceError) as error:
            await patient._request("s", "GET", url, timeout_s=0.05)
        assert error.value.kind == "timeout"


async def test_a_brief_server_error_is_retried_once(client: HttpClient, server: TestServer) -> None:
    assert await client.get_json("flaky", str(server.make_url("/flaky"))) == {"essai": 2}
    # Le second essai a réussi : l'incident ne compte pas pour le coupe-circuit.
    HITS.clear()
    assert await client.get_json("flaky", str(server.make_url("/flaky"))) == {"essai": 2}


async def test_a_lasting_server_error_fails_after_exactly_two_attempts(
    client: HttpClient, server: TestServer
) -> None:
    with pytest.raises(SourceError) as error:
        await client.get_json("panne", str(server.make_url("/counted/panne")))
    assert error.value.kind == "http_error"
    assert HITS["panne"] == 2


async def test_writes_missing_resources_and_timeouts_are_never_retried(
    client: HttpClient, server: TestServer
) -> None:
    with pytest.raises(SourceError):
        await client.post_json("ecriture", str(server.make_url("/flaky")), payload={})
    assert HITS["flaky"] == 1

    with pytest.raises(SourceError) as missing:
        await client.get_json("absent", str(server.make_url("/counted/absent")))
    assert missing.value.kind == "not_found"
    assert HITS["absent"] == 1

    with pytest.raises(SourceError) as slow:
        await client.get_json("lent", str(server.make_url("/counted/lent")))
    assert slow.value.kind == "timeout"
    assert HITS["lent"] == 1
