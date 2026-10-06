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


def test_synthesis_keeps_the_three_heaviest_findings_of_each_kind() -> None:
    synthesis = build_synthesis(
        {
            "georisques": ok(
                {
                    "inondation": {"concerne": True},
                    "argiles": {"code": "3"},
                    "radon": {"classe_potentiel": "3"},
                    "seveso": {"sites": [{"distance_m": 812.4}]},
                }
            ),
            "bruit": ok({"niveau_max_db": 70, "infrastructures_couvertes": ["fer", "route"]}),
            "proximite": ok(
                {
                    "rayon_m": 500,
                    "categories": {
                        "transports": {"nb": 12, "plus_proche": {"marche_min": 3}},
                        "commerces": {"nb": 4, "plus_proche": {"marche_min": 9}},
                    },
                }
            ),
            "connectivite": ok({"part_fibre_pct": 97.3}),
            "loyers": ok({"loyer_m2_charges_comprises": 14.0}),
            "dvf": ok({"prix_m2_median": 2400}),
        }
    )
    assert [item.titre for item in synthesis.alertes] == [
        "Zone inondable répertoriée",
        "Site Seveso à 812 m",
        "Argiles : exposition forte",
    ]
    assert [item.titre for item in synthesis.points_forts] == [
        "Transports à 3 min à pied",
        "Rendement locatif brut estimé à 7,0 %",
        "Commune presque entièrement fibrée",
    ]
    assert synthesis.points_forts[0].detail == "12 arrêt(s) ou station(s) dans un rayon de 500 m."


def test_synthesis_is_empty_without_remarkable_data_and_ignores_failed_sources() -> None:
    synthesis = build_synthesis(
        {
            "georisques": ok({"inondation": {"concerne": False}, "argiles": {"code": "1"}}),
            "bruit": SourceResult(status="timeout"),
            # Seul le ferroviaire est cartographié : le calme n'est pas un point fort.
            "dpe": ok({"etiquette_dominante": "D", "analyse": {"part_efg_pct": 20.0}}),
            "loyers": ok({"loyer_m2_charges_comprises": "***LOCKED***"}),
            "dvf": ok({"prix_m2_median": 3000}),
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
