"""Environnement du bien : qualité de l'air, inventaires du territoire et ensoleillement."""

import asyncio
import logging
import re
import unicodedata
from datetime import UTC, date, datetime, timedelta
from typing import Any

from app.core.errors import NoDataError, SourceError
from app.core.geo import departement_code, destination
from app.core.http import HttpClient
from app.services.insights import atmo_label, relief_summary
from app.services.providers.apicarto import feature_properties
from app.services.providers.base import AuditContext, ProviderData, to_float
from app.services.solar import AZIMUTH_LABELS, AZIMUTHS_DEG, horizon_profile, sunlight_scores

logger = logging.getLogger(__name__)

_ATMO_WFS_URL = "https://data.atmo-france.org/geoserver/ind/ows"
_GEO_COMMUNE_URL = "https://geo.api.gouv.fr/communes"
# Code de zone : commune INSEE (5 caractères) ou SIREN d'intercommunalité (9 chiffres).
_ZONE_CODE = re.compile(r"[0-9AB]{5}|\d{9}", re.ASCII)
_DEPARTMENT = re.compile(r"\d{2,3}|2[AB]", re.ASCII)
_ATMO_MIN, _ATMO_MAX = 1, 6
# clé du rapport -> colonne du flux
_ATMO_SUB_INDICES = {
    "pm2_5": "code_pm25",
    "pm10": "code_pm10",
    "no2": "code_no2",
    "o3": "code_o3",
    "so2": "code_so2",
}
_ATMO_POLLUTANT_LABELS = {
    "pm2_5": "particules fines PM2.5",
    "pm10": "particules PM10",
    "no2": "dioxyde d'azote",
    "o3": "ozone",
    "so2": "dioxyde de soufre",
}

# Point d'entrée commun des couches d'Atmo France (épisodes, inventaires).
_ATMO_OWS_URL = "https://data.atmo-france.org/geoserver/ows"
# Historique des épisodes de pollution : départements, bassins d'air (Auvergne-Rhône-Alpes,
# seuls à porter un vrai polygone) et Île-de-France (une zone régionale, code « 11 »).
_EPISODE_WINDOW = timedelta(days=365)
_EPISODE_FIELDS = "code_zone,lib_zone,date_ech,etat,code_pol,lib_pol"
# Plafond large : un département suivi chaque jour publie environ 1 100 lignes par an.
_EPISODE_MAX_ROWS = 5000
_NO_EPISODE = "PAS DE DEPASSEMENT"
_EPISODE_LEVELS = {
    "INFORMATION ET RECOMMANDATION": "information",
    "ALERTE": "alerte",
    # Niveau d'information qui dure : la procédure préfectorale est celle de l'alerte.
    "ALERTE SUR PERSISTANCE": "alerte",
}
_IDF_DEPARTMENTS = frozenset({"75", "77", "78", "91", "92", "93", "94", "95"})
_IDF_ZONE = ("11", "ILE-DE-FRANCE")
# Codes de polluant du flux ; quelques lignes portent un code parasite (« 08 », « 24 ») :
# le libellé, lu ensuite, les rattrape.
_EPISODE_POLLUTANT_CODES = {"1": "so2", "5": "pm10", "7": "o3", "8": "no2", "6001": "pm2_5"}
_EPISODE_POLLUTANT_WORDS = (
    ("2.5", "pm2_5"),
    ("2,5", "pm2_5"),
    ("10", "pm10"),
    ("ozone", "o3"),
    ("o3", "o3"),
    ("azote", "no2"),
    ("no2", "no2"),
    ("soufre", "so2"),
    ("so2", "so2"),
)
_ALTI_URL = "https://data.geopf.fr/altimetrie/1.0/calcul/alti/rest/elevation.json"
_RING_DISTANCES_M: tuple[float, ...] = (50.0, 150.0, 400.0, 1000.0, 2500.0)
# Valeur renvoyée par le service IGN hors emprise du modèle de terrain.
_NO_DATA_ALTITUDE = -9000.0


