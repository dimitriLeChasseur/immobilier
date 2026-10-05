"""Limitation de débit en mémoire, par fenêtre glissante."""

import time
from collections import deque
from collections.abc import Callable

_MAX_TRACKED_KEYS = 10_000


class SlidingWindowRateLimiter:
    """Autorise `limit` requêtes par clé sur une fenêtre de `window_s` secondes.

    État local au processus : suffisant tant que le backend tourne en un seul worker.
    """

    def __init__(
        self,
        limit: int,
        window_s: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._limit = limit
        self._window_s = window_s
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}

    def check(self, key: str) -> float | None:
        """Enregistre une requête. Renvoie None si autorisée, sinon le délai d'attente en s."""
        now = self._clock()
        hits = self._hits.setdefault(key, deque())
        while hits and now - hits[0] >= self._window_s:
            hits.popleft()
        if len(hits) >= self._limit:
            return self._window_s - (now - hits[0])
        hits.append(now)
        if len(self._hits) > _MAX_TRACKED_KEYS:
            self._evict(now)
        return None

    def _evict(self, now: float) -> None:
        stale = [key for key, hits in self._hits.items() if now - hits[-1] >= self._window_s]
        for key in stale:
            del self._hits[key]
