"""Calculs géographiques purs (aucune E/S)."""

import math
from typing import Any

_EARTH_RADIUS_M = 6_371_008.8
_M_PER_DEG_LAT = 110_540.0
_M_PER_DEG_LON_EQUATOR = 111_320.0
# 4,8 km/h, avec un détour moyen de 30 % par rapport à la distance à vol d'oiseau.
_WALK_SPEED_M_PER_MIN = 80.0
_WALK_DETOUR_FACTOR = 1.3

# Arrondissements municipaux -> commune de rattachement.
_ARRONDISSEMENT_PREFIXES = {"751": "75056", "132": "13055", "6938": "69123"}


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance orthodromique en mètres entre deux points WGS84."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(a))


def destination(
    lat: float, lon: float, bearing_deg: float, distance_m: float
) -> tuple[float, float]:
    """Point (lat, lon) atteint depuis l'origine ; approximation plane, valable < 10 km."""
    bearing = math.radians(bearing_deg)
    d_lat = distance_m * math.cos(bearing) / _M_PER_DEG_LAT
    d_lon = distance_m * math.sin(bearing) / (_M_PER_DEG_LON_EQUATOR * math.cos(math.radians(lat)))
    return round(lat + d_lat, 6), round(lon + d_lon, 6)


def circle_polygon(lat: float, lon: float, radius_m: float, segments: int = 16) -> dict[str, Any]:
    """Polygone GeoJSON approchant un cercle."""
    ring = []
    for index in range(segments):
        point_lat, point_lon = destination(lat, lon, 360.0 * index / segments, radius_m)
        ring.append([point_lon, point_lat])
    ring.append(ring[0])
    return {"type": "Polygon", "coordinates": [ring]}


def walking_minutes(distance_m: float) -> int:
    """Temps de marche estimé à partir de la distance à vol d'oiseau."""
    return max(1, round(distance_m * _WALK_DETOUR_FACTOR / _WALK_SPEED_M_PER_MIN))


def departement_code(citycode: str) -> str:
    """Code du département d'une commune (trois caractères outre-mer : 971, 974…)."""
    return citycode[:3] if citycode.startswith("97") else citycode[:2]


def commune_codes(citycode: str) -> list[str]:
    """Codes INSEE à interroger : le code fourni puis, pour Paris/Lyon/Marseille, la commune."""
    for prefix, parent in _ARRONDISSEMENT_PREFIXES.items():
        if citycode.startswith(prefix) and citycode != parent:
            return [citycode, parent]
    return [citycode]
