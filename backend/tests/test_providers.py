"""Logique de transformation des sources (sans réseau)."""

from typing import Any

import pytest

from app.services.providers.dvf import _distance_to_feature, _section_key, build_sales, summarize
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


def test_dvf_summary_details_flats_by_size() -> None:
    rows = [
        dvf_row(id_mutation="a", valeur_fonciere="400000.0"),  # 2 pièces, 50 m²
        dvf_row(id_mutation="b", valeur_fonciere="300000.0", surface_reelle_bati="30.0"),
        dvf_row(
            id_mutation="c",
            valeur_fonciere="630000.0",
            surface_reelle_bati="90.0",
            nombre_pieces_principales="4.0",
        ),
        # Sans nombre de pièces, ou maison : hors du détail par taille.
        dvf_row(id_mutation="d", nombre_pieces_principales=""),
        dvf_row(id_mutation="e", type_local="Maison", nombre_pieces_principales="5.0"),
    ]
    summary = summarize(build_sales(rows, *ORIGIN, radius_m=300))
    assert summary["par_taille"] == {
        "t1_t2": {"nb_ventes": 2, "prix_m2_median": 9000, "surface_mediane_m2": 40},
        "t3_plus": {"nb_ventes": 1, "prix_m2_median": 7000, "surface_mediane_m2": 90},
    }


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


def test_dvf_section_distance_is_zero_inside_and_grows_outside() -> None:
    square = [[[2.0, 48.0], [2.01, 48.0], [2.01, 48.01], [2.0, 48.01], [2.0, 48.0]]]
    inside = {"geometry": {"type": "Polygon", "coordinates": square}}
    multi = {"geometry": {"type": "MultiPolygon", "coordinates": [square]}}
    assert _distance_to_feature(inside, 48.005, 2.005) == 0
    assert _distance_to_feature(multi, 48.005, 2.005) == 0
    # 0,01° de latitude au nord du bord : environ 1,1 km.
    assert 1000 < _distance_to_feature(inside, 48.02, 2.005) < 1200
    assert _distance_to_feature({"geometry": None}, 48.0, 2.0) == 0


def priced(mutation: str, when: str, price: float) -> dict[str, Any]:
    return dvf_row(id_mutation=mutation, date_mutation=when, valeur_fonciere=str(price))


def window_of(old: int, recent: int, *, place: tuple[str, str] | None = None) -> dict[str, Any]:
    """Synthèse de `old` ventes de 2022 à 6 000 €/m² et `recent` ventes de 2025 à 7 200 €/m²."""

    def sale(name: str, year: int, index: int, price: float) -> dict[str, Any]:
        month, day = index % 9 + 1, index % 27 + 1
        row = priced(f"{name}{index}", f"{year}-0{month}-{day:02d}", price)
        if place is not None:
            row["latitude"], row["longitude"] = place
        return row

    rows = [sale("old", 2022, i, 300_000) for i in range(old)]
    rows += [sale("new", 2025, i, 360_000) for i in range(recent)]
    return summarize(build_sales(rows, *ORIGIN, radius_m=300))


def test_dvf_recent_median_covers_the_last_24_months_of_known_sales() -> None:
    summary = window_of(20, 20)
    window = summary["recent"]
    assert window["mois"] == 24
    # La fenêtre se termine à la dernière vente publiée, pas à la date du jour.
    assert window["jusqu_au"].startswith("2025-")
    assert window["nb_ventes"] == 20
    assert window["prix_m2_median"] > summary["prix_m2_median"]
    assert window["par_type"] == {"appartement": {"nb_ventes": 20, "prix_m2_median": 7200}}
    # Les ventes de 2022 sont à plus de 24 mois : elles servent de période de comparaison.
    assert (window["tendance"], window["tendance_pct"]) == ("en hausse", 20.0)


def test_dvf_trend_is_only_quantified_with_enough_sales_in_both_periods() -> None:
    # Entre 5 et 19 ventes : le sens de l'évolution, sans pourcentage trompeur.
    small = window_of(5, 30)["recent"]
    assert (small["tendance"], small["tendance_pct"]) == ("en hausse", None)
    # Sur un petit échantillon, un écart de quelques points reste « stable ».
    slight = summarize(
        build_sales(
            [priced(f"o{i}", f"2022-0{i + 1}-15", 300_000) for i in range(5)]
            + [priced(f"n{i}", f"2025-0{i + 1}-15", 318_000) for i in range(5)],
            *ORIGIN,
            radius_m=300,
        )
    )["recent"]
    assert (slight["tendance"], slight["tendance_pct"]) == ("stable", None)
    # Moins de cinq ventes avant : rien n'est avancé.
    none = window_of(4, 30)["recent"]
    assert (none["tendance"], none["tendance_pct"]) == (None, None)
    assert window_of(30, 4)["recent"] is None


def test_dvf_map_points_group_the_sales_of_one_building() -> None:
    summary = window_of(3, 4, place=("48.8628", "2.3377"))
    # Sept ventes à la même adresse : un seul point, avec leur médiane et la dernière année.
    assert summary["points"] == [[2.3377, 48.8628, 7200, 7, 2025]]
