"""DVF : ventes de logements dans un rayon de 300 m.

`api.cquest.org/dvf` n'étant plus en service, la source est l'API de l'application
officielle DVF (Etalab), interrogée par section cadastrale : on récupère d'abord les
sections qui recoupent le rayon (API Carto), puis leurs mutations en parallèle.
"""

import json
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import median, quantiles
from typing import Any

from app.core.errors import NoDataError
from app.core.geo import circle_polygon, haversine_m
from app.core.http import HttpClient
from app.services.providers.base import (
    AuditContext,
    ProviderData,
    as_rows,
    gather_parts,
    to_float,
)
from app.services.street import Street, normalize_street_name

_FEUILLE_URL = "https://apicarto.ign.fr/api/cadastre/feuille"
_MUTATIONS_URL = "https://app.dvf.etalab.gouv.fr/api/mutations3"
_RADIUS_M = 300
_MAX_SECTIONS = 12
_LON_LAT = 2
# Marge autour de l'emprise de la voie pour retrouver ses sections cadastrales.
_STREET_MARGIN_M = 40
_RECENT_SALES = 10
_RECENT_MONTHS = 24
# Ventes nécessaires pour avancer une médiane, puis pour chiffrer son évolution.
_MIN_SALES_FOR_MEDIAN = 5
_MIN_SALES_FOR_TREND_PCT = 20
_STABLE_BELOW_PCT = 3.0
_STABLE_BELOW_PCT_SMALL_SAMPLE = 10.0
_MAX_MAP_POINTS = 300
_HOUSING = {"Appartement": "appartement", "Maison": "maison"}
_IGNORED_LOCALS = {"Dépendance", "None", ""}
_MIN_SURFACE_M2 = 9.0
_MIN_SALES_FOR_QUARTILES = 4
# Bornes de vraisemblance du prix au m² (écarte ventes en bloc et erreurs de saisie).
_MIN_PRICE_M2, _MAX_PRICE_M2 = 300.0, 60_000.0


@dataclass(frozen=True, slots=True)
class Sale:
    date: str
    price: float
    surface_m2: float
    kind: str
    distance_m: int
    rooms: int | None = None
    # Numéro dans la voie, tel que publié par DVF.
    number: int | None = None
    lat: float = 0.0
    lon: float = 0.0

    @property
    def price_m2(self) -> float:
        return self.price / self.surface_m2


class DvfProvider:
    name = "dvf"

    def __init__(self, http: HttpClient) -> None:
        self._http = http

    async def fetch(self, ctx: AuditContext) -> ProviderData:
        if ctx.street is not None:
            along_street = await self._fetch_street(ctx, ctx.street)
            if along_street is not None:
                return along_street
            # Aucune vente enregistrée dans la voie : analyse au rayon, comme pour une adresse.
        polygon = circle_polygon(ctx.lat, ctx.lon, _RADIUS_M)
        rows, nb_sections, missing = await self._rows(ctx, polygon)
        sales = build_sales(rows, ctx.lat, ctx.lon, _RADIUS_M)
        if not sales:
            raise NoDataError
        summary = summarize(sales)
        summary["perimetre"] = "rayon"
        summary["rayon_m"] = _RADIUS_M
        summary["sections_interrogees"] = nb_sections
        return ProviderData(data=summary, missing=missing)

    async def _fetch_street(self, ctx: AuditContext, street: Street) -> ProviderData | None:
        """Ventes de la voie, comparées à celles des sections cadastrales qu'elle traverse."""
        rows, nb_sections, missing = await self._rows(ctx, street.envelope(_STREET_MARGIN_M))
        reach = street.length_m + _RADIUS_M
        sales = build_sales(
            [row for row in rows if _on_street(row, street)], ctx.lat, ctx.lon, reach
        )
        if not sales:
            return None
        summary = summarize(sales)
        summary["perimetre"] = "rue"
        summary["rue"] = street.name
        summary["sections_interrogees"] = nb_sections
        summary["comparaison"] = _comparison(summary, build_sales(rows, ctx.lat, ctx.lon, reach))
        return ProviderData(data=summary, missing=missing)

    async def _rows(
        self, ctx: AuditContext, polygon: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], int, tuple[str, ...]]:
        """Lignes DVF des sections recoupant l'emprise : (lignes, nb sections, échecs)."""
        sections = await self._sections(ctx, polygon)
        if not sections:
            raise NoDataError
        by_section, missing = await gather_parts(
            {
                f"{commune}/{section}": self._mutations(commune, section)
                for commune, section in sections
            }
        )
        rows = [row for section_rows in by_section.values() for row in section_rows]
        return rows, len(by_section), missing

    async def _sections(self, ctx: AuditContext, area: dict[str, Any]) -> list[tuple[str, str]]:
        polygon = json.dumps(area, separators=(",", ":"))
        payload = await self._http.get_json(
            "apicarto_feuille", _FEUILLE_URL, params={"geom": polygon}
        )
        distances: dict[tuple[str, str], float] = {}
        for feature in as_rows(payload, "features"):
            section = _section_key(feature.get("properties") or {})
            if section is not None:
                distance = _distance_to_feature(feature, ctx.lat, ctx.lon)
                distances[section] = min(distance, distances.get(section, distance))
        # Au-delà du plafond, ce sont les sections les plus éloignées qui sont écartées.
        return sorted(distances, key=lambda section: (distances[section], section))[:_MAX_SECTIONS]

    async def _mutations(self, commune: str, section: str) -> list[dict[str, Any]]:
        payload = await self._http.get_json("dvf", f"{_MUTATIONS_URL}/{commune}/{section}")
        return as_rows(payload, "mutations")


