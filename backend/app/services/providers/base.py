"""Contrat commun des sources de données et utilitaires partagés."""

import asyncio
import logging
import math
from collections.abc import Awaitable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from app.core.errors import SourceError
from app.core.geo import commune_codes
from app.services.street import Street

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AuditContext:
    """Localisation résolue, transmise à chaque source."""

    lat: float
    lon: float
    citycode: str
    postcode: str | None = None
    region: str | None = None
    # Renseignée en mode « rue » : les sources qui le peuvent agrègent alors le long de la voie.
    street: Street | None = None

    @property
    def commune_codes(self) -> list[str]:
        return commune_codes(self.citycode)


@dataclass(frozen=True, slots=True)
class ProviderData:
    """Données d'une source ; `missing` liste les sous-appels restés sans réponse."""

    data: dict[str, Any]
    missing: tuple[str, ...] = ()


class Provider(Protocol):
    """Une source de données de l'audit.

    `fetch` lève NoDataError si la source n'a rien pour cette localisation,
    SourceError si elle est en échec.
    """

    @property
    def name(self) -> str: ...

    async def fetch(self, ctx: AuditContext) -> ProviderData: ...


async def gather_parts(
    calls: Mapping[str, Awaitable[Any]],
) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Exécute des sous-appels en parallèle en tolérant les échecs partiels.

    Renvoie (résultats, clés en échec). Lève la première SourceError si tout échoue.
    """
    outcomes = await asyncio.gather(*calls.values(), return_exceptions=True)
    results: dict[str, Any] = {}
    failures: list[tuple[str, SourceError]] = []
    for key, outcome in zip(calls, outcomes, strict=True):
        if isinstance(outcome, SourceError):
            failures.append((key, outcome))
        elif isinstance(outcome, BaseException):
            raise outcome
        else:
            results[key] = outcome
    if failures and not results:
        raise failures[0][1]
    for key, failure in failures:
        logger.warning("Sous-appel %s en échec : %s", key, failure)
    return results, tuple(key for key, _ in failures)


def as_rows(payload: Any, key: str) -> list[dict[str, Any]]:
    """Extrait `payload[key]` en garantissant une liste d'objets."""
    rows = payload.get(key) if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise SourceError("invalid_response", f"missing '{key}'", transient=False)
    return [row for row in rows if isinstance(row, dict)]


def to_float(value: Any) -> float | None:
    """Convertit en float les nombres et chaînes numériques ; None pour 'nan', 'None', ''."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number
