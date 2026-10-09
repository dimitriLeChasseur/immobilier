"""Synthèse en tête de rapport et repères de comparaison."""

from typing import Any

from app.core.geo import departement_code
from app.schemas.audit import Finding, ReportMeta, SourceResult, Synthesis
from app.services.providers.base import AuditContext
from app.services.providers.reference import CrimeProvider, PropertyTaxProvider, SchoolsProvider
from app.services.synthesis import build_synthesis
from app.services.teaser import LOCKED, mask_meta

ANGERS = AuditContext(lat=47.47, lon=-0.55, citycode="49007")


def ok(data: dict[str, Any]) -> SourceResult:
    return SourceResult(status="ok", data=data)


def test_departement_code_handles_corsica_and_overseas() -> None:
    assert departement_code("49007") == "49"
    assert departement_code("2A004") == "2A"
    assert departement_code("97411") == "974"


RICH = {
    "georisques": ok(
        {
            "inondation": {"concerne": True},
            "argiles": {"code": "3"},
            "radon": {"classe_potentiel": "3"},
            "seveso": {"sites": [{"distance_m": 812.4}]},
        }
    ),
    "bruit": ok({"niveau_max_db": 70, "infrastructures_couvertes": ["fer", "route"]}),
    "permis_construire": ok({"risque_vis_a_vis": True}),
    "proximite": ok(
        {
            "rayon_m": 500,
            "categories": {
                "transports": {"nb": 12, "plus_proche": {"marche_min": 3}},
                "commerces": {"nb": 4, "plus_proche": {"marche_min": 2}},
            },
        }
    ),
    "connectivite": ok({"part_fibre_pct": 97.3}),
    "loyers": ok({"loyer_m2_charges_comprises": 14.0}),
    "dvf": ok(
        {
            "prix_m2_median": 3900,
            "par_type": {"appartement": {"prix_m2_median": 2400, "nb_ventes": 40}},
        }
    ),
}


def test_synthesis_puts_address_findings_first_with_one_finding_per_theme() -> None:
    synthesis = build_synthesis(RICH)
    # Trois thèmes distincts, tous propres à l'adresse : ni l'argile (même thème que Seveso),
    # ni l'inondation et le radon (connus pour la commune seulement) ne les évincent.
    assert [(item.theme, item.titre) for item in synthesis.alertes] == [
        ("Risques", "Site Seveso à 812 m"),
        ("Bruit", "Bruit fort : 70 dB(A) et plus"),
        ("Urbanisme", "Projet de construction en hauteur tout proche"),
    ]
    assert [(item.theme, item.titre) for item in synthesis.points_forts] == [
        ("Vie de quartier", "Transports à 3 min à pied"),
        ("Rendement", "Rendement locatif brut estimé à 7,0 %"),
        ("Connexion", "Commune presque entièrement fibrée"),
    ]
    assert synthesis.points_forts[0].detail == "12 arrêt(s) ou station(s) dans un rayon de 500 m."


def test_commune_level_findings_fill_the_remaining_slots() -> None:
    commune_only = build_synthesis(
        {"georisques": ok({"inondation": {"concerne": True}, "radon": {"classe_potentiel": "3"}})}
    )
    # Deux constats communaux du même thème : le plus lourd d'abord, l'autre prend une place libre.
    assert [item.titre for item in commune_only.alertes] == [
        "Radon : potentiel maximal",
        "Commune exposée au risque d'inondation",
    ]


def test_flood_is_a_strong_alert_only_when_a_prevention_plan_covers_the_address() -> None:
    risks = ok(
        {
            "inondation": {"concerne": True},
            "tri": ["Angers - Authion - Saumur"],
            "plans_prevention": [{"nom": "PPRi-Confluence de Maine", "type": "PPRN-I"}],
        }
    )
    outside = build_synthesis(
        {"georisques": risks, "urbanisme": ok({"servitudes": [{"code": "AC4"}]})}
    )
    assert [item.titre for item in outside.alertes] == ["Commune exposée au risque d'inondation"]
    assert "sans indiquer si cette adresse est concernée" in outside.alertes[0].detail

    covered = build_synthesis(
        {"georisques": risks, "urbanisme": ok({"servitudes": [{"code": "PM1"}]})}
    )
    assert [item.titre for item in covered.alertes] == [
        "Adresse dans le périmètre d'un plan de prévention des risques"
    ]

    # Un constat à l'adresse passe devant la mention communale.
    noisy = build_synthesis({"georisques": risks, "bruit": ok({"niveau_max_db": 70})})
    assert [item.theme for item in noisy.alertes] == ["Bruit", "Risques"]
    assert build_synthesis({"georisques": ok({"inondation": {"concerne": False}})}).alertes == []