def _on_street(row: dict[str, Any], street: Street) -> bool:
    """Vrai si la ligne DVF porte le code de la voie ou, à défaut, son nom."""
    code = str(row.get("adresse_code_voie") or "").upper()
    if street.fantoir is not None and code == street.fantoir:
        return True
    return normalize_street_name(row.get("adresse_nom_voie")) == normalize_street_name(street.name)


def _comparison(street_summary: dict[str, Any], area_sales: list[Sale]) -> dict[str, Any]:
    """Repère : ventes de tout le secteur traversé, voie comprise."""
    area_median = _median_price(area_sales)
    gap = 100 * (street_summary["prix_m2_median"] - area_median) / area_median
    return {
        "perimetre": "sections cadastrales traversées",
        "nb_ventes": len(area_sales),
        "prix_m2_median": area_median,
        "ecart_pct": round(gap, 1),
    }


def _positions(coordinates: Any) -> Iterator[tuple[float, float]]:
    """Sommets (lon, lat) d'une géométrie GeoJSON, quel que soit son niveau d'imbrication."""
    if not isinstance(coordinates, list):
        return
    if len(coordinates) >= _LON_LAT and all(isinstance(c, int | float) for c in coordinates[:2]):
        yield float(coordinates[0]), float(coordinates[1])
        return
    for item in coordinates:
        yield from _positions(item)


def _distance_to_feature(feature: dict[str, Any], lat: float, lon: float) -> float:
    """Distance du point à l'emprise de la feuille (0 si le point est dedans)."""
    points = list(_positions((feature.get("geometry") or {}).get("coordinates")))
    if not points:
        return 0.0
    lons, lats = [p[0] for p in points], [p[1] for p in points]
    nearest_lon = min(max(lon, min(lons)), max(lons))
    nearest_lat = min(max(lat, min(lats)), max(lats))
    return haversine_m(lat, lon, nearest_lat, nearest_lon)


def _section_key(properties: dict[str, Any]) -> tuple[str, str] | None:
    """(code commune DVF, préfixe+section) à partir d'une feuille cadastrale."""
    department, section = properties.get("code_dep"), properties.get("section")
    arrondissement, commune = properties.get("code_arr"), properties.get("code_com")
    if not (isinstance(department, str) and isinstance(section, str) and isinstance(commune, str)):
        return None
    # Paris, Lyon, Marseille : DVF est indexé par arrondissement.
    local_code = (
        arrondissement if isinstance(arrondissement, str) and arrondissement != "000" else commune
    )
    prefix = str(properties.get("com_abs") or "000")
    return f"{department}{local_code}", f"{prefix}{section.rjust(2, '0')}"


