"""Collège public de secteur d'une adresse, d'après la carte scolaire.

La carte donne un collège par commune ou, dans les communes partagées entre plusieurs
collèges, par tronçon de voie (numéros de début et de fin, côté pair ou impair).
"""

from collections.abc import Mapping, Sequence
from typing import Any

# Statuts rendus avec la liste des collèges retenus.
ADDRESS, STREET, COMMUNE, UNKNOWN, NOT_COVERED = (
    "adresse",
    "voie",
    "commune",
    "indetermine",
    "non_couvert",
)


def _covers(row: Mapping[str, Any], number: int) -> bool:
    """Vrai si le tronçon contient ce numéro, parité comprise."""
    first, last = row.get("numero_debut"), row.get("numero_fin")
    if first is not None and number < first:
        return False
    if last is not None and number > last:
        return False
    parity = row.get("parite")
    if parity == "P":
        return number % 2 == 0
    if parity == "I":
        return number % 2 == 1
    return True


def _unique(codes: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(codes))


def resolve_sector(
    rows: Sequence[Mapping[str, Any]], nb_colleges: int, number: int | None
) -> tuple[str, list[str]]:
    """(statut, identifiants des collèges) à partir des lignes de la carte pour une voie.

    - « commune » : toute la commune relève du même secteur ;
    - « adresse » : le numéro tombe dans un tronçon de la voie ;
    - « voie » : la voie est connue mais pas le numéro, ou il sort des tronçons décrits :
      les collèges de toute la voie sont rendus ;
    - « indetermine » : la commune figure sur la carte, pas cette voie ;
    - « non_couvert » : la commune est absente de la carte.
    """
    whole_commune = _unique([row["uai"] for row in rows if row.get("secteur_unique")])
    if whole_commune:
        return COMMUNE, whole_commune
    if not rows:
        return (UNKNOWN if nb_colleges else NOT_COVERED), []
    if number is not None:
        matching = _unique([row["uai"] for row in rows if _covers(row, number)])
        if matching:
            return ADDRESS, matching
    return STREET, _unique([row["uai"] for row in rows])
