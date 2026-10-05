"""Encadrement des loyers : territoires où le loyer est plafonné par un loyer de référence.

Aucun jeu de données national n'existe : la liste ci-dessous reprend la fiche officielle
https://www.service-public.gouv.fr/particuliers/vosdroits/F1314 (vérifiée le 1er août 2026).
Elle est à relire à chaque nouveau décret.
"""

from dataclasses import dataclass

VERIFIED_ON = "2026-08-01"

_EST_ENSEMBLE = ("93006", "93008", "93010", "93045", "93048", "93053", "93055", "93061", "93063")
_PLAINE_COMMUNE = (
    "93001",
    "93027",
    "93031",
    "93039",
    "93059",
    "93066",
    "93070",
    "93072",
    "93079",
)

# Code INSEE de la commune -> territoire d'application.
_FULLY_COVERED: dict[str, str] = {
    "75056": "Paris",
    "33063": "Bordeaux",
    # Hellemmes et Lomme sont des communes associées à Lille (même code INSEE).
    "59350": "Lille, Hellemmes et Lomme",
    "69123": "Lyon",
    "69266": "Villeurbanne",
    "34172": "Montpellier",
    **dict.fromkeys(_EST_ENSEMBLE, "Est Ensemble"),
    **dict.fromkeys(_PLAINE_COMMUNE, "Plaine Commune"),
}

# Intercommunalités (SIREN) dont une partie seulement des communes est concernée.
_PARTLY_COVERED_EPCI: dict[str, str] = {
    "200040715": "Grenoble-Alpes Métropole",
    "200067106": "Communauté d'agglomération du Pays Basque",
}


@dataclass(frozen=True, slots=True)
class RentControl:
    # "oui", "partiel" (certaines communes de l'intercommunalité seulement) ou "non".
    status: str
    territory: str | None = None


def rent_control(commune_codes: list[str], epci_code: str | None) -> RentControl:
    for code in commune_codes:
        territory = _FULLY_COVERED.get(code)
        if territory is not None:
            return RentControl("oui", territory)
    partial = _PARTLY_COVERED_EPCI.get(epci_code or "")
    return RentControl("partiel", partial) if partial else RentControl("non")
