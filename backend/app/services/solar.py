"""Ensoleillement : position du soleil et masque du relief (calculs purs).

Équivalent minimal de suncalc : déclinaison et angle horaire en temps solaire vrai,
ce qui suffit pour intégrer une durée d'ensoleillement sur la journée.
"""

import math
from collections.abc import Sequence

AZIMUTHS_DEG: tuple[int, ...] = (0, 45, 90, 135, 180, 225, 270, 315)
AZIMUTH_LABELS: tuple[str, ...] = ("N", "NE", "E", "SE", "S", "SO", "O", "NO")

# Jour de l'année du 21 de chaque mois : échantillonne les quatre saisons.
_SAMPLE_DAYS: tuple[int, ...] = (21, 52, 80, 111, 141, 172, 202, 233, 264, 294, 325, 355)
_WINTER_SOLSTICE_DAY = 355
_STEP_MINUTES = 15
_OBSERVER_HEIGHT_M = 1.5


def sun_position(lat_deg: float, day_of_year: int, solar_hour: float) -> tuple[float, float]:
    """(élévation, azimut depuis le nord, sens horaire) en degrés."""
    lat = math.radians(lat_deg)
    declination = math.radians(23.44) * math.sin(2 * math.pi * (284 + day_of_year) / 365)
    hour_angle = math.radians(15.0 * (solar_hour - 12.0))
    sin_elevation = math.sin(lat) * math.sin(declination) + math.cos(lat) * math.cos(
        declination
    ) * math.cos(hour_angle)
    elevation = math.asin(max(-1.0, min(1.0, sin_elevation)))
    azimuth = math.atan2(
        math.sin(hour_angle),
        math.cos(hour_angle) * math.sin(lat) - math.tan(declination) * math.cos(lat),
    )
    return math.degrees(elevation), (math.degrees(azimuth) + 180.0) % 360.0


def horizon_profile(
    origin_altitude_m: float,
    ring_altitudes_m: Sequence[Sequence[float]],
    distances_m: Sequence[float],
) -> list[float]:
    """Angle d'élévation du relief (degrés, >= 0) pour chaque azimut de AZIMUTHS_DEG.

    `ring_altitudes_m[i][j]` : altitude dans l'azimut i à la distance `distances_m[j]`.
    """
    eye_level = origin_altitude_m + _OBSERVER_HEIGHT_M
    profile = []
    for altitudes in ring_altitudes_m:
        angles = (
            math.degrees(math.atan2(altitude - eye_level, distance))
            for altitude, distance in zip(altitudes, distances_m, strict=True)
        )
        profile.append(round(max(0.0, *angles), 1))
    return profile


def _horizon_at(profile: Sequence[float], azimuth_deg: float) -> float:
    """Interpolation linéaire du masque entre deux azimuts échantillonnés."""
    sector = 360.0 / len(profile)
    position = azimuth_deg / sector
    lower = int(position) % len(profile)
    upper = (lower + 1) % len(profile)
    fraction = position - int(position)
    return profile[lower] * (1 - fraction) + profile[upper] * fraction


def _day_ratio(lat_deg: float, day_of_year: int, profile: Sequence[float]) -> tuple[int, int]:
    """(pas de temps ensoleillés, pas de temps où le soleil est levé) sur une journée."""
    lit = daylight = 0
    for step in range(24 * 60 // _STEP_MINUTES):
        elevation, azimuth = sun_position(lat_deg, day_of_year, step * _STEP_MINUTES / 60.0)
        if elevation <= 0:
            continue
        daylight += 1
        if elevation > _horizon_at(profile, azimuth):
            lit += 1
    return lit, daylight


def sunlight_scores(lat_deg: float, profile: Sequence[float]) -> dict[str, int]:
    """Part (0-100) du temps de jour non masqué par le relief (année, solstice d'hiver)."""
    lit_total = daylight_total = 0
    for day in _SAMPLE_DAYS:
        lit, daylight = _day_ratio(lat_deg, day, profile)
        lit_total += lit
        daylight_total += daylight
    winter_lit, winter_daylight = _day_ratio(lat_deg, _WINTER_SOLSTICE_DAY, profile)
    return {
        "annuel": round(100 * lit_total / daylight_total) if daylight_total else 0,
        "solstice_hiver": round(100 * winter_lit / winter_daylight) if winter_daylight else 0,
    }
