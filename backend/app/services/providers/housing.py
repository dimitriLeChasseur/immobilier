"""Contexte locatif et coûts d'usage : occupation des logements, règles locales, connectivité."""

import asyncio
from typing import Any

from app.core.errors import NoDataError, RepositoryError, SourceError
from app.core.geo import haversine_m
from app.core.http import HttpClient
from app.repositories.reference import ReferenceRepository
from app.services.insights import noise_message
from app.services.iris import IrisLocator
from app.services.providers.base import AuditContext, ProviderData, as_rows, gather_parts
from app.services.providers.rental_rules import VERIFIED_ON, rent_control

_GEO_COMMUNE_URL = "https://geo.api.gouv.fr/communes"

# Charges de copropriété annuelles au m² (annonces immobilières, 2018, licence CC-BY-SA) :
# https://www.data.gouv.fr/datasets/charges-de-copropriete-dans-toute-la-france
# Seule source ouverte au m² : ancienne, elle ne donne qu'un ordre de grandeur.
_COPRO_YEAR = 2018
_COPRO_BY_CITY: dict[str, tuple[str, float]] = {
    "75056": ("Paris", 40.28),
    "69123": ("Lyon", 22.45),
    "13055": ("Marseille", 24.38),
    "33063": ("Bordeaux", 18.82),
    "06088": ("Nice", 32.05),
    "31555": ("Toulouse", 21.45),
    "44109": ("Nantes", 20.72),
    "67482": ("Strasbourg", 24.14),
    "34172": ("Montpellier", 22.12),
    "35238": ("Rennes", 21.93),
    "59350": ("Lille", 25.45),
}
_COPRO_BY_REGION: dict[str, float] = {
    "Pays de la Loire": 20.06,
    "Bretagne": 16.41,
    "Occitanie": 19.98,
    "Auvergne-Rhône-Alpes": 23.04,
    "Île-de-France": 34.20,
    "Provence-Alpes-Côte d'Azur": 27.38,
    "Grand Est": 21.21,
    "Bourgogne-Franche-Comté": 21.72,
    "Normandie": 24.96,
    "Hauts-de-France": 23.74,
    "Nouvelle-Aquitaine": 19.85,
    "Corse": 16.42,
    "Centre-Val de Loire": 24.70,
}
_OVERSEAS_CHARGES = 19.19
_OVERSEAS_REGIONS = frozenset({"Guadeloupe", "Martinique", "Guyane", "La Réunion", "Mayotte"})


def _share(part: Any, total: Any) -> float | None:
    if not isinstance(part, int) or not isinstance(total, int) or total <= 0:
        return None
    return round(100 * part / total, 1)


_TABULAR_URL = "https://tabular-api.data.gouv.fr/api/resources"
# Zones où l'offre de logements est jugée insuffisante par l'arrêté de zonage.
_TENSE_ZONES = frozenset({"Abis", "A bis", "A", "B1"})


