"""Synthèse du rapport : les alertes et les points forts les plus marquants.

Chaque règle lit les données d'une source et produit, si elle s'applique, un constat pondéré.
Seuls les plus importants sont retenus, pour donner une lecture en tête de rapport.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from app.schemas.audit import Finding, SourceResult, Synthesis

_MAX_FINDINGS = 3
_STRONG_NOISE_DB = 65
_CLAY_STRONG = 3
_INDUSTRIAL_SITE_NEAR_M = 100
_CAVITY_NEAR_M = 200
_CAMPUS_NEAR_M = 800
_RADON_MAX = 3
# Plus exigeant que le signal de la carte DPE (40 %) : seule une nette majorité fait une alerte.
_POOR_ENERGY_SHARE_PCT = 50
_GOOD_ENERGY_LABELS = frozenset({"A", "B", "C"})
_BURGLARY = "Cambriolages de logement"
# Écart au repère départemental à partir duquel un taux est jugé remarquable.
_CRIME_HIGH_RATIO, _CRIME_LOW_RATIO = 1.5, 0.67
_TAX_HIGH_RATIO, _TAX_LOW_RATIO = 1.3, 0.75
_HIGH_VACANCY_PCT = 12
_LOW_FIBRE_PCT, _HIGH_FIBRE_PCT = 80, 95
_WALKABLE_MIN = 5
_GOOD_IPS = 110
_GOOD_YIELD_PCT = 6.0
_MIN_SALES_FOR_YIELD = 5
_MONTHS = 12


@dataclass(frozen=True, slots=True)
class _Scored:
    weight: int
    finding: Finding
    # Vrai pour un constat propre à l'adresse ; faux s'il vaut pour toute la commune.
    local: bool = True


Data = Mapping[str, Any]
Sources = Mapping[str, SourceResult]
Rule = Callable[[Data], _Scored | None]
CrossRule = Callable[[Sources], _Scored | None]


def _scored(weight: int, theme: str, title: str, detail: str, *, local: bool = True) -> _Scored:
    return _Scored(weight, Finding(theme=theme, titre=title, detail=detail), local)


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _fr(value: float) -> str:
    """Nombre à une décimale, avec la virgule française."""
    return f"{value:.1f}".replace(".", ",")


def _level(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# --- Alertes


def _has_easement(sources: Sources, code: str) -> bool:
    """Vrai si une servitude de cette catégorie couvre le point (Géoportail de l'urbanisme)."""
    easements = _data(sources, "urbanisme").get("servitudes") or []
    return any(item.get("code") == code for item in easements)


def _prevention_plan(sources: Sources) -> _Scored | None:
    """Seul constat de risque naturel établi à l'adresse : la servitude d'un plan de prévention."""
    if not _has_easement(sources, "PM1"):
        return None
    return _scored(
        90,
        "Risques",
        "Adresse dans le périmètre d'un plan de prévention des risques",
        "Une servitude de plan de prévention des risques naturels couvre ce point : le règlement "
        "peut limiter les travaux et peser sur l'assurance. Demandez l'état des risques.",
    )


def _flood_in_commune(sources: Sources) -> _Scored | None:
    """Mention, et non alerte forte : atlas, plans et TRI sont connus à l'échelle de la commune."""
    if _has_easement(sources, "PM1"):
        return None
    data = _data(sources, "georisques")
    plans = [
        plan["nom"]
        for plan in data.get("plans_prevention") or []
        if "PPRN-I" in str(plan.get("type")) or str(plan.get("nom")).upper().startswith("PPRI")
    ]
    if not plans and not (data.get("inondation") or {}).get("concerne") and not data.get("tri"):
        return None
    return _scored(
        35,
        "Risques",
        "Commune exposée au risque d'inondation",
        "Le risque est recensé pour la commune, sans indiquer si cette adresse est concernée : "
        "l'état des risques fourni par le vendeur le précise.",
        local=False,
    )


def _industrial_past(data: Data) -> _Scored | None:
    sites = (data.get("anciens_sites_industriels") or {}).get("plus_proches") or []
    nearest = _number(sites[0].get("distance_m")) if sites else None
    if nearest is None or nearest > _INDUSTRIAL_SITE_NEAR_M:
        return None
    return _scored(
        55,
        "Risques",
        f"Ancien site industriel à {round(nearest)} m",
        "Une activité passée a pu polluer les sols : consultez sa fiche sur Géorisques, "
        "surtout pour un jardin ou un rez-de-chaussée.",
    )


def _cavity(data: Data) -> _Scored | None:
    cavities = data.get("cavites") or {}
    nearest = _number((cavities.get("plus_proche") or {}).get("distance_m"))
    if nearest is None or nearest > _CAVITY_NEAR_M:
        return None
    return _scored(
        65,
        "Risques",
        f"Cavité souterraine à {round(nearest)} m",
        f"{cavities.get('nb_cavites')} cavité(s) recensée(s) dans un rayon de "
        f"{cavities.get('rayon_m')} m : risque d'affaissement à faire préciser.",
    )


def _heritage(sources: Sources) -> _Scored | None:
    """Abords de monument historique, d'après le bâtiment ou la servitude relevée au point."""
    building = _data(sources, "batiment").get("monument_historique") or {}
    if not building.get("dans_perimetre") and not _has_easement(sources, "AC1"):
        return None
    return _scored(
        40,
        "Urbanisme",
        "Abords d'un monument historique",
        "Les travaux visibles de l'extérieur sont soumis à l'avis de l'architecte des "
        "Bâtiments de France : délais et contraintes à prévoir.",
    )


def _building_energy(data: Data) -> _Scored | None:
    label = (data.get("dpe") or {}).get("classe")
    if label not in _GOOD_ENERGY_LABELS:
        return None
    return _scored(
        55,
        "Énergie",
        f"Bâtiment classé {label}",
        "Étiquette énergie retenue pour le bâtiment par la base nationale des bâtiments.",
    )


def _seveso(data: Data) -> _Scored | None:
    seveso = data.get("seveso") or {}
    sites = seveso.get("sites") or []
    if not sites:
        return None
    nearest = sites[0].get("distance_m")
    where = f"à {round(nearest)} m" if isinstance(nearest, int | float) else "à proximité"
    return _scored(
        85,
        "Risques",
        f"Site Seveso {where}",
        f"{len(sites)} site(s) industriel(s) classé(s) Seveso dans le périmètre étudié.",
    )


def _clay(data: Data) -> _Scored | None:
    level = _level((data.get("argiles") or {}).get("code"))
    if level is None or level < _CLAY_STRONG:
        return None
    return _scored(
        80,
        "Risques",
        "Argiles : exposition forte",
        "Sol très sensible au retrait-gonflement : risque de fissures, étude de sol à prévoir.",
    )


def _radon(data: Data) -> _Scored | None:
    if _level((data.get("radon") or {}).get("classe_potentiel")) != _RADON_MAX:
        return None
    return _scored(
        50,
        "Risques",
        "Radon : potentiel maximal",
        "Commune en catégorie 3 sur 3 : aération quotidienne et mesure en hiver recommandées.",
        local=False,
    )


def _noise_alert(data: Data) -> _Scored | None:
    level = _number(data.get("niveau_max_db"))
    if level is None or level < _STRONG_NOISE_DB:
        return None
    return _scored(
        80,
        "Bruit",
        f"Bruit fort : {round(level)} dB(A) et plus",
        "Le bien est dans une zone de bruit élevé d'une grande infrastructure : vérifiez "
        "l'isolation et l'orientation des pièces de vie.",
    )


def _overlook(data: Data) -> _Scored | None:
    if not data.get("risque_vis_a_vis"):
        return None
    return _scored(
        70,
        "Urbanisme",
        "Projet de construction en hauteur tout proche",
        "Un permis autorisé à proximité immédiate peut créer un vis-à-vis ou masquer la vue.",
    )


def _poor_energy(data: Data) -> _Scored | None:
    share = _number((data.get("analyse") or {}).get("part_efg_pct"))
    if share is None or share <= _POOR_ENERGY_SHARE_PCT:
        return None
    return _scored(
        60,
        "Énergie",
        f"{round(share)} % de logements voisins classés E, F ou G",
        "Parc énergivore : demandez le DPE du bien, c'est un levier de négociation et un "
        "poste de travaux probable.",
    )


def _burglary(data: Data) -> tuple[float, float] | None:
    for row in data.get("indicateurs") or []:
        if row.get("indicateur") == _BURGLARY:
            rate = _number(row.get("taux_pour_mille"))
            reference = _number((row.get("reperes") or {}).get("departement"))
            if rate is not None and reference:
                return rate, reference
    return None


def _crime_alert(data: Data) -> _Scored | None:
    rates = _burglary(data)
    if rates is None or rates[0] < _CRIME_HIGH_RATIO * rates[1]:
        return None
    return _scored(
        55,
        "Sécurité",
        "Cambriolages nettement au-dessus du département",
        f"{_fr(rates[0])} pour 1 000 habitants dans la commune, contre {_fr(rates[1])} dans "
        "le département.",
        local=False,
    )


def _tax_ratio(data: Data) -> tuple[float, float] | None:
    rate = _number(data.get("taux_tfb_total"))
    median = _number((data.get("reperes") or {}).get("mediane_departement"))
    return (rate, median) if rate is not None and median else None


def _tax_alert(data: Data) -> _Scored | None:
    rates = _tax_ratio(data)
    if rates is None or rates[0] < _TAX_HIGH_RATIO * rates[1]:
        return None
    return _scored(
        45,
        "Fiscalité",
        "Taxe foncière élevée pour le département",
        f"Taux de {_fr(rates[0])} %, contre {_fr(rates[1])} % pour la commune médiane du "
        "département.",
        local=False,
    )


def _vacancy(data: Data) -> _Scored | None:
    share = _number((data.get("occupation") or {}).get("part_vacants_pct"))
    if share is None or share < _HIGH_VACANCY_PCT:
        return None
    return _scored(
        40,
        "Marché locatif",
        f"{round(share)} % de logements vacants dans le quartier",
        "Vacance élevée : la mise en location ou la revente peut prendre plus de temps.",
        local=False,
    )


def _rent_control(data: Data) -> _Scored | None:
    if (data.get("encadrement_loyers") or {}).get("statut") != "oui":
        return None
    return _scored(
        45,
        "Marché locatif",
        "Loyers encadrés",
        "Le loyer est plafonné par un loyer de référence : intégrez-le au calcul du rendement.",
        local=False,
    )


def _low_fibre(data: Data) -> _Scored | None:
    share = _number(data.get("part_fibre_pct"))
    if share is None or share >= _LOW_FIBRE_PCT:
        return None
    return _scored(
        35,
        "Connexion",
        f"Fibre : {round(share)} % seulement des locaux de la commune",
        "Déploiement incomplet : vérifiez l'éligibilité de l'adresse avant d'acheter.",
        local=False,
    )


# --- Points forts


def _nearest(data: Data, category: str) -> tuple[int, float] | None:
    summary = (data.get("categories") or {}).get(category) or {}
    minutes = _number((summary.get("plus_proche") or {}).get("marche_min"))
    count = _number(summary.get("nb"))
    return (round(count or 0), minutes) if minutes is not None else None


def _transport(data: Data) -> _Scored | None:
    nearest = _nearest(data, "transports")
    if nearest is None or nearest[1] > _WALKABLE_MIN:
        return None
    return _scored(
        60,
        "Vie de quartier",
        f"Transports à {round(nearest[1])} min à pied",
        f"{nearest[0]} arrêt(s) ou station(s) dans un rayon de {data.get('rayon_m')} m.",
    )


def _shops(data: Data) -> _Scored | None:
    nearest = _nearest(data, "commerces")
    if nearest is None or nearest[1] > _WALKABLE_MIN:
        return None
    return _scored(
        50,
        "Vie de quartier",
        f"Commerces alimentaires à {round(nearest[1])} min à pied",
        f"{nearest[0]} commerce(s) alimentaire(s) dans un rayon de {data.get('rayon_m')} m.",
    )


def _quiet(data: Data) -> _Scored | None:
    covered = data.get("infrastructures_couvertes") or []
    if data.get("niveau_max_db") is not None or not {"route", "fer"} <= set(covered):
        return None
    return _scored(
        55,
        "Bruit",
        "Hors des zones de bruit cartographiées",
        "Moins de 55 dB(A) en moyenne pour les grandes routes et voies ferrées.",
    )


def _good_energy(data: Data) -> _Scored | None:
    if data.get("etiquette_dominante") not in _GOOD_ENERGY_LABELS:
        return None
    return _scored(
        45,
        "Énergie",
        f"Voisinage majoritairement classé {data['etiquette_dominante']}",
        "Les logements diagnostiqués autour sont plutôt sobres en énergie.",
    )


def _crime_strength(data: Data) -> _Scored | None:
    rates = _burglary(data)
    if rates is None or rates[0] > _CRIME_LOW_RATIO * rates[1]:
        return None
    return _scored(
        50,
        "Sécurité",
        "Cambriolages nettement sous la moyenne du département",
        f"{_fr(rates[0])} pour 1 000 habitants dans la commune, contre {_fr(rates[1])} dans "
        "le département.",
        local=False,
    )


def _tax_strength(data: Data) -> _Scored | None:
    rates = _tax_ratio(data)
    if rates is None or rates[0] > _TAX_LOW_RATIO * rates[1]:
        return None
    return _scored(
        40,
        "Fiscalité",
        "Taxe foncière modérée pour le département",
        f"Taux de {_fr(rates[0])} %, contre {_fr(rates[1])} % pour la commune médiane du "
        "département.",
        local=False,
    )


def _fibre(data: Data) -> _Scored | None:
    share = _number(data.get("part_fibre_pct"))
    if share is None or share < _HIGH_FIBRE_PCT:
        return None
    return _scored(
        40,
        "Connexion",
        "Commune presque entièrement fibrée",
        f"{round(share)} % des locaux sont raccordables à la fibre.",
        local=False,
    )


def _schools(data: Data) -> _Scored | None:
    best: tuple[str, float, float] | None = None
    for kind, stats in (data.get("par_type") or {}).items():
        score, reference = _number(stats.get("ips_moyen")), _number(stats.get("moyenne_nationale"))
        if score is not None and reference and score >= _GOOD_IPS and score > reference:
            if best is None or score - reference > best[1] - best[2]:
                best = (kind, score, reference)
    if best is None:
        return None
    labels = {"ecole": "Écoles", "college": "Collèges", "lycee": "Lycées"}
    return _scored(
        50,
        "Écoles",
        f"{labels.get(best[0], 'Établissements')} proches au-dessus de la moyenne",
        f"Indice de position sociale moyen de {_fr(best[1])}, contre {_fr(best[2])} en France.",
    )


def _students(data: Data) -> _Scored | None:
    """Établissement d'enseignement supérieur tout proche : demande locative étudiante."""
    schools = (data.get("superieur") or {}).get("etablissements") or []
    nearest = schools[0] if schools else {}
    distance = _number(nearest.get("distance_m"))
    if distance is None or distance > _CAMPUS_NEAR_M:
        return None
    name = nearest.get("sigle") or nearest.get("nom")
    return _scored(
        45,
        "Marché locatif",
        f"Enseignement supérieur à {round(distance)} m",
        f"{name} est à distance de marche : la demande locative étudiante soutient les "
        "petites surfaces.",
    )


_ALERTS: tuple[tuple[str, Rule], ...] = (
    ("georisques", _seveso),
    ("georisques", _clay),
    ("georisques", _cavity),
    ("georisques", _industrial_past),
    ("georisques", _radon),
    ("bruit", _noise_alert),
    ("permis_construire", _overlook),
    ("dpe", _poor_energy),
    ("delinquance", _crime_alert),
    ("taxe_fonciere", _tax_alert),
    ("marche_locatif", _vacancy),
    ("marche_locatif", _rent_control),
    ("connectivite", _low_fibre),
)
_STRENGTHS: tuple[tuple[str, Rule], ...] = (
    ("proximite", _transport),
    ("proximite", _shops),
    ("bruit", _quiet),
    ("batiment", _building_energy),
    ("dpe", _good_energy),
    ("delinquance", _crime_strength),
    ("taxe_fonciere", _tax_strength),
    ("connectivite", _fibre),
    ("ecoles", _schools),
    ("ecoles", _students),
)


def _flat_market(dvf: Data) -> Data:
    """Ventes d'appartements : les 24 derniers mois s'ils suffisent, sinon les cinq ans."""
    recent = ((dvf.get("recent") or {}).get("par_type") or {}).get("appartement") or {}
    if (_number(recent.get("nb_ventes")) or 0) >= _MIN_SALES_FOR_YIELD:
        return recent
    flats: Data = (dvf.get("par_type") or {}).get("appartement") or {}
    return flats


def _yield_strength(sources: Sources) -> _Scored | None:
    """Rendement brut : loyer d'appartement de la commune sur prix des appartements voisins.

    Le loyer de référence étant celui des appartements, il n'est rapporté qu'à des ventes
    d'appartements : sans elles, aucun rendement n'est avancé.
    """
    rent = _number(_data(sources, "loyers").get("loyer_m2_charges_comprises"))
    flats = _flat_market(_data(sources, "dvf"))
    price = _number(flats.get("prix_m2_median"))
    sales = _number(flats.get("nb_ventes")) or 0
    # Une poignée de ventes ne fait pas un prix de marché (quartier pavillonnaire).
    if rent is None or not price or sales < _MIN_SALES_FOR_YIELD:
        return None
    gross = 100 * rent * _MONTHS / price
    if gross < _GOOD_YIELD_PCT:
        return None
    return _scored(
        60,
        "Rendement",
        f"Rendement locatif brut estimé à {_fr(gross)} %",
        "Loyer d'annonce des appartements de la commune rapporté au prix médian des "
        "appartements vendus à proximité, avant charges et taxe foncière.",
        local=False,
    )


def _data(sources: Sources, name: str) -> Data:
    result = sources.get(name)
    return result.data if result is not None and isinstance(result.data, dict) else {}


def _top(scored: list[_Scored]) -> list[Finding]:
    """Constats retenus : ceux de l'adresse d'abord, en variant les thèmes si possible."""
    # Tri stable : à rang égal, l'ordre des règles départage.
    ranked = sorted(scored, key=lambda item: (not item.local, -item.weight))
    kept: list[_Scored] = []
    for item in ranked:
        if all(item.finding.theme != other.finding.theme for other in kept):
            kept.append(item)
    kept = kept[:_MAX_FINDINGS]
    # La diversité prime, mais une place libre n'est jamais laissée vide : elle revient au
    # constat suivant, même si son thème est déjà représenté.
    for item in ranked:
        if len(kept) >= _MAX_FINDINGS:
            break
        if item not in kept:
            kept.append(item)
    return [item.finding for item in sorted(kept, key=ranked.index)]


def build_synthesis(sources: Sources) -> Synthesis:
    """Les trois alertes et les trois points forts les plus marquants du rapport."""
    alerts = [found for name, rule in _ALERTS if (found := rule(_data(sources, name)))]
    alerts += [found for cross in _CROSS_ALERTS if (found := cross(sources))]
    strengths = [found for name, rule in _STRENGTHS if (found := rule(_data(sources, name)))]
    strengths += [found for cross in _CROSS_STRENGTHS if (found := cross(sources))]
    return Synthesis(alertes=_top(alerts), points_forts=_top(strengths))


# Règles lisant plusieurs sources à la fois.
_CROSS_ALERTS: tuple[CrossRule, ...] = (_prevention_plan, _flood_in_commune, _heritage)
_CROSS_STRENGTHS: tuple[CrossRule, ...] = (_yield_strength,)
