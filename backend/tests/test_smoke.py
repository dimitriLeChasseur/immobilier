"""Règles du test de fumée (sans appel réseau)."""

from datetime import UTC, datetime

from app.schemas.audit import AuditReport, Location, ReportMeta, SourceResult, StreetInfo
from app.smoke import CASES, EXPECTED_KEYS, check_report, check_source, persistent

ADDRESS, STREET = CASES
META = ReportMeta(
    generated_at=datetime(2026, 1, 1, tzinfo=UTC), is_partial=False, report_version=1, duration_ms=1
)


def healthy(name: str, **extra: object) -> SourceResult:
    return SourceResult(status="ok", data={key: 1 for key in EXPECTED_KEYS[name]} | extra)


def test_a_complete_answer_raises_no_alarm() -> None:
    assert check_source("dvf", healthy("dvf"), ADDRESS) is None


def test_format_drift_and_outages_are_reported() -> None:
    drifted = SourceResult(status="ok", data={"nb_ventes": 3})
    assert check_source("dvf", drifted, ADDRESS) == (
        "champs absents : prix_m2_median, dernieres_ventes"
    )
    down = SourceResult(status="timeout", error="Délai dépassé")
    assert check_source("dvf", down, ADDRESS) == "timeout (Délai dépassé)"
    partial = SourceResult(status="partial", data={"risques": []}, missing=["radon"])
    assert check_source("georisques", partial, ADDRESS) == "réponse partielle, sans : radon"
    assert check_source("dvf", None, ADDRESS) == "source absente du rapport"


def test_no_data_is_only_accepted_where_it_is_expected() -> None:
    empty = SourceResult(status="empty")
    assert check_source("cadastre", empty, STREET) is None
    assert check_source("cadastre", empty, ADDRESS) is not None


def test_street_case_requires_the_street_mode() -> None:
    sources = {name: healthy(name) for name in EXPECTED_KEYS}
    sources["dvf"] = healthy("dvf", comparaison={})
    sources["dpe"] = healthy("dpe", par_numero=[])
    point = Location(lat=47.469, lon=-0.5529, label="x", citycode="49007")
    report = AuditReport(location=point, sources=sources, meta=META)
    assert check_report(report, STREET, list(EXPECTED_KEYS)) == [
        "localisation : la voie n'a pas été reconnue (mode rue inactif)"
    ]
    street = StreetInfo(
        id="49007_7050", nom="Rue Saint-Aubin", nb_numeros=2, longueur_m=1, points=[]
    )
    recognised = report.model_copy(update={"location": point.model_copy(update={"rue": street})})
    assert check_report(recognised, STREET, list(EXPECTED_KEYS)) == []


def test_only_anomalies_seen_twice_on_the_same_source_are_kept() -> None:
    first = ["ecoles : timeout (Délai dépassé)", "dvf : champs absents : prix_m2_median"]
    second = ["dvf : http_error (500)", "bruit : timeout (Délai dépassé)"]
    assert persistent(first, second) == ["dvf : http_error (500)"]
    assert persistent(first, []) == []