class AirQualityProvider:
    """Indice ATMO du jour (1 « bon » à 6 « extrêmement mauvais »), publié par Atmo France.

    Donnée ouverte des associations agréées de surveillance de la qualité de l'air (AASQA),
    sous licence ODbL : usage commercial permis, attribution obligatoire. Selon les régions,
    l'indice est calculé à la commune ou à l'intercommunalité : on cherche du plus précis
    au plus large.
    """

    name = "qualite_air"

    def __init__(self, http: HttpClient) -> None:
        self._http = http

    async def fetch(self, ctx: AuditContext) -> ProviderData:
        # Indice du jour et épisodes de l'année : deux flux, chacun utile sans l'autre.
        outcomes = await asyncio.gather(
            self._index(ctx), self._episodes(ctx), return_exceptions=True
        )
        parts = dict(zip(("indice", "episodes"), outcomes, strict=True))
        for outcome in parts.values():
            if isinstance(outcome, BaseException) and not isinstance(
                outcome, SourceError | NoDataError
            ):
                raise outcome
        index, episodes = parts["indice"], parts["episodes"]
        published = isinstance(episodes, dict) and (
            episodes["nb_jours"] > 0 or episodes["suivi_quotidien"]
        )
        if not isinstance(index, dict) and not published:
            for outcome in parts.values():
                if isinstance(outcome, SourceError):
                    raise outcome
            raise NoDataError
        data = dict(index) if isinstance(index, dict) else {}
        data["episodes"] = episodes if isinstance(episodes, dict) else None
        missing = tuple(key for key, outcome in parts.items() if isinstance(outcome, SourceError))
        return ProviderData(data=data, missing=missing)

    async def _index(self, ctx: AuditContext) -> dict[str, Any]:
        today = datetime.now(UTC).date()
        codes = ctx.commune_codes
        rows = await self._indices(codes, today)
        if not rows:
            epci = await self._epci_code(codes[-1])
            if epci is None:
                raise NoDataError
            codes = [epci]
            rows = await self._indices(codes, today)
        forecast = select_forecast(rows, codes)
        if not forecast:
            raise NoDataError
        current = forecast[0]
        tomorrow = forecast[1] if len(forecast) > 1 else None
        level = int(current["code_qual"])
        return {
            "indice": level,
            "qualificatif": atmo_label(level),
            "date": str(current.get("date_ech"))[:10],
            "zone": {
                "code": current.get("code_zone"),
                "nom": current.get("lib_zone"),
                "type": str(current.get("type_zone") or "").lower(),
            },
            "sous_indices": {
                key: _valid_level(current.get(source_key))
                for key, source_key in _ATMO_SUB_INDICES.items()
            },
            "polluants_dominants": _dominant_pollutants(current, level),
            "demain": (
                {
                    "indice": int(tomorrow["code_qual"]),
                    "qualificatif": atmo_label(int(tomorrow["code_qual"])),
                }
                if tomorrow
                else None
            ),
            "producteur": current.get("source"),
            "origine": "Atmo France (indice ATMO, licence ODbL)",
        }

    async def _indices(self, codes: list[str], since: date) -> list[dict[str, Any]]:
        quoted = ", ".join(f"'{code}'" for code in codes if _ZONE_CODE.fullmatch(code))
        if not quoted:
            return []
        payload = await self._http.get_json(
            "atmo_france",
            _ATMO_WFS_URL,
            params={
                "service": "WFS",
                "version": "2.0.0",
                "request": "GetFeature",
                "typeNames": "ind:ind_atmo_2021",
                "outputFormat": "application/json",
                "count": 20,
                "CQL_FILTER": f"code_zone IN ({quoted}) AND date_ech >= '{since.isoformat()}'",
            },
        )
        return feature_properties(payload)

    async def _episodes(self, ctx: AuditContext) -> dict[str, Any]:
        """Jours d'épisode de pollution observés sur les douze derniers mois dans la zone.

        La plupart des régions ne publient que les jours d'épisode : sans jour « pas de
        dépassement » dans le flux, zéro épisode veut dire « aucun publié », pas « aucun ».
        """
        today = datetime.now(UTC).date()
        start = today - _EPISODE_WINDOW
        department = departement_code(ctx.citycode)
        in_idf = department in _IDF_DEPARTMENTS
        zone_code = _IDF_ZONE[0] if in_idf else department
        # Le flux écrit parfois le département sans son zéro initial (« 8 » : Ardennes).
        codes = (
            sorted({zone_code, zone_code.lstrip("0")}) if _DEPARTMENT.fullmatch(zone_code) else []
        )
        quoted = ", ".join(f"'{code}'" for code in codes)
        where = f"INTERSECTS(the_geom, SRID=4326;POINT({ctx.lon} {ctx.lat}))"
        if quoted:
            where += f" OR code_zone IN ({quoted})"
        payload = await self._http.get_json(
            "atmo_france",
            _ATMO_OWS_URL,
            params={
                "service": "WFS",
                "version": "2.0.0",
                "request": "GetFeature",
                "typeNames": "alrt:alrt",
                "outputFormat": "application/json",
                "propertyName": _EPISODE_FIELDS,
                "count": _EPISODE_MAX_ROWS,
                "CQL_FILTER": (
                    f"date_ech >= '{start.isoformat()}' AND date_ech < '{today.isoformat()}'"
                    f" AND ({where})"
                ),
            },
        )
        if isinstance(payload, dict) and (payload.get("numberMatched") or 0) > _EPISODE_MAX_ROWS:
            logger.warning("Épisodes de %s tronqués à %d lignes", zone_code, _EPISODE_MAX_ROWS)
        rows = [row for row in feature_properties(payload) if _same_zone(row, in_idf=in_idf)]
        days: dict[str, set[str]] = {}
        alert_days: dict[str, set[str]] = {}
        for row in rows:
            level = _EPISODE_LEVELS.get(str(row.get("etat")))
            pollutant = _episode_pollutant(row)
            if level is None or pollutant is None:
                continue
            day = str(row.get("date_ech"))[:10]
            days.setdefault(pollutant, set()).add(day)
            if level == "alerte":
                alert_days.setdefault(pollutant, set()).add(day)
        by_pollutant = [
            {
                "polluant": pollutant,
                "libelle": _ATMO_POLLUTANT_LABELS[pollutant],
                "nb_jours": len(pollutant_days),
                "nb_jours_alerte": len(alert_days.get(pollutant, ())),
            }
            for pollutant, pollutant_days in days.items()
        ]
        first = rows[0] if rows else {}
        return {
            "zone": {
                "code": first.get("code_zone", zone_code if codes else None),
                "nom": first.get("lib_zone"),
            },
            "debut": start.isoformat(),
            "fin": (today - timedelta(days=1)).isoformat(),
            "suivi_quotidien": any(row.get("etat") == _NO_EPISODE for row in rows),
            "nb_jours": len(set().union(*days.values())),
            "nb_jours_alerte": len(set().union(*alert_days.values())),
            "par_polluant": sorted(
                by_pollutant, key=lambda item: (-item["nb_jours"], item["polluant"])
            ),
        }

    async def _epci_code(self, commune_code: str) -> str | None:
        """Intercommunalité de la commune ; son absence ne doit pas faire échouer le bloc."""
        try:
            payload = await self._http.get_json(
                "geo_api", f"{_GEO_COMMUNE_URL}/{commune_code}", params={"fields": "codeEpci"}
            )
        except SourceError:
            return None
        code = payload.get("codeEpci") if isinstance(payload, dict) else None
        return code if isinstance(code, str) else None