class RentalMarketProvider:
    """Occupation des logements du quartier (IRIS) et encadrement des loyers."""

    name = "marche_locatif"

    def __init__(
        self,
        http: HttpClient,
        repository: ReferenceRepository,
        *,
        abc_resource_id: str | None = None,
        iris: IrisLocator | None = None,
    ) -> None:
        self._http = http
        self._repository = repository
        self._abc_resource_id = abc_resource_id
        self._iris = iris or IrisLocator(http)

    async def fetch(self, ctx: AuditContext) -> ProviderData:
        data, missing = await gather_parts(
            {
                "occupation": self._occupancy(ctx),
                "encadrement_loyers": self._rent_control(ctx),
                "zonage_abc": self._abc_zone(ctx),
                "zone_tendue": self._tense_zone(ctx),
            }
        )
        # Aucun recensement national des communes ayant instauré un permis de louer.
        data["permis_de_louer"] = {"statut": "inconnu"}
        return ProviderData(data=data, missing=missing)

    async def _tense_zone(self, ctx: AuditContext) -> dict[str, Any] | None:
        """Classement au zonage de la taxe sur les logements vacants (« zone tendue »).

        None si la commune ne figure pas dans la liste ingérée.
        """
        try:
            zone = await self._repository.tense_zone(ctx.commune_codes)
        except RepositoryError as exc:
            raise SourceError("http_error", str(exc)) from exc
        if zone is None:
            return None
        category = zone["categorie"]
        return {
            "categorie": category,
            "tendue": category != "non_tendue",
            "reference": zone["reference"],
        }

    async def _abc_zone(self, ctx: AuditContext) -> dict[str, Any] | None:
        """Zone A bis, A, B1, B2 ou C de la commune : tension du marché du logement."""
        if self._abc_resource_id is None:
            return None
        url = f"{_TABULAR_URL}/{self._abc_resource_id}/data/"
        for code in reversed(ctx.commune_codes):
            payload = await self._http.get_json(
                "data_gouv_tabular", url, params={"CODGEO__exact": code, "page_size": 1}
            )
            for row in as_rows(payload, "data"):
                # L'intitulé de la colonne porte la date d'entrée en vigueur de la liste.
                for column, zone in row.items():
                    if column.startswith("Zonage ABC") and isinstance(zone, str):
                        return {"zone": zone.strip(), "tendu": zone.strip() in _TENSE_ZONES}
        return None

    async def _occupancy(self, ctx: AuditContext) -> dict[str, Any] | None:
        iris = await self._iris.locate(ctx.lat, ctx.lon)
        if iris is None:
            return None
        try:
            row = await self._repository.iris_housing(iris.code)
        except RepositoryError as exc:
            raise SourceError("http_error", str(exc)) from exc
        if row is None:
            return None
        main_homes, dwellings = row["residences_principales"], row["logements"]
        return {
            "iris": {"code": iris.code, "nom": iris.name},
            "annee": row["annee"],
            "logements": dwellings,
            "part_proprietaires_pct": _share(row["proprietaires"], main_homes),
            "part_locataires_pct": _share(row["locataires"], main_homes),
            "part_locataires_hlm_pct": _share(row["locataires_hlm"], main_homes),
            "part_vacants_pct": _share(row["logements_vacants"], dwellings),
            "part_residences_secondaires_pct": _share(row["residences_secondaires"], dwellings),
        }

    async def _rent_control(self, ctx: AuditContext) -> dict[str, Any]:
        commune_code = ctx.commune_codes[-1]
        payload = await self._http.get_json(
            "geo_api", f"{_GEO_COMMUNE_URL}/{commune_code}", params={"fields": "codeEpci"}
        )
        epci = payload.get("codeEpci") if isinstance(payload, dict) else None
        rule = rent_control(ctx.commune_codes, epci if isinstance(epci, str) else None)
        return {"statut": rule.status, "territoire": rule.territory, "verifie_le": VERIFIED_ON}


class ConnectivityProvider:
    """Part des locaux de la commune raccordables à la fibre (ARCEP)."""

    name = "connectivite"

    def __init__(self, repository: ReferenceRepository) -> None:
        self._repository = repository

    async def fetch(self, ctx: AuditContext) -> ProviderData:
        try:
            row = await self._repository.connectivity(ctx.commune_codes)
        except RepositoryError as exc:
            raise SourceError("http_error", str(exc)) from exc
        if row is None:
            raise NoDataError
        premises = row["nb_locaux"]
        return ProviderData(
            data={
                "niveau": "commune",
                "date_donnees": row["date_donnees"],
                "nb_locaux": premises,
                "part_fibre_pct": _share(row["eligibles_fibre"], premises),
                "part_cable_pct": _share(row["eligibles_cable"], premises),
                "part_4g_fixe_pct": _share(row["eligibles_4g_fixe"], premises),
            }
        )


class CondoChargesProvider:
    """Ordre de grandeur des charges de copropriété (moyenne de la ville ou de la région)."""

    name = "copropriete"

    async def fetch(self, ctx: AuditContext) -> ProviderData:
        # Table embarquée : aucune E/S, mais le contrat Provider est asynchrone.
        await asyncio.sleep(0)
        level, territory, charges = self._lookup(ctx)
        return ProviderData(
            data={
                "charges_m2_an": charges,
                "niveau": level,
                "territoire": territory,
                "millesime": _COPRO_YEAR,
                "origine": "Annonces immobilières (MeilleureCopro, data.gouv.fr)",
            }
        )

    @staticmethod
    def _lookup(ctx: AuditContext) -> tuple[str, str, float]:
        for code in ctx.commune_codes:
            if code in _COPRO_BY_CITY:
                city, charges = _COPRO_BY_CITY[code]
                return "ville", city, charges
        region = ctx.region or ""
        if region in _COPRO_BY_REGION:
            return "region", region, _COPRO_BY_REGION[region]
        if region in _OVERSEAS_REGIONS:
            return "region", "Outre-mer", _OVERSEAS_CHARGES
        raise NoDataError


_ANFR_URL = "https://data.anfr.fr/d4c/api/records/1.0/search/"
_ANFR_DATASET = "observatoire_2g_3g_4g"
_ANFR_RADIUS_M = 1000
_ANFR_ROWS = 500
# Un émetteur 5G déployé est déclaré « techniquement opérationnel », les autres « en service ».
_ANFR_ACTIVE = frozenset({"En service", "Techniquement opérationnel"})
_GENERATIONS = ("2G", "3G", "4G", "5G")
_OPERATOR_LABELS = {"SFR": "SFR", "SRR": "SRR"}
_NOISE_CLASS_WIDTH_DB = 5
_NOISE_TOP_CLASS_DB = 75


