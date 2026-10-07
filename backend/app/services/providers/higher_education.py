"""Enseignement supérieur à proximité (données ouvertes du ministère chargé de l'ESR).

Deux jeux complémentaires : les établissements principaux, publics et privés (universités,
écoles), et les implantations des établissements publics (facultés, campus, antennes).
"""

from typing import Any

from app.core.geo import haversine_m
from app.core.http import HttpClient
from app.services.providers.base import AuditContext, as_rows, gather_parts, to_float

_BASE_URL = "https://data.enseignementsup-recherche.gouv.fr/api/explore/v2.1/catalog/datasets"
_MAIN = "fr-esr-principaux-etablissements-enseignement-superieur"
_SITES = "fr-esr-implantations_etablissements_d_enseignement_superieur_publics"
_SOURCE = "esr"
RADIUS_M = 3000
_PAGE_SIZE = 100
_LIMIT = 12
_SAME_BUILDING_M = 30
_NOT_TEACHING = ("BIBLIOTHÈQUE", "BIBLIOTHEQUE", "SERVICE", "DIRECTION", "PRÉSIDENCE")


class HigherEducationFinder:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    async def nearby(self, ctx: AuditContext) -> tuple[dict[str, Any], bool]:
        """Établissements du plus proche au plus lointain, et vrai si la liste est incomplète.

        Lève SourceError si aucun des deux jeux ne répond.
        """
        parts, missing = await gather_parts(
            {name: self._records(name, ctx) for name in (_MAIN, _SITES)}
        )
        schools: dict[str, dict[str, Any]] = {}
        # Les établissements principaux d'abord : ils portent le sigle et le secteur.
        for row in parts.get(_MAIN, []):
            _add(schools, _main(row, ctx))
        for row in parts.get(_SITES, []):
            _add(schools, _site(row, ctx))
        ranked = sorted(schools.values(), key=lambda school: school["distance_m"])
        return {
            "rayon_m": RADIUS_M,
            "nb": len(ranked),
            "etablissements": ranked[:_LIMIT],
        }, bool(missing)

    async def _records(self, dataset: str, ctx: AuditContext) -> list[dict[str, Any]]:
        payload = await self._http.get_json(
            _SOURCE,
            f"{_BASE_URL}/{dataset}/records",
            params={
                "where": (
                    f"within_distance(coordonnees, geom'POINT({ctx.lon} {ctx.lat})', {RADIUS_M}m)"
                ),
                "limit": _PAGE_SIZE,
            },
        )
        return as_rows(payload, "results")


def _add(schools: dict[str, dict[str, Any]], school: dict[str, Any] | None) -> None:
    """Ajoute un établissement, sans doublon : même code UAI, même nom, ou même bâtiment.

    Les composantes d'une université logées à la même adresse (facultés, instituts, services)
    ne forment qu'une ligne : la première rencontrée, c'est-à-dire l'établissement principal.
    """
    if school is None:
        return
    key = str(school.pop("uai") or school["nom"]).casefold()
    same_name = any(
        existing["nom"].casefold() == school["nom"].casefold() for existing in schools.values()
    )
    same_place = any(
        haversine_m(existing["lat"], existing["lon"], school["lat"], school["lon"])
        < _SAME_BUILDING_M
        for existing in schools.values()
    )
    if key not in schools and not same_name and not same_place:
        schools[key] = school


def _located(row: dict[str, Any], ctx: AuditContext) -> tuple[float, float, int] | None:
    position = row.get("coordonnees") or {}
    lon, lat = to_float(position.get("lon")), to_float(position.get("lat"))
    if lon is None or lat is None:
        return None
    return lon, lat, round(haversine_m(ctx.lat, ctx.lon, lat, lon))


def _kind(value: Any) -> str | None:
    if isinstance(value, list):
        value = value[0] if value else None
    return value if isinstance(value, str) and value else None


def _main(row: dict[str, Any], ctx: AuditContext) -> dict[str, Any] | None:
    place, name = _located(row, ctx), row.get("uo_lib")
    if place is None or not isinstance(name, str):
        return None
    return {
        "uai": row.get("uai"),
        "nom": name,
        "sigle": row.get("sigle"),
        "type": _kind(row.get("type_d_etablissement")),
        "secteur": row.get("secteur_d_etablissement"),
        "effectif": None,
        "lon": place[0],
        "lat": place[1],
        "distance_m": place[2],
    }


def _site(row: dict[str, Any], ctx: AuditContext) -> dict[str, Any] | None:
    place, name = _located(row, ctx), row.get("implantation_lib")
    if place is None or not isinstance(name, str):
        return None
    if name.upper().startswith(_NOT_TEACHING):
        # Bibliothèques, services et directions : des implantations, pas des lieux d'études.
        return None
    students = to_float(row.get("effectif"))
    return {
        "uai": row.get("uai"),
        # Publiés en capitales : « UNITÉ DE FORMATION… » devient lisible.
        "nom": name.capitalize() if name.isupper() else name,
        "sigle": row.get("sigle"),
        "type": _kind(row.get("type_d_etablissement")),
        "secteur": "public",
        "effectif": round(students) if students else None,
        "lon": place[0],
        "lat": place[1],
        "distance_m": place[2],
    }
