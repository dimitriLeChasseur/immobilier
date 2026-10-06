"""BDNB (CSTB) : caractéristiques du bâtiment situé à l'adresse, et sa copropriété.

La Base de données nationale des bâtiments croise fichiers fonciers, DPE, registre national
des copropriétés et monuments historiques. Elle est interrogée par l'identifiant BAN de
l'adresse, résolu côté serveur ; une voie entière n'a pas de bâtiment unique.
"""

from typing import Any

from app.core.errors import NoDataError
from app.core.http import HttpClient
from app.services.providers.base import AuditContext, ProviderData, gather_parts, to_float

_BASE_URL = "https://api.bdnb.io/v1/bdnb/donnees"
_SOURCE = "bdnb"
_DPE_LABELS = "abcdefg"
_BUILDING_FIELDS = ",".join(
    [
        "libelle_adr_principale_ban",
        "l_libelle_adr",
        "annee_construction",
        "usage_niveau_1_txt",
        "nb_niveau",
        "hauteur_mean",
        "nb_log",
        "mat_mur_txt",
        "mat_toit_txt",
        "type_energie_chauffage",
        "type_installation_chauffage",
        "classe_bilan_dpe",
        *(f"nb_classe_bilan_dpe_{label}" for label in _DPE_LABELS),
        "perimetre_bat_historique",
        "denomination_monument_historique",
        "distance_monument_historique",
        "fiabilite_cr_adr_niv_1",
    ]
)
# Valeurs par lesquelles la base signale qu'elle ne sait pas.
_UNKNOWN = frozenset({"", "INDETERMINE", "INCONNU", "AUTRES"})


def _known(value: Any) -> str | None:
    """Libellé exploitable, None si la base ne connaît pas la valeur."""
    if not isinstance(value, str) or value.strip().upper() in _UNKNOWN:
        return None
    return value.strip().capitalize()


# La base publie les énergies sans accent.
_ENERGIES = {
    "electricite": "Électricité",
    "reseau de chaleur": "Réseau de chaleur",
    "gaz": "Gaz",
    "fioul": "Fioul",
    "bois": "Bois",
}


def _energy(value: Any) -> str | None:
    label = _known(value)
    return _ENERGIES.get(label.lower(), label) if label else None


def _whole(value: Any) -> int | None:
    number = to_float(value)
    return round(number) if number is not None else None


def _rows(payload: Any) -> list[dict[str, Any]]:
    return [row for row in payload if isinstance(row, dict)] if isinstance(payload, list) else []


def _first(values: Any) -> Any:
    return values[0] if isinstance(values, list) and values else None


class BuildingProvider:
    name = "batiment"

    def __init__(self, http: HttpClient) -> None:
        self._http = http

    async def fetch(self, ctx: AuditContext) -> ProviderData:
        if ctx.street is not None or not ctx.address_id:
            raise NoDataError
        links = _rows(
            await self._http.get_json(
                _SOURCE,
                f"{_BASE_URL}/rel_batiment_groupe_adresse",
                params={
                    "cle_interop_adr": f"eq.{ctx.address_id}",
                    "select": "batiment_groupe_id",
                    "limit": 1,
                },
            )
        )
        if not links or not isinstance(links[0].get("batiment_groupe_id"), str):
            # Adresse non rattachée à un bâtiment dans la base.
            raise NoDataError
        group: dict[str, str | int | float] = {
            "batiment_groupe_id": f"eq.{links[0]['batiment_groupe_id']}",
            "limit": 1,
        }
        parts, missing = await gather_parts(
            {
                "batiment": self._http.get_json(
                    _SOURCE,
                    f"{_BASE_URL}/batiment_groupe_complet",
                    params={**group, "select": _BUILDING_FIELDS},
                ),
                "copropriete": self._http.get_json(
                    _SOURCE, f"{_BASE_URL}/batiment_groupe_rnc", params=group
                ),
            }
        )
        buildings = _rows(parts.get("batiment"))
        if "batiment" in parts and not buildings:
            raise NoDataError
        data = _building(buildings[0]) if buildings else {}
        if "copropriete" in parts:
            data["copropriete"] = _condominium(_rows(parts["copropriete"]))
        data["origine"] = "Base de données nationale des bâtiments (CSTB)"
        return ProviderData(data=data, missing=missing)


def _building(row: dict[str, Any]) -> dict[str, Any]:
    addresses = row.get("l_libelle_adr")
    labels = {
        label.upper(): count
        for label in _DPE_LABELS
        if (count := _whole(row.get(f"nb_classe_bilan_dpe_{label}")))
    }
    return {
        "adresse": row.get("libelle_adr_principale_ban"),
        # Un même bâtiment peut porter plusieurs adresses (angle de rues, entrées multiples).
        "nb_adresses": len(addresses) if isinstance(addresses, list) else None,
        "annee_construction": _whole(row.get("annee_construction")),
        "usage": _known(row.get("usage_niveau_1_txt")),
        "nb_niveaux": _whole(row.get("nb_niveau")),
        "hauteur_m": _whole(row.get("hauteur_mean")),
        "nb_logements": _whole(row.get("nb_log")),
        "materiaux": {
            "murs": _known(row.get("mat_mur_txt")),
            "toit": _known(row.get("mat_toit_txt")),
        },
        "chauffage": {
            "energie": _energy(row.get("type_energie_chauffage")),
            "installation": _known(row.get("type_installation_chauffage")),
        },
        "dpe": {"classe": row.get("classe_bilan_dpe"), "repartition": labels},
        "monument_historique": {
            "dans_perimetre": bool(row.get("perimetre_bat_historique")),
            "nom": row.get("denomination_monument_historique"),
            "distance_m": _whole(row.get("distance_monument_historique")),
        },
        "fiabilite_adresse": row.get("fiabilite_cr_adr_niv_1"),
    }


def _condominium(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Copropriété immatriculée au registre national, None si le bâtiment n'en a pas."""
    if not rows:
        return None
    row = rows[0]
    return {
        "nom": _first(row.get("l_nom_copro")),
        "immatriculation": row.get("numero_immat_principal"),
        "nb_lots": _whole(row.get("nb_lot_tot")),
        "nb_logements": _whole(row.get("nb_log")),
        "nb_lots_stationnement": _whole(row.get("nb_lot_garpark")),
        "nb_lots_tertiaires": _whole(row.get("nb_lot_tertiaire")),
        "annee_construction": _whole(_first(row.get("l_annee_construction"))),
    }