def test_heritage_is_read_from_the_easement_too() -> None:
    street_mode = build_synthesis({"urbanisme": ok({"servitudes": [{"code": "AC1"}]})})
    assert [item.titre for item in street_mode.alertes] == ["Abords d'un monument historique"]


def test_distant_cavities_and_a_slim_majority_of_poor_labels_raise_no_alert() -> None:
    def cavity(distance: int) -> SourceResult:
        nearest = {"distance_m": distance}
        return ok({"cavites": {"rayon_m": 500, "nb_cavites": 3, "plus_proche": nearest}})

    assert build_synthesis({"georisques": cavity(450)}).alertes == []
    assert build_synthesis({"georisques": cavity(120)}).alertes[0].titre == (
        "Cavité souterraine à 120 m"
    )
    assert build_synthesis({"dpe": ok({"analyse": {"part_efg_pct": 42.0}})}).alertes == []
    assert build_synthesis({"dpe": ok({"analyse": {"part_efg_pct": 57.0}})}).alertes[0].titre == (
        "57 % de logements voisins classés E, F ou G"
    )


def test_yield_compares_apartment_rent_with_apartment_prices_only() -> None:
    rent = ok({"loyer_m2_charges_comprises": 14.0})
    houses_only = {"par_type": {"maison": {"prix_m2_median": 2000}}, "prix_m2_median": 2000}
    assert build_synthesis({"loyers": rent, "dvf": ok(houses_only)}).points_forts == []


def test_synthesis_is_empty_without_remarkable_data_and_ignores_failed_sources() -> None:
    synthesis = build_synthesis(
        {
            "georisques": ok({"inondation": {"concerne": False}, "argiles": {"code": "1"}}),
            "bruit": SourceResult(status="timeout"),
            # Seul le ferroviaire est cartographié : le calme n'est pas un point fort.
            "dpe": ok({"etiquette_dominante": "D", "analyse": {"part_efg_pct": 20.0}}),
            "loyers": ok({"loyer_m2_charges_comprises": "***LOCKED***"}),
            "dvf": ok({"par_type": {"appartement": {"prix_m2_median": 3000}}}),
        }
    )
    assert synthesis == Synthesis()
    rail_only = build_synthesis(
        {"bruit": ok({"niveau_max_db": None, "infrastructures_couvertes": ["fer"]})}
    )
    assert rail_only.points_forts == []


def test_benchmarks_turn_local_rates_into_findings() -> None:
    def crime(rate: float) -> SourceResult:
        row = {
            "indicateur": "Cambriolages de logement",
            "taux_pour_mille": rate,
            "reperes": {"departement": 2.0},
        }
        return ok({"indicateurs": [row]})

    def tax(rate: float) -> SourceResult:
        return ok({"taux_tfb_total": rate, "reperes": {"mediane_departement": 40.0}})

    high = build_synthesis({"delinquance": crime(3.4), "taxe_fonciere": tax(56.65)})
    assert [item.theme for item in high.alertes] == ["Sécurité", "Fiscalité"]
    assert "3,4 pour 1 000 habitants" in high.alertes[0].detail
    assert "56,6 %, contre 40,0 %" in high.alertes[1].detail

    low = build_synthesis({"delinquance": crime(1.0), "taxe_fonciere": tax(28.0)})
    assert [item.theme for item in low.points_forts] == ["Sécurité", "Fiscalité"]
    assert build_synthesis({"delinquance": crime(2.2), "taxe_fonciere": tax(42.0)}) == Synthesis()


def test_schools_strength_compares_like_with_like() -> None:
    by_kind = {
        "ecole": {"ips_moyen": 121.0, "moyenne_nationale": 104.5},
        "lycee": {"ips_moyen": 108.0, "moyenne_nationale": 107.3},
    }
    synthesis = build_synthesis({"ecoles": ok({"par_type": by_kind})})
    assert synthesis.points_forts[0].titre == "Écoles proches au-dessus de la moyenne"
    assert "121,0, contre 104,5 en France" in synthesis.points_forts[0].detail


def test_teaser_keeps_the_themes_and_locks_the_content() -> None:
    meta = ReportMeta(
        generated_at="2026-10-06T10:00:00Z",
        is_partial=False,
        report_version=7,
        duration_ms=1,
        synthese=Synthesis(
            alertes=[Finding(theme="Risques", titre="Zone inondable répertoriée", detail="x")],
            points_forts=[Finding(theme="Bruit", titre="Calme", detail="y")],
        ),
    )
    masked = mask_meta(meta)
    assert masked.synthese is not None
    assert masked.synthese.alertes == [Finding(theme="Risques", titre=LOCKED, detail=LOCKED)]
    assert masked.synthese.points_forts[0].theme == "Bruit"
    assert "inondable" not in masked.model_dump_json()
    assert meta.synthese is not None and meta.synthese.alertes[0].titre.startswith("Zone")


