"""Briques transverses : circuit-breaker, limitation de débit, géométrie."""

import pytest

from app.core.geo import circle_polygon, commune_codes, haversine_m, walking_minutes
from app.core.http import CircuitBreaker
from app.core.rate_limit import SlidingWindowRateLimiter


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_breaker_opens_after_threshold_and_recovers() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker(failure_threshold=2, reset_after_s=30, clock=clock)

    breaker.record_failure()
    assert breaker.allow()
    breaker.record_failure()
    assert not breaker.allow()

    clock.now = 30
    assert breaker.allow(), "un appel d'essai passe après le délai"
    assert not breaker.allow(), "les appels concurrents restent bloqués"

    breaker.record_success()
    assert breaker.allow()


def test_breaker_reopens_when_trial_fails() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker(failure_threshold=1, reset_after_s=10, clock=clock)
    breaker.record_failure()
    clock.now = 10
    assert breaker.allow()
    breaker.record_failure()
    assert not breaker.allow()


def test_rate_limiter_blocks_then_releases() -> None:
    clock = FakeClock()
    limiter = SlidingWindowRateLimiter(limit=2, window_s=60, clock=clock)

    assert limiter.check("ip") is None
    assert limiter.check("ip") is None
    assert limiter.check("ip") == pytest.approx(60)
    assert limiter.check("other") is None

    clock.now = 61
    assert limiter.check("ip") is None


def test_haversine_matches_known_distance() -> None:
    # Notre-Dame -> Tour Eiffel : environ 4,1 km.
    assert haversine_m(48.8530, 2.3499, 48.8584, 2.2945) == pytest.approx(4100, rel=0.02)


def test_circle_polygon_is_closed_and_at_radius() -> None:
    ring = circle_polygon(48.86, 2.33, 300)["coordinates"][0]
    assert ring[0] == ring[-1]
    for lon, lat in ring:
        assert haversine_m(48.86, 2.33, lat, lon) == pytest.approx(300, rel=0.01)


def test_walking_minutes() -> None:
    assert walking_minutes(10) == 1
    assert walking_minutes(800) == 13


@pytest.mark.parametrize(
    ("citycode", "expected"),
    [
        ("75101", ["75101", "75056"]),
        ("69381", ["69381", "69123"]),
        ("13201", ["13201", "13055"]),
        ("75056", ["75056"]),
        ("49007", ["49007"]),
    ],
)
def test_commune_codes(citycode: str, expected: list[str]) -> None:
    assert commune_codes(citycode) == expected
