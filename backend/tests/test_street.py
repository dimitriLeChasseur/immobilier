"""Mode « rue » : résolution de la voie et agrégation le long de ses numéros."""

from typing import Any

import pytest

from app.core.errors import SourceError
from app.services.providers.base import AuditContext
from app.services.providers.dpe import DpeProvider, _by_number
from app.services.providers.dvf import DvfProvider, _on_street
from app.services.street import (
    BanStreetResolver,
    Street,
    is_street_id,
    normalize_street_name,
    parse_street,
)

STREET = Street(
    id="49007_7050",
    name="Rue Saint-Aubin",
    points=((-0.5540, 47.4699), (-0.5530, 47.4692), (-0.5520, 47.4685), (-0.5510, 47.4678)),
)
CENTER = (47.4690, -0.5529)


def lookup(**overrides: Any) -> dict[str, Any]:
    numbers = [
        {"numero": 3, "suffixe": None, "position": {"coordinates": [-0.5530, 47.4692]}},
        {"numero": 1, "suffixe": None, "position": {"coordinates": [-0.5540, 47.4699]}},
        {"numero": 1, "suffixe": "bis", "position": {"coordinates": [-0.5539, 47.4698]}},
        {"numero": 5, "position": None},
    ]
    return (
        {"type": "voie", "idVoie": "49007_7050", "nomVoie": "Rue Saint-Aubin"}
        | {"numeros": numbers}
        | overrides
    )


@pytest.mark.parametrize(
    ("ban_id", "expected"),
    [
        ("49007_7050", True),
        ("2A004_0123", True),
        ("49176_2betic", True),
        ("49007_7050_00012", False),
        ("49007", False),
        ("", False),
        ("49007_7050/../x", False),
    ],
)
def test_only_street_identifiers_trigger_the_street_mode(ban_id: str, expected: bool) -> None:
    assert is_street_id(ban_id) is expected


def test_street_points_follow_the_numbering() -> None:
    street = parse_street(lookup(), *CENTER)
    assert street is not None
    assert street.name == "Rue Saint-Aubin"
    # Numéros 1, 1 bis, 3 ; le 5, sans position, est écarté.
    assert street.points == ((-0.5540, 47.4699), (-0.5539, 47.4698), (-0.5530, 47.4692))
    assert street.fantoir == "7050"


@pytest.mark.parametrize(
    "payload",
    [
        None,
        lookup(type="numero"),
        lookup(numeros=[]),
        lookup(numeros=[{"numero": 1, "position": {"coordinates": [-0.554, 47.4699]}}]),
        lookup(nomVoie=None),
    ],
)
def test_unusable_lookups_fall_back_to_the_point_analysis(payload: Any) -> None:
    assert parse_street(payload, *CENTER) is None


def test_street_far_from_the_requested_point_is_rejected() -> None:
    # Identifiant d'une rue d'Angers présenté avec des coordonnées parisiennes.
    assert parse_street(lookup(), 48.8566, 2.3522) is None


def test_street_geometry_helpers() -> None:
    assert STREET.sample(2) == [STREET.points[0], STREET.points[-1]]
    assert STREET.sample(10) == list(STREET.points)
    assert 250 < STREET.length_m < 350
    ring = STREET.envelope(40)["coordinates"][0]
    assert ring[0] == ring[-1]
    assert min(p[0] for p in ring) < -0.5540 < -0.5510 < max(p[0] for p in ring)
    assert Street(id="49176_2betic", name="x", points=STREET.points).fantoir is None


def test_street_names_match_between_ban_and_dvf() -> None:
    assert normalize_street_name("Rue Saint-Aubin") == normalize_street_name("RUE SAINT AUBIN")
    assert normalize_street_name("Allée de l'Église") == "ALLEE DE L EGLISE"
    assert normalize_street_name(None) == ""


def test_dvf_rows_are_matched_by_street_code_then_by_name() -> None:
    assert _on_street({"adresse_code_voie": "7050", "adresse_nom_voie": "AUTRE"}, STREET)
    assert _on_street({"adresse_code_voie": "9999", "adresse_nom_voie": "RUE SAINT AUBIN"}, STREET)
    assert not _on_street({"adresse_code_voie": "6450", "adresse_nom_voie": "RUE DU CANAL"}, STREET)
    assert not _on_street({}, STREET)