def build_sales(rows: list[dict[str, Any]], lat: float, lon: float, radius_m: float) -> list[Sale]:
    """Regroupe les lignes DVF par mutation et ne garde que les ventes de logements du rayon."""
    grouped: dict[str, dict[tuple[Any, ...], dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        mutation_id = row.get("id_mutation")
        if isinstance(mutation_id, str):
            # Une même ligne peut être répétée (plusieurs natures de culture, sections voisines).
            grouped[mutation_id][_row_identity(row)] = row
    sales = [
        sale
        for lots in grouped.values()
        if (sale := _sale_from_lots(list(lots.values()), lat, lon, radius_m)) is not None
    ]
    sales.sort(key=lambda sale: sale.date, reverse=True)
    return sales


def _row_identity(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("id_parcelle"),
        row.get("lot1_numero"),
        row.get("type_local"),
        row.get("surface_reelle_bati"),
        row.get("nombre_pieces_principales"),
    )


def _sale_from_lots(
    lots: list[dict[str, Any]], lat: float, lon: float, radius_m: float
) -> Sale | None:
    first = lots[0]
    built = [lot for lot in lots if str(lot.get("type_local")) not in _IGNORED_LOCALS]
    # On écarte les mutations mêlant logements et locaux d'activité : prix non ventilable.
    if first.get("nature_mutation") != "Vente" or not built:
        return None
    if any(lot.get("type_local") not in _HOUSING for lot in built):
        return None
    price = to_float(first.get("valeur_fonciere"))
    surface = sum(to_float(lot.get("surface_reelle_bati")) or 0.0 for lot in built)
    lot_lat, lot_lon = to_float(first.get("latitude")), to_float(first.get("longitude"))
    if price is None or surface < _MIN_SURFACE_M2 or lot_lat is None or lot_lon is None:
        return None
    distance = haversine_m(lat, lon, lot_lat, lot_lon)
    if distance > radius_m or not _MIN_PRICE_M2 <= price / surface <= _MAX_PRICE_M2:
        return None
    kinds = {_HOUSING[str(lot["type_local"])] for lot in built}
    rooms = sum(to_float(lot.get("nombre_pieces_principales")) or 0.0 for lot in built)
    return Sale(
        date=str(first.get("date_mutation")),
        price=price,
        surface_m2=surface,
        kind=kinds.pop() if len(kinds) == 1 else "mixte",
        distance_m=round(distance),
        rooms=round(rooms) if rooms else None,
        number=round(number) if (number := to_float(first.get("adresse_numero"))) else None,
        lat=lot_lat,
        lon=lot_lon,
    )


def _median_price(sales: list[Sale]) -> int:
    return round(median(sale.price_m2 for sale in sales))


def _spread(sales: list[Sale]) -> dict[str, int]:
    """Étendue des prix au m² : extrêmes et quartiles (moitié centrale des ventes)."""
    prices = sorted(sale.price_m2 for sale in sales)
    if len(prices) >= _MIN_SALES_FOR_QUARTILES:
        first, _, third = quantiles(prices, n=4)
    else:
        first, third = prices[0], prices[-1]
    return {
        "min": round(prices[0]),
        "q1": round(first),
        "q3": round(third),
        "max": round(prices[-1]),
    }


def _sale_date(sale: Sale) -> date | None:
    try:
        return date.fromisoformat(sale.date[:10])
    except ValueError:
        return None


def _recent(sales: list[Sale]) -> dict[str, Any] | None:
    """Médiane des 24 derniers mois de ventes connues, et son évolution sur la période d'avant.

    La fenêtre se termine à la dernière vente publiée (DVF a plusieurs mois de retard), non à
    la date du jour. Sans assez de ventes, aucun chiffre n'est avancé.
    """
    dated = [(when, sale) for sale in sales if (when := _sale_date(sale)) is not None]
    if not dated:
        return None
    latest = max(when for when, _ in dated)
    window = timedelta(days=_RECENT_MONTHS * 365 // 12)
    recent = [sale for when, sale in dated if latest - when < window]
    previous = [sale for when, sale in dated if window <= latest - when < 2 * window]
    if len(recent) < _MIN_SALES_FOR_MEDIAN:
        return None
    median_recent = _median_price(recent)
    by_kind: dict[str, list[Sale]] = defaultdict(list)
    for sale in recent:
        by_kind[sale.kind].append(sale)
    return {
        "mois": _RECENT_MONTHS,
        "jusqu_au": latest.isoformat(),
        "nb_ventes": len(recent),
        "prix_m2_median": median_recent,
        "par_type": {
            kind: {"nb_ventes": len(items), "prix_m2_median": _median_price(items)}
            for kind, items in sorted(by_kind.items())
        },
        **_trend(median_recent, len(recent), previous),
    }


def _trend(median_recent: int, nb_recent: int, previous: list[Sale]) -> dict[str, Any]:
    """Évolution par rapport aux 24 mois précédents.

    Un pourcentage n'est donné qu'avec assez de ventes dans chaque période ; en dessous,
    seul le sens de l'évolution est indiqué, et rien du tout sur une poignée de ventes.
    """
    if len(previous) < _MIN_SALES_FOR_MEDIAN:
        return {"tendance": None, "tendance_pct": None}
    change = 100 * (median_recent - _median_price(previous)) / _median_price(previous)
    precise = min(nb_recent, len(previous)) >= _MIN_SALES_FOR_TREND_PCT
    # Sur une poignée de ventes, un écart de quelques points n'est que du bruit : il faut un
    # mouvement net pour parler de hausse ou de baisse.
    if abs(change) < (_STABLE_BELOW_PCT if precise else _STABLE_BELOW_PCT_SMALL_SAMPLE):
        direction = "stable"
    else:
        direction = "en hausse" if change > 0 else "en baisse"
    return {"tendance": direction, "tendance_pct": round(change, 1) if precise else None}


def _map_points(sales: list[Sale]) -> list[list[float]]:
    """[lon, lat, prix médian au m², nombre de ventes, année de la dernière] par emplacement.

    Les ventes d'un même immeuble partagent une position : elles sont réunies en un point.
    """
    by_place: dict[tuple[float, float], list[Sale]] = defaultdict(list)
    for sale in sales:
        if sale.date[:4].isdigit():
            by_place[(round(sale.lon, 5), round(sale.lat, 5))].append(sale)
    points = [
        [lon, lat, _median_price(items), len(items), max(int(item.date[:4]) for item in items)]
        for (lon, lat), items in by_place.items()
    ]
    # Les emplacements les plus actifs d'abord, si le plafond doit en écarter : en zone très
    # dense, ce sont donc les ventes isolées (souvent des maisons) qui sortent de la carte.
    points.sort(key=lambda point: -point[3])
    return points[:_MAX_MAP_POINTS]


def summarize(sales: list[Sale]) -> dict[str, Any]:
    """Indicateurs de prix au m² : global, par type de bien et par année."""
    by_kind: dict[str, list[Sale]] = defaultdict(list)
    by_year: dict[str, list[Sale]] = defaultdict(list)
    for sale in sales:
        by_kind[sale.kind].append(sale)
        by_year[sale.date[:4]].append(sale)
    return {
        "nb_ventes": len(sales),
        "prix_m2_median": _median_price(sales),
        "recent": _recent(sales),
        "points": _map_points(sales),
        "dispersion": _spread(sales),
        "par_type": {
            kind: {"nb_ventes": len(items), "prix_m2_median": _median_price(items)}
            for kind, items in sorted(by_kind.items())
        },
        "historique": [
            {"annee": int(year), "nb_ventes": len(items), "prix_m2_median": _median_price(items)}
            for year, items in sorted(by_year.items())
            if year.isdigit()
        ],
        "dernieres_ventes": [
            {
                "date": sale.date,
                "prix": round(sale.price),
                "surface_m2": round(sale.surface_m2),
                "prix_m2": round(sale.price_m2),
                "type": sale.kind,
                "pieces": sale.rooms,
                "numero": sale.number,
                "distance_m": sale.distance_m,
            }
            for sale in sales[:_RECENT_SALES]
        ],
    }
