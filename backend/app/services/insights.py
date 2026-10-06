"""Règles métier : traduction des mesures brutes en constats et recommandations lisibles.

Ces textes font partie du rapport (API, PDF, interface) : ils vivent dans la couche Service
pour que tous les supports disent la même chose.
"""

from collections.abc import Mapping, Sequence
from typing import Any

_CLAY_SENSITIVE_FROM = 2
_RADON_MAX = 3
_RADON_MEDIUM = 2
_SEISMIC_REGULATED_FROM = 3

CLAY_ADVICE = (
    "Sol sensible : recherchez des fissures sur les façades. "
    "Étude de sol exigée pour terrain à bâtir."
)
RADON_MAX_ADVICE = "Niveau maximal maîtrisable : aérez chaque jour, posez un dosimètre en hiver."
RADON_MEDIUM_ADVICE = "Une ventilation en bon état suffit le plus souvent."
# L'atlas n'est qu'un inventaire : son silence ne vaut pas absence de risque.
FLOOD_UNLISTED_ADVICE = (
    "Seul l'atlas des zones inondables est consulté ici. Il ne couvre ni les plans de "
    "prévention (PPRI), ni les remontées de nappe, ni le ruissellement : demandez l'état "
    "des risques au vendeur ou éditez-le sur georisques.gouv.fr."
)
FLOOD_ADVICE = (
    "Demandez l'état des risques au vendeur et consultez le plan de prévention (PPRI) : "
    "il peut limiter les travaux et peser sur l'assurance."
)
SEISMIC_ADVICE = (
    "Des règles de construction parasismique s'appliquent aux bâtiments neufs et aux gros travaux."
)

# Part des diagnostics E, F ou G au-delà de laquelle le parc voisin est jugé énergivore.
POOR_ENERGY_THRESHOLD_PCT = 40.0
_POOR_ENERGY_LABELS = ("E", "F", "G")
POOR_ENERGY_MESSAGE = (
    "Plus de 40 % des logements voisins sont classés E, F ou G : levier de négociation fort, "
    "ces étiquettes étant visées par les interdictions de location (G depuis 2025, F en 2028, "
    "E en 2034)."
)

# Directions d'où vient le soleil en France métropolitaine, de l'est à l'ouest par le sud.
_SUN_DIRECTIONS: dict[str, str] = {
    "E": "à l'est",
    "SE": "au sud-est",
    "S": "au sud",
    "SO": "au sud-ouest",
    "O": "à l'ouest",
}
_OPEN_HORIZON_DEG = 5.0
OPEN_HORIZON_SUMMARY = (
    "Horizon dégagé de l'est à l'ouest : le relief ne fait pratiquement pas d'ombre, "
    "été comme hiver."
)

_NOISE_KINDS = {
    "route": "routières",
    "fer": "ferroviaires",
    "air": "aéroportuaires",
    "industrie": "industrielles",
}
# Sources de bruit dont l'absence de carte doit être dite : les deux plus répandues.
_NOISE_EXPECTED = {"route": "routier", "fer": "ferroviaire"}
_NOISE_MESSAGES: tuple[tuple[int, str], ...] = (
    (
        70,
        "Exposition très forte : au-delà des valeurs limites réglementaires. "
        "Vérifiez l'isolation acoustique et l'orientation des pièces de vie.",
    ),
    (
        65,
        "Exposition forte : gêne probable fenêtres ouvertes. "
        "Visitez aux heures de pointe et vérifiez le vitrage.",
    ),
    (55, "Exposition modérée : bruit de fond perceptible, à apprécier lors d'une visite."),
)


def _level(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def risk_recommendations(risks: Mapping[str, Any]) -> dict[str, str]:
    """Recommandation par risque, uniquement quand le niveau la justifie."""
    advice: dict[str, str] = {}
    clay = _level((risks.get("argiles") or {}).get("code"))
    if clay is not None and clay >= _CLAY_SENSITIVE_FROM:
        advice["argiles"] = CLAY_ADVICE
    radon = _level((risks.get("radon") or {}).get("classe_potentiel"))
    if radon == _RADON_MAX:
        advice["radon"] = RADON_MAX_ADVICE
    elif radon == _RADON_MEDIUM:
        advice["radon"] = RADON_MEDIUM_ADVICE
    flood = risks.get("inondation")
    if flood is not None:
        advice["inondation"] = FLOOD_ADVICE if flood.get("concerne") else FLOOD_UNLISTED_ADVICE
    seismic = _level((risks.get("sismicite") or {}).get("code"))
    if seismic is not None and seismic >= _SEISMIC_REGULATED_FROM:
        advice["sismicite"] = SEISMIC_ADVICE
    return advice


def energy_assessment(distribution: Mapping[str, int]) -> dict[str, Any]:
    """Part des étiquettes E, F, G et signal de négociation associé."""
    total = sum(distribution.values())
    poor = sum(distribution.get(label, 0) for label in _POOR_ENERGY_LABELS)
    share = round(100 * poor / total, 1) if total else None
    leverage = share is not None and share > POOR_ENERGY_THRESHOLD_PCT
    return {
        "part_efg_pct": share,
        "levier_negociation": leverage,
        "message": POOR_ENERGY_MESSAGE if leverage else None,
    }


def relief_summary(mask_deg: Mapping[str, float]) -> str:
    """Exposition au soleil décrite en une phrase, d'après la hauteur du relief par direction."""
    heights = {direction: float(mask_deg.get(direction, 0.0)) for direction in _SUN_DIRECTIONS}
    highest = max(heights, key=lambda direction: heights[direction])
    lowest = min(heights, key=lambda direction: heights[direction])
    if heights[highest] < _OPEN_HORIZON_DEG:
        return OPEN_HORIZON_SUMMARY
    return (
        f"Relief marqué {_SUN_DIRECTIONS[highest]} ({round(heights[highest])}° au-dessus de "
        "l'horizon) : le soleil y est masqué quand il est bas, surtout en hiver. "
        f"Meilleur dégagement {_SUN_DIRECTIONS[lowest]}."
    )


def _join(words: list[str]) -> str:
    return " et ".join(filter(None, [", ".join(words[:-1]), words[-1]])) if words else ""


def noise_message(max_db: int | None, covered: Sequence[str] = ("route", "fer")) -> str:
    """Constat sur l'exposition au bruit (`max_db` : borne basse de la classe la plus forte).

    `covered` liste les infrastructures dont la carte existe ici : le constat ne porte que
    sur elles, et l'absence de carte routière ou ferroviaire est signalée.
    """
    message = next((text for threshold, text in _NOISE_MESSAGES if (max_db or 0) >= threshold), "")
    if not message:
        kinds = _join([_NOISE_KINDS[kind] for kind in _NOISE_KINDS if kind in covered])
        message = (
            "Hors des zones de bruit cartographiées : moins de 55 dB(A) en moyenne sur 24 h "
            f"pour les grandes infrastructures {kinds}."
        )
    unmapped = [label for kind, label in _NOISE_EXPECTED.items() if kind not in covered]
    if unmapped:
        message += (
            f" Bruit {_join(unmapped)} non cartographié dans notre base pour ce secteur : "
            "ce constat n'en dit rien."
        )
    return message


# Indice ATMO (arrêté du 10 juillet 2020) : six niveaux, du meilleur au pire.
_ATMO_LABELS = {
    1: "Bon",
    2: "Moyen",
    3: "Dégradé",
    4: "Mauvais",
    5: "Très mauvais",
    6: "Extrêmement mauvais",
}


def atmo_label(level: int) -> str:
    """Qualificatif officiel de l'indice ATMO."""
    return _ATMO_LABELS[level]