class FakeHttp:
    def __init__(self, responses: dict[str, Any]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    async def get_json(self, source: str, url: str, *, params: Any = None) -> Any:
        self.calls.append((source, url, dict(params or {})))
        outcome = self._responses[source]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome(params or {}) if callable(outcome) else outcome


async def test_resolver_ignores_addresses_and_survives_an_outage() -> None:
    http = FakeHttp({"ban_lookup": lookup()})
    resolver = BanStreetResolver(http)  # type: ignore[arg-type]
    assert await resolver.resolve("49007_7050_00012", *CENTER) is None
    assert http.calls == []
    street = await resolver.resolve("49007_7050", *CENTER)
    assert street is not None
    assert http.calls[0][1].endswith("/lookup/49007_7050")

    down = BanStreetResolver(FakeHttp({"ban_lookup": SourceError("timeout")}))  # type: ignore[arg-type]
    assert await down.resolve("49007_7050", *CENTER) is None


def sale(mutation: str, code: str, price: float, number: int = 12) -> dict[str, Any]:
    return {
        "id_mutation": mutation,
        "date_mutation": "2025-03-01",
        "nature_mutation": "Vente",
        "valeur_fonciere": str(price),
        "type_local": "Appartement",
        "surface_reelle_bati": "50.0",
        "nombre_pieces_principales": "2.0",
        "id_parcelle": f"49007000DE{mutation}",
        "lot1_numero": "1",
        "latitude": "47.4690",
        "longitude": "-0.5529",
        "adresse_code_voie": code,
        "adresse_nom_voie": "RUE SAINT AUBIN" if code == "7050" else "RUE VOISINE",
        "adresse_numero": f"{number}.0",
    }


FEUILLES = {
    "features": [
        {
            "properties": {"code_dep": "49", "code_com": "007", "code_arr": "000", "section": "DE"},
            "geometry": None,
        }
    ]
}
CTX = AuditContext(lat=CENTER[0], lon=CENTER[1], citycode="49007", street=STREET)


async def test_dvf_reports_the_street_and_compares_it_with_its_surroundings() -> None:
    rows = [sale("a", "7050", 150_000), sale("b", "7050", 170_000, 14), sale("c", "1234", 250_000)]
    http = FakeHttp({"apicarto_feuille": FEUILLES, "dvf": {"mutations": rows}})
    data = (await DvfProvider(http).fetch(CTX)).data  # type: ignore[arg-type]

    assert data["perimetre"] == "rue"
    assert data["rue"] == "Rue Saint-Aubin"
    assert data["nb_ventes"] == 2
    assert data["prix_m2_median"] == 3200
    assert "rayon_m" not in data
    assert data["comparaison"] == {
        "perimetre": "sections cadastrales traversées",
        "nb_ventes": 3,
        "prix_m2_median": 3400,
        "ecart_pct": -5.9,
    }
    assert {entry["numero"] for entry in data["dernieres_ventes"]} == {12, 14}
    # Les sections sont cherchées sur l'emprise de la voie, pas sur un cercle.
    assert '"Polygon"' in http.calls[0][2]["geom"]


async def test_dvf_falls_back_to_the_radius_when_the_street_has_no_sale() -> None:
    http = FakeHttp(
        {"apicarto_feuille": FEUILLES, "dvf": {"mutations": [sale("c", "1234", 250_000)]}}
    )
    data = (await DvfProvider(http).fetch(CTX)).data  # type: ignore[arg-type]
    assert data["perimetre"] == "rayon"
    assert data["rayon_m"] == 300
    assert data["nb_ventes"] == 1
    assert "comparaison" not in data


def dpe(number: str, label: str, year: int | None = None) -> dict[str, Any]:
    return {
        "numero_voie_ban": number,
        "etiquette_dpe": label,
        "etiquette_ges": "C",
        "annee_construction": year,
    }


async def test_dpe_lists_the_diagnostics_of_the_street_by_number() -> None:
    rows = [
        dpe("19bis", "D"),
        dpe("2", "E", 1950),
        dpe("2", "E", 1930),
        dpe("2", "C"),
        dpe("10", "B"),
    ]
    http = FakeHttp({"ademe": {"total": 5, "results": rows}})
    data = (await DpeProvider(http).fetch(CTX)).data  # type: ignore[arg-type]

    assert http.calls[0][2]["identifiant_ban_starts"] == "49007_7050_"
    assert data["perimetre"] == "rue"
    assert data["nb_dpe_analyses"] == 5
    assert data["etiquette_dominante"] == "E"
    assert [entry["numero"] for entry in data["par_numero"]] == ["2", "10", "19bis"]
    assert data["par_numero"][0] == {
        "numero": "2",
        "nb_dpe": 3,
        "etiquette_dominante": "E",
        "annee_construction": 1930,
    }


async def test_dpe_falls_back_to_the_radius_when_no_diagnostic_is_tied_to_the_street() -> None:
    def answer(params: dict[str, Any]) -> dict[str, Any]:
        nearby = [{"etiquette_dpe": "C", "etiquette_ges": "B", "_geo_distance": 42.2}]
        return {"total": 1, "results": [] if "identifiant_ban_starts" in params else nearby}

    http = FakeHttp({"ademe": answer})
    data = (await DpeProvider(http).fetch(CTX)).data  # type: ignore[arg-type]
    assert data["perimetre"] == "rayon"
    assert data["rayon_effectif_m"] == 43
    assert len(http.calls) == 2


def test_dpe_numbers_without_label_are_skipped() -> None:
    assert _by_number([dpe("", "A"), {"etiquette_dpe": "B"}]) == []
