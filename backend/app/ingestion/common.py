"""Briques communes de l'ingestion : téléchargement, lecture CSV, conversions."""

import asyncio
import codecs
import csv
import io
import logging
import re
import zlib
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import TypeVar

import aiohttp

T = TypeVar("T")

logger = logging.getLogger(__name__)

_HTTP_SERVER_ERROR = 500
_HTTP_TOO_MANY_REQUESTS = 429
_INSEE_PATTERN = re.compile(r"^(?:\d{2}|2[AB])\d{3}$", re.ASCII)
_MISSING = {"", "NA", "nan", "None", "null"}
_GZIP_MAGIC = b"\x1f\x8b"
_CHUNK_BYTES = 256 * 1024
_OVERSEAS_PREFIXES = ("97", "98")


@dataclass(frozen=True, slots=True)
class IngestionOptions:
    """Paramètres de la ligne de commande."""

    # None = France entière ; sinon codes de département ("49", "2A", "974").
    departements: frozenset[str] | None = None
    # Nombre d'années de délinquance conservées (année courante incluse).
    crime_years: int = 3
    # Ancienneté maximale des autorisations d'urbanisme, en années.
    permit_years: int = 5
    # Carte des loyers : fichier data.gouv par type de bien et millésime, lus dans la
    # configuration (LOYERS_*) pour suivre une nouvelle édition sans toucher au code.
    rent_resources: Mapping[str, str] = field(default_factory=dict)
    rent_year: int = 0

    def accepts(self, code_insee: str) -> bool:
        return self.departements is None or departement_of(code_insee) in self.departements


def departement_of(code_insee: str) -> str:
    return code_insee[:3] if code_insee.startswith(_OVERSEAS_PREFIXES) else code_insee[:2]


def is_insee_code(value: str) -> bool:
    return _INSEE_PATTERN.fullmatch(value) is not None


def to_number(value: str | None) -> float | None:
    """Nombre au format français ou anglais ; None si la valeur est absente."""
    if value is None or value.strip() in _MISSING:
        return None
    try:
        return float(value.strip().replace(",", "."))
    except ValueError:
        return None


def to_integer(value: str | None) -> int | None:
    number = to_number(value)
    return round(number) if number is not None else None


def to_date(value: str | None) -> date | None:
    if value is None or value.strip() in _MISSING:
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


def read_csv(text: str, delimiter: str = ";") -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text.lstrip("﻿")), delimiter=delimiter))


def batched(items: Iterable[T], size: int) -> Iterator[list[T]]:
    batch: list[T] = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


class Downloader:
    """Téléchargements longs de l'ingestion (hors du budget de 3 s des appels temps réel)."""

    def __init__(
        self, session: aiohttp.ClientSession, *, attempts: int = 5, retry_delay_s: float = 5.0
    ) -> None:
        self._session = session
        self._attempts = attempts
        self._retry_delay_s = retry_delay_s

    async def text(self, url: str, params: Mapping[str, str] | None = None) -> str:
        async def attempt() -> str:
            async with self._session.get(url, params=params) as response:
                response.raise_for_status()
                return await response.text(encoding="utf-8")

        return await self._with_retries(attempt)

    async def content(self, url: str) -> bytes:
        """Fichier binaire entier (archive zip) ; à réserver aux fichiers de taille modérée."""
        buffer = bytearray()

        async def attempt() -> str:
            buffer.clear()
            async with self._session.get(url) as response:
                response.raise_for_status()
                buffer.extend(await response.read())
            return ""

        await self._with_retries(attempt)
        return bytes(buffer)

    async def post_form(self, url: str, build_form: Callable[[], aiohttp.FormData]) -> str:
        """`build_form` est rappelé à chaque tentative : un FormData ne sert qu'une fois."""

        async def attempt() -> str:
            async with self._session.post(url, data=build_form()) as response:
                response.raise_for_status()
                return await response.text(encoding="utf-8")

        return await self._with_retries(attempt)

    async def _with_retries(self, attempt: Callable[[], Awaitable[str]]) -> str:
        """Réessaie les échecs transitoires (5xx, coupure, timeout) avec une attente croissante."""
        for number in range(1, self._attempts + 1):
            try:
                return await attempt()
            except aiohttp.ClientResponseError as exc:
                if exc.status < _HTTP_SERVER_ERROR and exc.status != _HTTP_TOO_MANY_REQUESTS:
                    raise
                error: Exception = exc
            except (aiohttp.ClientError, TimeoutError) as exc:
                error = exc
            if number == self._attempts:
                raise error
            delay = self._retry_delay_s * 2 ** (number - 1)
            logger.warning("Tentative %d échouée (%s), reprise dans %.0f s", number, error, delay)
            await asyncio.sleep(delay)
        raise RuntimeError("unreachable")

    async def csv_rows(self, url: str, delimiter: str = ";") -> AsyncIterator[dict[str, str]]:
        """Lit un CSV (gzip ou non) ligne à ligne, sans le charger en mémoire.

        Suppose l'absence de saut de ligne à l'intérieur des champs.
        """
        header: list[str] | None = None
        async for lines in self._line_blocks(url):
            for values in csv.reader(lines, delimiter=delimiter):
                if header is None:
                    header = [name.lstrip("﻿") for name in values]
                elif len(values) == len(header):
                    yield dict(zip(header, values, strict=True))

    async def _line_blocks(self, url: str) -> AsyncIterator[list[str]]:
        decoder = codecs.getincrementaldecoder("utf-8")()
        inflater: zlib._Decompress | None = None
        pending = ""
        first = True
        async with self._session.get(url) as response:
            response.raise_for_status()
            async for chunk in response.content.iter_chunked(_CHUNK_BYTES):
                if first:
                    first = False
                    if chunk.startswith(_GZIP_MAGIC):
                        inflater = zlib.decompressobj(wbits=31)
                data = inflater.decompress(chunk) if inflater is not None else chunk
                *lines, pending = (pending + decoder.decode(data)).split("\n")
                if lines:
                    yield lines
        if pending.strip():
            yield [pending]