class Repository:
    """Référentiel minimal : une commune, ses repères et trois établissements."""

    def __init__(self, broken: bool = False) -> None:
        self.broken = broken

    def _check(self) -> None:
        if self.broken:
            from app.core.errors import RepositoryError

            raise RepositoryError("down")

    async def crime_indicators(self, codes: list[str]) -> list[dict[str, Any]]:
        return [{"indicateur": "Cambriolages de logement", "annee": 2025, "taux_pour_mille": 1.7}]

    async def crime_benchmarks(self, year: int, departement: str) -> dict[str, dict[str, float]]:
        self._check()
        assert (year, departement) == (2025, "49")
        return {"Cambriolages de logement": {"departement": 2.1, "national": 3.27}}

    async def crime_rates(self, codes: list[str], year: int) -> dict[str, float]:
        assert year == 2024
        return {"Cambriolages de logement": 2.0}

    async def property_tax(self, codes: list[str]) -> dict[str, Any]:
        return {"annee": 2025, "taux_tfb_total": 56.65}

    async def property_tax_benchmarks(self, year: int, departement: str) -> dict[str, float]:
        self._check()
        return {"departement": 41.2, "national": 40.33}

    async def schools_nearby(self, *args: Any) -> list[dict[str, Any]]:
        return [
            {"type_etablissement": "ecole", "ips": 120.0},
            {"type_etablissement": "ecole", "ips": 130.0},
            {"type_etablissement": "lycee", "ips": 110.0},
            {"type_etablissement": "college", "ips": None},
        ]

    async def ips_benchmarks(self, departement: str) -> dict[str, dict[str, float]]:
        self._check()
        return {"ecole": {"departement": 106.0, "national": 104.5}}


async def test_providers_attach_benchmarks_to_local_figures() -> None:
    repository = Repository()
    crime = (await CrimeProvider(repository).fetch(ANGERS)).data  # type: ignore[arg-type]
    assert crime["indicateurs"][0]["reperes"] == {
        "departement": 2.1,
        "national": 3.27,
        "annee_precedente": 2.0,
    }
    tax = (await PropertyTaxProvider(repository).fetch(ANGERS)).data  # type: ignore[arg-type]
    assert tax["reperes"] == {"mediane_departement": 41.2, "mediane_nationale": 40.33}
    schools = (await SchoolsProvider(repository).fetch(ANGERS)).data  # type: ignore[arg-type]
    assert schools["par_type"] == {
        "ecole": {
            "nb": 2,
            "ips_moyen": 125.0,
            "moyenne_departement": 106.0,
            "moyenne_nationale": 104.5,
        },
        "lycee": {
            "nb": 1,
            "ips_moyen": 110.0,
            "moyenne_departement": None,
            "moyenne_nationale": None,
        },
    }


async def test_missing_benchmarks_never_hide_the_local_figures() -> None:
    repository = Repository(broken=True)
    crime = (await CrimeProvider(repository).fetch(ANGERS)).data  # type: ignore[arg-type]
    assert crime["indicateurs"][0]["taux_pour_mille"] == 1.7
    assert "reperes" not in crime["indicateurs"][0]
    tax = (await PropertyTaxProvider(repository).fetch(ANGERS)).data  # type: ignore[arg-type]
    assert tax["reperes"] == {"mediane_departement": None, "mediane_nationale": None}
    schools = (await SchoolsProvider(repository).fetch(ANGERS)).data  # type: ignore[arg-type]
    assert schools["par_type"]["ecole"]["moyenne_nationale"] is None


def test_free_slots_go_to_the_next_findings_even_within_one_theme() -> None:
    risks = ok(
        {
            "seveso": {"sites": [{"distance_m": 300}]},
            "argiles": {"code": "3"},
            "cavites": {"rayon_m": 500, "nb_cavites": 1, "plus_proche": {"distance_m": 50}},
            "inondation": {"concerne": True},
        }
    )
    easement = ok({"servitudes": [{"code": "PM1"}]})
    synthesis = build_synthesis({"georisques": risks, "urbanisme": easement})
    # Tout relève du thème « Risques » : les trois places sont tout de même remplies, par poids.
    assert [item.titre for item in synthesis.alertes] == [
        "Adresse dans le périmètre d'un plan de prévention des risques",
        "Site Seveso à 300 m",
        "Argiles : exposition forte",
    ]
    # La diversité reste prioritaire dès qu'un autre thème existe.
    varied = build_synthesis(
        {"georisques": risks, "urbanisme": easement, "bruit": ok({"niveau_max_db": 70})}
    )
    # Le bruit entre dans la sélection ; l'affichage reste trié par importance.
    assert [item.titre for item in varied.alertes] == [
        "Adresse dans le périmètre d'un plan de prévention des risques",
        "Site Seveso à 300 m",
        "Bruit fort : 70 dB(A) et plus",
    ]