def _valid_level(value: Any) -> int | None:
    """Indice entre 1 et 6 ; 0 (absent) et 7 (événement) ne sont pas des niveaux."""
    level = to_float(value)
    if level is None or not _ATMO_MIN <= level <= _ATMO_MAX:
        return None
    return int(level)


def select_forecast(rows: list[dict[str, Any]], codes: list[str]) -> list[dict[str, Any]]:
    """Indices de la zone la plus précise disponible, du jour le plus proche au plus lointain."""
    usable = [row for row in rows if _valid_level(row.get("code_qual")) is not None]
    for code in codes:
        zone_rows = [row for row in usable if row.get("code_zone") == code]
        if zone_rows:
            return sorted(zone_rows, key=lambda row: str(row.get("date_ech")))
    return []


def _same_zone(row: dict[str, Any], *, in_idf: bool) -> bool:
    """Écarte l'homonyme du code « 11 », porté à la fois par l'Aude et l'Île-de-France."""
    if row.get("code_zone") != _IDF_ZONE[0]:
        return True
    return (_plain_upper(row.get("lib_zone")) == _IDF_ZONE[1]) == in_idf


def _plain_upper(value: Any) -> str:
    """Libellé en capitales, sans accents ni espaces autour : « Île-de-France » → ILE-DE-FRANCE."""
    decomposed = unicodedata.normalize("NFKD", str(value or "").strip().upper())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _episode_pollutant(row: dict[str, Any]) -> str | None:
    """Polluant normalisé d'un épisode, par son code puis, à défaut, par son libellé."""
    pollutant = _EPISODE_POLLUTANT_CODES.get(str(row.get("code_pol")))
    if pollutant is not None:
        return pollutant
    label = str(row.get("lib_pol") or "").lower()
    return next((key for word, key in _EPISODE_POLLUTANT_WORDS if word in label), None)


