"""Logique de transformation des sources (sans réseau)."""

from typing import Any

import pytest

from app.services.providers.dvf import _section_key, build_sales, summarize
from app.services.providers.poi import build_query, classify
from app.services.solar import horizon_profile, sun_position, sunlight_scores

ORIGIN = (48.8627, 2.3376)


def dvf_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id_mutation": "2024-1",
        "date_mutation": "2024-03-01",
        "nature_mutation": "Vente",
        "valeur_fonciere": "500000.0",
        "id_parcelle": "75101000AU0008",
        "lot1_numero": "1",
        "type_local": "Appartement",
        "surface_reelle_bati": "50.0",
        "nombre_pieces_principales": "2.0",
        "latitude": "48.8628",
        "longitude": "2.3377",
    }
    row.update(overrides)
    return row


def test_dvf_groups_lots_and_ignores_outbuildings() -> None:
    rows = [
        dvf_row(),
        dvf_row(),  # doublon strict
        dvf_row(lot1_numero="2", surface_reelle_bati="30.0"),
        dvf_row(lot1_numero="3", type_local="Dépendance", surface_reelle_bati="nan"),
    ]
    sales = build_sales(rows, *ORIGIN, radius_m=300)
    assert len(sales) == 1
    assert sales[0].surface_m2 == 80
    assert round(sales[0].price_m2) == 6250
    assert sales[0].kind == "appartement"


@pytest.mark.parametrize(
    "overrides",
    [
        {"nature_mutation": "Echange"},
        {"type_local": "Local industriel. commercial ou assimilé"},
        {"latitude": "48.90"},  # hors rayon
        {"valeur_fonciere": "nan"},
        {"valeur_fonciere": "1.0"},  # prix au m² invraisemblable
        {"surface_reelle_bati": "nan"},
    ],
)
def test_dvf_rejects_unusable_mutations(overrides: dict[str, Any]) -> None:
    assert build_sales([dvf_row(**overrides)], *ORIGIN, radius_m=300) == []


def test_dvf_summary_medians_by_year_and_kind() -> None:
    rows = [
        dvf_row(id_mutation="a", date_mutation="2023-05-01", valeur_fonciere="400000.0"),
        dvf_row(id_mutation="b", date_mutation="2024-05-01", valeur_fonciere="500000.0"),
        dvf_row(
            id_mutation="c",
            date_mutation="2024-06-01",
            valeur_fonciere="900000.0",
            type_local="Maison",
            surface_reelle_bati="100.0",
        ),
    ]
    summary = summarize(build_sales(rows, *ORIGIN, radius_m=300))
    assert summary["nb_ventes"] == 3
    assert summary["prix_m2_median"] == 9000
    assert summary["par_type"]["maison"] == {"nb_ventes": 1, "prix_m2_median": 9000}
    assert summary["historique"] == [
        {"annee": 2023, "nb_ventes": 1, "prix_m2_median": 8000},
        {"annee": 2024, "nb_ventes": 2, "prix_m2_median": 9500},
    ]
    assert summary["dernieres_ventes"][0]["date"] == "2024-06-01"


def test_dvf_section_key_handles_arrondissements_and_short_sections() -> None:
    paris = {
        "code_dep": "75",
        "code_com": "056",
        "code_arr": "101",
        "com_abs": "000",
        "section": "AU",
    }
    rural = {
        "code_dep": "49",
        "code_com": "007",
        "code_arr": "000",
        "com_abs": "000",
        "section": "B",
    }
    assert _section_key(paris) == ("75101", "000AU")
    assert _section_key(rural) == ("49007", "0000B")
    assert _section_key({"section": "A"}) is None


def test_poi_classification_and_query() -> None:
    assert classify({"railway": "station", "name": "Châtelet"}) == ("transports", "station")
    assert classify({"amenity": "pharmacy"}) == ("sante", "pharmacy")
    assert classify({"amenity": "bar"}) is None
    query = build_query(48.86, 2.33)
    assert query.startswith("[out:json][timeout:4];")
    assert 'amenity~"^(doctors|kindergarten|pharmacy|school)$"' in query


def test_sun_is_south_at_noon_and_higher_in_summer() -> None:
    winter_elevation, winter_azimuth = sun_position(48.86, 355, 12.0)
    summer_elevation, summer_azimuth = sun_position(48.86, 172, 12.0)
    assert winter_azimuth == pytest.approx(180, abs=0.5)
    assert summer_azimuth == pytest.approx(180, abs=0.5)
    assert winter_elevation == pytest.approx(17.7, abs=0.5)
    assert summer_elevation == pytest.approx(64.6, abs=0.5)


def test_sunlight_score_drops_with_southern_relief() -> None:
    distances = [100.0, 1000.0]
    flat = horizon_profile(100.0, [[100.0, 100.0]] * 8, distances)
    assert sunlight_scores(48.86, flat) == {"annuel": 100, "solstice_hiver": 100}

    # Crête de 400 m à 1 km du sud-est au sud-ouest (index 3 à 5) : ~21,7° de masque,
    # au-dessus du soleil de midi au solstice d'hiver (17,7°) mais pas en été (64,6°).
    rings = [[100.0, 100.0] for _ in range(8)]
    for index in (3, 4, 5):
        rings[index] = [100.0, 500.0]
    masked = horizon_profile(100.0, rings, distances)
    assert masked[4] == pytest.approx(21.7, abs=0.5)
    scores = sunlight_scores(48.86, masked)
    assert scores["solstice_hiver"] == 0
    assert 50 < scores["annuel"] < 100