def test_commune_mention_takes_a_free_slot() -> None:
    synthesis = build_synthesis(
        {
            "georisques": ok(
                {
                    "inondation": {"concerne": True},
                    "radon": {"classe_potentiel": "3"},
                    "anciens_sites_industriels": {"plus_proches": [{"distance_m": 64}]},
                }
            )
        }
    )
    assert [item.titre for item in synthesis.alertes] == [
        "Ancien site industriel à 64 m",
        "Radon : potentiel maximal",
        "Commune exposée au risque d'inondation",
    ]


def test_yield_needs_enough_apartment_sales() -> None:
    rent = ok({"loyer_m2_charges_comprises": 14.0})

    def flats(count: int) -> SourceResult:
        return ok({"par_type": {"appartement": {"prix_m2_median": 2400, "nb_ventes": count}}})

    assert build_synthesis({"loyers": rent, "dvf": flats(4)}).points_forts == []
    assert len(build_synthesis({"loyers": rent, "dvf": flats(5)}).points_forts) == 1


def test_yield_prefers_recent_apartment_prices_when_there_are_enough() -> None:
    rent = ok({"loyer_m2_charges_comprises": 14.0})

    def market(recent_sales: int) -> SourceResult:
        return ok(
            {
                "par_type": {"appartement": {"prix_m2_median": 2800, "nb_ventes": 60}},
                "recent": {
                    "par_type": {"appartement": {"prix_m2_median": 2000, "nb_ventes": recent_sales}}
                },
            }
        )

    # 14 x 12 / 2 000 = 8,4 % sur les ventes récentes ; 6,0 % sur cinq ans.
    recent = build_synthesis({"loyers": rent, "dvf": market(12)}).points_forts[0]
    assert recent.titre == "Rendement locatif brut estimé à 8,4 %"
    five_years = build_synthesis({"loyers": rent, "dvf": market(3)}).points_forts[0]
    assert five_years.titre == "Rendement locatif brut estimé à 6,0 %"


def test_yield_headline_is_the_best_dwelling_type_and_compares_the_others() -> None:
    rents = ok(
        {
            "loyer_m2_charges_comprises": 14.0,
            "par_typologie": {
                "t1_t2": {"loyer_m2_charges_comprises": 17.0},
                "t3_plus": {"loyer_m2_charges_comprises": 12.0},
                "maison": {"loyer_m2_charges_comprises": 11.0},
            },
        }
    )
    dvf = ok(
        {
            "par_type": {
                "appartement": {"prix_m2_median": 3000, "nb_ventes": 60},
                # Trop peu de ventes de maisons : ce type n'entre pas dans la comparaison.
                "maison": {"prix_m2_median": 1500, "nb_ventes": 3},
            },
            "par_taille": {
                "t1_t2": {"prix_m2_median": 3200, "nb_ventes": 30},
                "t3_plus": {"prix_m2_median": 2900, "nb_ventes": 25},
            },
            "recent": {"par_taille": {"t1_t2": {"prix_m2_median": 3000, "nb_ventes": 9}}},
        }
    )
    # 1-2 pièces : 17 x 12 / 3 000 (24 derniers mois) = 6,8 % ; ensemble : 5,6 % ; grands : 5,0 %.
    finding = build_synthesis({"loyers": rents, "dvf": dvf}).points_forts[0]
    assert finding.titre == (
        "Rendement locatif brut estimé à 6,8 % pour un appartement de 1 ou 2 pièces"
    )
    assert finding.detail.endswith(
        "Pour comparaison, un appartement : 5,6 % ; un appartement de 3 pièces et plus : 5,0 %."
    )

    # Valeurs masquées : aucun calcul, aucune erreur.
    locked = "***LOCKED***"
    masked = {
        "loyers": ok({"loyer_m2_charges_comprises": locked, "par_typologie": locked}),
        "dvf": ok({"par_type": locked, "par_taille": locked, "recent": locked}),
    }
    assert build_synthesis(masked).points_forts == []

    # Aucun type n'atteint le seuil : pas de point fort.
    dear = ok({"par_type": {"appartement": {"prix_m2_median": 4000, "nb_ventes": 60}}})
    assert build_synthesis({"loyers": rents, "dvf": dear}).points_forts == []