def _antenna_position(record: dict[str, Any]) -> tuple[float, float] | None:
    """(lat, lon) d'un enregistrement ANFR, dont le champ est « 47.47 , -0.55 »."""
    parts = str(record.get("coordonnees") or "").split(",")
    try:
        return float(parts[0]), float(parts[1])
    except (IndexError, ValueError):
        return None


class MobileNetworkProvider:
    """Antennes-relais actives autour du point, par opérateur et génération (ANFR, Cartoradio)."""

    name = "reseau_mobile"

    def __init__(self, http: HttpClient) -> None:
        self._http = http

    async def fetch(self, ctx: AuditContext) -> ProviderData:
        payload = await self._http.get_json(
            "anfr",
            _ANFR_URL,
            params={
                "dataset": _ANFR_DATASET,
                "rows": _ANFR_ROWS,
                "geofilter.distance": f"{ctx.lat},{ctx.lon},{_ANFR_RADIUS_M}",
            },
        )
        records = [
            fields
            for row in as_rows(payload, "records")
            if isinstance(fields := row.get("fields"), dict)
            and fields.get("statut") in _ANFR_ACTIVE
        ]
        operators = summarize_antennas(records, ctx)
        if not operators:
            raise NoDataError
        return ProviderData(
            data={
                "rayon_m": _ANFR_RADIUS_M,
                "nb_sites": len({record.get("sup_id") for record in records}),
                "operateurs": operators,
                "operateurs_5g": [op["nom"] for op in operators if "5G" in op["generations"]],
                "liste_tronquee": int(payload.get("nhits") or 0) > _ANFR_ROWS,
            }
        )


def summarize_antennas(records: list[dict[str, Any]], ctx: AuditContext) -> list[dict[str, Any]]:
    """Par opérateur : générations disponibles, nombre de sites et distance du plus proche."""
    by_operator: dict[str, dict[str, Any]] = {}
    for record in records:
        name, generation = record.get("adm_lb_nom"), record.get("generation")
        position = _antenna_position(record)
        if not isinstance(name, str) or generation not in _GENERATIONS or position is None:
            continue
        entry = by_operator.setdefault(name, {"generations": set(), "sites": {}})
        entry["generations"].add(generation)
        distance = round(haversine_m(ctx.lat, ctx.lon, *position))
        site = record.get("sup_id")
        entry["sites"][site] = min(distance, entry["sites"].get(site, distance))
    return [
        {
            "nom": _OPERATOR_LABELS.get(name, name.title()),
            "generations": [g for g in _GENERATIONS if g in entry["generations"]],
            "nb_sites": len(entry["sites"]),
            "site_le_plus_proche_m": min(entry["sites"].values()),
        }
        for name, entry in sorted(by_operator.items())
    ]


class NoiseProvider:
    """Exposition au bruit des grandes infrastructures (cartes de bruit stratégiques, Lden)."""

    name = "bruit"

    def __init__(self, repository: ReferenceRepository) -> None:
        self._repository = repository

    async def _levels(self, ctx: AuditContext) -> list[dict[str, Any]]:
        """Classes de bruit au point, ou les plus fortes le long de la voie en mode « rue »."""
        if ctx.street is not None:
            return await self._repository.noise_levels_along(ctx.street.points)
        return await self._repository.noise_levels(ctx.lat, ctx.lon)

    async def fetch(self, ctx: AuditContext) -> ProviderData:
        try:
            covered = await self._repository.noise_coverage(ctx.lat, ctx.lon)
            levels = await self._levels(ctx) if covered else []
        except RepositoryError as exc:
            raise SourceError("http_error", str(exc)) from exc
        if not covered:
            # Aucune carte ingérée pour ce territoire : on ne peut rien affirmer.
            raise NoDataError
        max_db = max((level["db_min"] for level in levels), default=None)
        message = noise_message(max_db, covered)
        street: dict[str, Any] = {}
        if ctx.street is not None:
            exposed = levels[0]["nb_exposes"] if levels else 0
            share = round(100 * exposed / len(ctx.street.points))
            street = {"perimetre": "rue", "part_rue_pct": share}
            if levels:
                message += f" {share} % des numéros de la rue sont en zone de bruit."
        return ProviderData(
            data={
                **street,
                "indice": "Lden",
                "niveau_max_db": max_db,
                "sources": [
                    {
                        "infrastructure": level["infrastructure"],
                        "db_min": level["db_min"],
                        "db_max": None
                        if level["db_min"] >= _NOISE_TOP_CLASS_DB
                        else level["db_min"] + _NOISE_CLASS_WIDTH_DB,
                    }
                    for level in levels
                ],
                "infrastructures_couvertes": covered,
                "message": message,
            }
        )