def _dominant_pollutants(row: dict[str, Any], level: int) -> list[str]:
    """Polluants dont le sous-indice atteint l'indice global : ce sont eux qui le déterminent."""
    return [
        _ATMO_POLLUTANT_LABELS[key]
        for key, source_key in _ATMO_SUB_INDICES.items()
        if _valid_level(row.get(source_key)) == level
    ]


# Inventaires territoriaux (format PCAET) : un total « All » et cinq grands secteurs.
_INVENTORY_LAYER = "emissions:emissions_epci"
_EPCI_CODE = re.compile(r"\d{9}", re.ASCII)
_ALL_SECTORS = "All"
_RESIDENTIAL_TERTIARY = "34"
_SECTORS = {
    "5": "Agriculture",
    "219": "Industrie, énergie et déchets",
    "34": "Résidentiel et tertiaire",
    "6": "Transport routier",
    "7": "Autres transports",
}
# clé du rapport -> colonnes de consommation du flux
_ENERGIES = {
    "electricite": ("conso_elec",),
    "gaz": ("conso_gn",),
    "produits_petroliers": ("conso_pp",),
    "bois": ("conso_bois",),
    "reseau_chaleur": ("conso_chaleur",),
    "autres": ("conso_cms", "conso_autres_enr", "conso_autres"),
}
_GES_TREND_FROM = 2018
# Atmo Occitanie ne compte que le scope 1 dans les GES de ses intercommunalités : le repère
# métropolitain, scopes 1 et 2, ne leur est pas comparable.
_SCOPE_ONE_ONLY_AASQA = "76"
# Repère « France métropolitaine », calculé le 2026-10-20 sur les 13 régions métropolitaines
# de emissions:emissions_regions (total pour les émissions, secteur résidentiel-tertiaire pour
# les énergies). À recalculer à chaque nouveau millésime d'inventaire.
_METRO_REFERENCES: dict[int, dict[str, Any]] = {
    2022: {
        "ges_t_par_habitant": 5.73,
        "nox_t_par_km2": 1.212,
        "pm2_5_t_par_km2": 0.328,
        "energie_residentiel_tertiaire": {
            "electricite": 45.9,
            "gaz": 26.9,
            "produits_petroliers": 9.6,
            "bois": 12.5,
            "reseau_chaleur": 4.2,
            "autres": 0.9,
        },
    },
    # Dernier millésime de l'outre-mer : il y est comparé à la métropole de la même année.
    2018: {
        "ges_t_par_habitant": 6.44,
        "nox_t_par_km2": 1.529,
        "pm2_5_t_par_km2": 0.391,
        "energie_residentiel_tertiaire": {
            "electricite": 42.5,
            "gaz": 29.9,
            "produits_petroliers": 11.5,
            "bois": 11.9,
            "reseau_chaleur": 3.7,
            "autres": 0.5,
        },
    },
}


