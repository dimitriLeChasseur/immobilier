"""Version « teaser » d'un rapport : les valeurs à forte valeur sont masquées côté serveur.

Le masquage est fait ici, avant toute sérialisation : un visiteur qui n'a pas acheté l'audit
ne reçoit jamais la donnée, ni dans la page, ni dans le trafic réseau. Les clés du JSON sont
conservées pour que l'interface garde sa structure.
"""

from collections.abc import Callable
from typing import Any

from app.schemas.audit import AuditReport, Finding, ReportMeta, SourceResult, Synthesis

LOCKED = "***LOCKED***"

# Liste blanche par source : seules ces clés restent lisibles. Toute autre clé, y compris
# celles qui seront ajoutées plus tard, est masquée par défaut.
_CLEAR_KEYS: dict[str, frozenset[str]] = {
    # Accroches : prouvent que le quartier a bien été analysé, sans livrer le résultat.
    "dvf": frozenset({"nb_ventes", "rayon_m", "sections_interrogees", "perimetre", "rue"}),
    "qualite_air": frozenset(
        {
            "indice",
            "qualificatif",
            "date",
            "zone",
            "producteur",
            "origine",
            "demain",
            "sous_indices",
            "polluants_dominants",
        }
    ),
    "georisques": frozenset({"risques", "catastrophes_naturelles"}),
    "reseau_mobile": frozenset({"nb_sites", "rayon_m", "liste_tronquee"}),
    "permis_construire": frozenset({"nb_permis", "rayon_m"}),
    "dpe": frozenset(
        {"nb_dpe_total", "nb_dpe_analyses", "rayon_m", "rayon_effectif_m", "perimetre"}
    ),
    "proximite": frozenset({"rayon_m", "methode_temps"}),
    "ecoles": frozenset({"rayon_m"}),
    "copropriete": frozenset({"niveau", "territoire", "millesime", "origine"}),
    "ensoleillement": frozenset({"methode"}),
    "bruit": frozenset({"indice"}),
    "marche_locatif": frozenset({"permis_de_louer"}),
    "cadastre": frozenset(),
    "urbanisme": frozenset(),
}


# Chiffres de la commune, déjà publiés en clair sur les fiches communales : les masquer
# dans l'aperçu d'une adresse ne protégerait rien.
_OPEN_SOURCES = frozenset({"loyers", "taxe_fonciere", "delinquance", "connectivite"})


def _poi_counts(categories: Any) -> Any:
    """Proximité : le nombre d'équipements reste visible, le plus proche est masqué."""
    if not isinstance(categories, dict):
        return LOCKED
    return {
        name: {"nb": stats.get("nb"), "plus_proche": LOCKED} if isinstance(stats, dict) else LOCKED
        for name, stats in categories.items()
    }


# Clés partiellement lisibles : (source, clé) -> transformation de la valeur.
_PARTIAL: dict[tuple[str, str], Callable[[Any], Any]] = {
    ("proximite", "categories"): _poi_counts,
}


def mask_data(source: str, data: dict[str, Any]) -> dict[str, Any]:
    if source in _OPEN_SOURCES:
        return data
    clear = _CLEAR_KEYS.get(source, frozenset())
    masked: dict[str, Any] = {}
    for key, value in data.items():
        if key in clear:
            masked[key] = value
        elif (source, key) in _PARTIAL:
            masked[key] = _PARTIAL[(source, key)](value)
        else:
            masked[key] = LOCKED
    return masked


def mask_result(source: str, result: SourceResult) -> SourceResult:
    """Résultat d'une source tel qu'un visiteur sans accès peut le recevoir."""
    if result.data is None:
        return result
    return result.model_copy(update={"data": mask_data(source, result.data)})


def _mask_findings(findings: list[Finding]) -> list[Finding]:
    """Le nombre de constats et leur thème servent d'accroche ; leur contenu est réservé."""
    return [Finding(theme=item.theme, titre=LOCKED, detail=LOCKED) for item in findings]


def mask_meta(meta: ReportMeta) -> ReportMeta:
    synthesis = meta.synthese
    if synthesis is not None:
        synthesis = Synthesis(
            alertes=_mask_findings(synthesis.alertes),
            points_forts=_mask_findings(synthesis.points_forts),
        )
    return meta.model_copy(update={"access": "teaser", "synthese": synthesis})


def mask_report(report: AuditReport) -> AuditReport:
    return report.model_copy(
        update={
            "sources": {name: mask_result(name, result) for name, result in report.sources.items()},
            "meta": mask_meta(report.meta),
        }
    )
