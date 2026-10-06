"""Client HTTP asynchrone : timeout strict, circuit-breaker par source, erreurs typées."""

import asyncio
import json
import time
from collections.abc import Callable, Mapping
from typing import Any

import aiohttp

from app.core.errors import SourceError

Params = Mapping[str, str | int | float]

_MAX_BODY_BYTES = 8 * 1024 * 1024
_CHUNK_BYTES = 64 * 1024
_HTTP_NOT_FOUND = 404
_HTTP_TOO_MANY_REQUESTS = 429
_HTTP_SERVER_ERROR = 500
_HTTP_CLIENT_ERROR = 400
# Relance d'une lecture : seulement si l'échec est arrivé vite, après une courte pause.
_RETRY_WITHIN_S = 2.0
_RETRY_DELAY_S = 0.3


class CircuitBreaker:
    """Coupe les appels vers une source après des échecs consécutifs.

    Fermé -> ouvert après `failure_threshold` échecs ; après `reset_after_s`, un
    unique appel d'essai est autorisé (semi-ouvert) : son succès referme le circuit.
    """

    def __init__(
        self,
        failure_threshold: int,
        reset_after_s: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._reset_after_s = reset_after_s
        self._clock = clock
        self._failures = 0
        self._opened_at: float | None = None

    def allow(self) -> bool:
        if self._opened_at is None:
            return True
        if self._clock() - self._opened_at >= self._reset_after_s:
            # Semi-ouvert : on laisse passer un essai et on réarme la fenêtre,
            # les appels concurrents restent bloqués jusqu'au verdict.
            self._opened_at = self._clock()
            return True
        return False

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self._failure_threshold:
            self._opened_at = self._clock()


class HttpClient:
    """Façade au-dessus d'une session aiohttp partagée."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        *,
        timeout_s: float,
        failure_threshold: int,
        reset_after_s: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._session = session
        self._clock = clock
        self._timeout = aiohttp.ClientTimeout(total=timeout_s)
        self._failure_threshold = failure_threshold
        self._reset_after_s = reset_after_s
        self._breakers: dict[str, CircuitBreaker] = {}

    async def get_json(self, source: str, url: str, *, params: Params | None = None) -> Any:
        """GET renvoyant le JSON décodé (None si le corps est vide)."""
        return await self._request(source, "GET", url, params=params)

    async def post_form_json(
        self,
        source: str,
        url: str,
        *,
        data: Mapping[str, str],
        timeout_s: float | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        """POST d'un formulaire renvoyant le JSON décodé.

        `timeout_s` raccourcit le délai de cet appel, pour enchaîner plusieurs serveurs de repli.
        """
        return await self._request(
            source, "POST", url, timeout_s=timeout_s, data=data, headers=headers
        )

    async def post_json(
        self, source: str, url: str, *, payload: Any, headers: Mapping[str, str] | None = None
    ) -> Any:
        """POST d'un corps JSON renvoyant le JSON décodé."""
        return await self._request(source, "POST", url, json=payload, headers=headers)

    def _breaker(self, source: str) -> CircuitBreaker:
        breaker = self._breakers.get(source)
        if breaker is None:
            breaker = CircuitBreaker(self._failure_threshold, self._reset_after_s)
            self._breakers[source] = breaker
        return breaker

    async def _request(
        self, source: str, method: str, url: str, *, timeout_s: float | None = None, **kwargs: Any
    ) -> Any:
        timeout = self._timeout if timeout_s is None else aiohttp.ClientTimeout(total=timeout_s)
        breaker = self._breaker(source)
        if not breaker.allow():
            raise SourceError("circuit_open", source)
        started = self._clock()
        try:
            try:
                payload = await self._send(source, method, url, timeout, kwargs)
            except SourceError as exc:
                if not self._worth_retrying(method, exc, started):
                    raise
                # Incident bref (502, connexion coupée) : un second essai suffit le plus souvent.
                await asyncio.sleep(_RETRY_DELAY_S)
                payload = await self._send(source, method, url, timeout, kwargs)
        except SourceError as exc:
            if exc.transient:
                breaker.record_failure()
            raise
        breaker.record_success()
        return payload

    def _worth_retrying(self, method: str, error: SourceError, started: float) -> bool:
        """Un seul nouvel essai, pour une lecture qui a échoué vite sur une erreur passagère.

        Un délai dépassé n'est pas rejoué : la source a déjà consommé son temps de réponse.
        """
        return (
            method == "GET"
            and error.transient
            and error.kind == "http_error"
            and self._clock() - started < _RETRY_WITHIN_S
        )

    async def _send(
        self,
        source: str,
        method: str,
        url: str,
        limit: aiohttp.ClientTimeout,
        kwargs: dict[str, Any],
    ) -> Any:
        try:
            async with self._session.request(method, url, timeout=limit, **kwargs) as response:
                return await _decode(response)
        except TimeoutError as exc:
            raise SourceError("timeout", source) from exc
        except aiohttp.ClientError as exc:
            raise SourceError("http_error", type(exc).__name__) from exc


async def _decode(response: aiohttp.ClientResponse) -> Any:
    status = response.status
    if status == _HTTP_NOT_FOUND:
        raise SourceError("not_found", str(status), transient=False)
    if status >= _HTTP_SERVER_ERROR or status == _HTTP_TOO_MANY_REQUESTS:
        raise SourceError("http_error", str(status))
    if status >= _HTTP_CLIENT_ERROR:
        raise SourceError("http_error", str(status), transient=False)

    body = bytearray()
    async for chunk in response.content.iter_chunked(_CHUNK_BYTES):
        body.extend(chunk)
        if len(body) > _MAX_BODY_BYTES:
            raise SourceError("invalid_response", "body too large", transient=False)
    if not body.strip():
        return None
    try:
        return json.loads(body)
    except ValueError as exc:
        raise SourceError("invalid_response", "invalid JSON") from exc