class ClimateAirEnergyProvider:
    """Inventaire des émissions et des consommations d'énergie de l'intercommunalité.

    Publié par Atmo France et les AASQA (ODbL), par millésime, au découpage intercommunal de
    mars 2023 : une intercommunalité créée depuis n'y figure pas. Le total fait foi : il n'est
    jamais recalculé à partir des secteurs, qui manquent ou s'en écartent pour quelques-unes.
    """

    name = "climat_air_energie"

    def __init__(self, http: HttpClient) -> None:
        self._http = http

    async def fetch(self, ctx: AuditContext) -> ProviderData:
        epci = await self._epci(ctx.commune_codes[-1])
        if epci is None:
            raise NoDataError
        payload = await self._http.get_json(
            "atmo_france",
            _ATMO_OWS_URL,
            params={
                "service": "WFS",
                "version": "2.0.0",
                "request": "GetFeature",
                "typeNames": _INVENTORY_LAYER,
                "outputFormat": "application/json",
                "CQL_FILTER": f"code = '{epci['code']}'",
            },
        )
        rows = feature_properties(payload)
        totals = {
            int(row["annee"]): row
            for row in rows
            # Un total nul est un inventaire non communiqué (Martinique), pas un territoire
            # qui n'émet rien.
            if row.get("code_pcaet") == _ALL_SECTORS
            and isinstance(row.get("annee"), int)
            and to_float(row.get("ges"))
        }
        if not totals:
            raise NoDataError
        year = max(totals)
        total = totals[year]
        sectors = {
            str(row.get("code_pcaet")): row
            for row in rows
            if row.get("annee") == year and str(row.get("code_pcaet")) in _SECTORS
        }
        reference = _METRO_REFERENCES.get(year, {})
        if not reference:
            logger.warning("Pas de repère métropolitain pour l'inventaire %d : à calculer", year)
        population, area = to_float(total.get("population")), to_float(total.get("superficie"))
        ges = _per(total.get("ges"), population, 2)
        past = totals.get(_GES_TREND_FROM) if year > _GES_TREND_FROM else None
        past_ges = _per(past.get("ges"), to_float(past.get("population")), 2) if past else None
        return ProviderData(
            data={
                "territoire": epci,
                "millesime": year,
                "version_inventaire": total.get("versioning_inventaire"),
                "producteur": total.get("source"),
                "ges": {
                    "t_par_habitant": ges,
                    "evolution_depuis_2018_pct": (
                        round(100 * (ges - past_ges) / past_ges, 1)
                        if ges is not None and past_ges
                        else None
                    ),
                    "repere_t_par_habitant": (
                        None
                        if total.get("aasqa") == _SCOPE_ONE_ONLY_AASQA
                        else reference.get("ges_t_par_habitant")
                    ),
                },
                **{
                    key: {
                        "t_par_km2": _per(total.get(key.replace("_", "")), area, 3),
                        "secteur_dominant": _dominant_sector(sectors, key.replace("_", "")),
                        "repere_t_par_km2": reference.get(f"{key}_t_par_km2"),
                    }
                    for key in ("nox", "pm2_5")
                },
                "energie_residentiel_tertiaire": _energy_shares(sectors.get(_RESIDENTIAL_TERTIARY)),
                "repere": (
                    {
                        "territoire": "France métropolitaine",
                        "millesime": year,
                        "energie_residentiel_tertiaire": reference["energie_residentiel_tertiaire"],
                    }
                    if reference
                    else None
                ),
                "origine": "Atmo France (inventaires territoriaux, licence ODbL)",
            }
        )

    async def _epci(self, commune_code: str) -> dict[str, str] | None:
        payload = await self._http.get_json(
            "geo_api", f"{_GEO_COMMUNE_URL}/{commune_code}", params={"fields": "epci"}
        )
        epci = payload.get("epci") if isinstance(payload, dict) else None
        if not isinstance(epci, dict) or not _EPCI_CODE.fullmatch(str(epci.get("code"))):
            return None
        return {"code": str(epci["code"]), "nom": str(epci.get("nom") or "")}


def _per(value: Any, base: float | None, digits: int) -> float | None:
    amount = to_float(value)
    return round(amount / base, digits) if amount is not None and base else None


def _dominant_sector(sectors: dict[str, dict[str, Any]], column: str) -> str | None:
    """Secteur qui émet le plus ; aucun quand l'inventaire n'est publié qu'au total."""
    amounts = {code: to_float(row.get(column)) for code, row in sectors.items()}
    ranked = [(amount, code) for code, amount in amounts.items() if amount]
    return _SECTORS[max(ranked)[1]] if ranked else None


def _energy_shares(row: dict[str, Any] | None) -> dict[str, float] | None:
    """Parts de chaque énergie, en %, dans la consommation du résidentiel et du tertiaire.

    Seules les parts sont rendues : l'unité des consommations n'est pas documentée.
    """
    total = to_float(row.get("conso")) if row else None
    if not row or not total:
        return None
    return {
        key: round(100 * sum(to_float(row.get(column)) or 0.0 for column in columns) / total, 1)
        for key, columns in _ENERGIES.items()
    }


class SunlightProvider:
    """Score d'ensoleillement à partir du relief environnant (IGN RGE Alti).

    Seul le relief est pris en compte : les bâtiments voisins ne sont pas modélisés.
    """

    name = "ensoleillement"

    def __init__(self, http: HttpClient) -> None:
        self._http = http

    async def fetch(self, ctx: AuditContext) -> ProviderData:
        points = [(ctx.lat, ctx.lon)] + [
            destination(ctx.lat, ctx.lon, azimuth, distance)
            for azimuth in AZIMUTHS_DEG
            for distance in _RING_DISTANCES_M
        ]
        altitudes = await self._altitudes(points)
        origin, ring = altitudes[0], altitudes[1:]
        width = len(_RING_DISTANCES_M)
        # Un point hors emprise (mer, étranger) ne masque rien : on le ramène à l'origine.
        rings = [
            [
                altitude if altitude > _NO_DATA_ALTITUDE else origin
                for altitude in ring[i : i + width]
            ]
            for i in range(0, len(ring), width)
        ]
        profile = horizon_profile(origin, rings, _RING_DISTANCES_M)
        mask = dict(zip(AZIMUTH_LABELS, profile, strict=True))
        return ProviderData(
            data={
                "altitude_m": round(origin, 1),
                "score": sunlight_scores(ctx.lat, profile),
                "masque_relief_deg": mask,
                "synthese": relief_summary(mask),
                "methode": "relief seul (RGE Alti), hors bâtiments voisins",
            }
        )

    async def _altitudes(self, points: list[tuple[float, float]]) -> list[float]:
        payload: Any = await self._http.get_json(
            "ign_alti",
            _ALTI_URL,
            params={
                "lat": "|".join(str(lat) for lat, _ in points),
                "lon": "|".join(str(lon) for _, lon in points),
                "resource": "ign_rge_alti_wld",
                "zonly": "true",
            },
        )
        elevations = payload.get("elevations") if isinstance(payload, dict) else None
        if not isinstance(elevations, list) or len(elevations) != len(points):
            raise SourceError("invalid_response", "elevations", transient=False)
        altitudes = [float(value) for value in elevations]
        if altitudes[0] <= _NO_DATA_ALTITUDE:
            raise SourceError("invalid_response", "origin outside coverage", transient=False)
        return altitudes
