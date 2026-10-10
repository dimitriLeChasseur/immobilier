"""Scripts des cartes de bruit : recensement des flux et conversion des zones.

Ces scripts sont autonomes (dépendances déclarées en tête de fichier) et hors du backend :

    uv run --no-project --with pytest --with geopandas --with pyogrio --with requests \\
        --with sqlalchemy --with "psycopg[binary]" pytest scripts/tests

Aucun appel réseau ni accès à la base : seules les fonctions de décision sont jouées.
"""

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import geopandas as gpd
import pytest
from shapely.geometry import GeometryCollection, LineString, MultiPolygon, Polygon

SCRIPTS = Path(__file__).resolve().parent.parent


def load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


discover = load("discover_bruit_sources")
ingest = load("ingest_bruit_lden")

SQUARE = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
# Nœud papillon : polygone invalide, que la réparation découpe en deux triangles.
BOWTIE = Polygon([(0, 0), (10, 10), (10, 0), (0, 10)])
SOURCE = ingest.Source(
    "d49-infra_r_a_ld_s_049", "wfs", "https://exemple.invalid/wfs", "49", "N_R_A"
)


# --- Recensement -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("layer", "kept"),
    [
        ("N_BRUIT_ZBR_INFRA_R_A_LD_S_049", True),
        ("ms:N_BRUIT_ZBR_INFRA_F_A_LDEN_S_075", True),
        ("n_bruit_zbr_infra_r_a_ld_s_02a", True),
        # Type C (dépassement de seuil) et indice de nuit : hors périmètre.
        ("N_BRUIT_ZBR_INFRA_R_C_LD_S_049", False),
        ("N_BRUIT_ZBR_INFRA_R_A_LN_S_049", False),
        ("N_BRUIT_PPBE_S_049", False),
    ],
)
def test_only_type_a_lden_layers_are_kept(layer: str, kept: bool) -> None:
    assert bool(discover.TYPE_A_LDEN.search(layer)) is kept


@pytest.mark.parametrize(
    ("layer", "expected"),
    [
        ("N_BRUIT_ZBR_INFRA_R_A_LD_S_049", ("49", False)),
        ("N_BRUIT_ZBR_INFRA_R_A_LD_S_075", ("75", False)),
        ("N_BRUIT_ZBR_INFRA_R_A_LD_S_02A", ("2A", False)),
        ("N_BRUIT_ZBR_INFRA_R_A_LD_S_974", ("974", False)),
        ("N_BRUIT_ZBR_INFRA_R_A_LD_S_069_2017", ("69", True)),
        ("N_BRUIT_ZBR_SANS_DEPARTEMENT", None),
    ],
)
def test_department_and_edition_are_read_from_the_layer_name(
    layer: str, expected: tuple[str, bool] | None
) -> None:
    assert discover.departement_of(layer) == expected


def test_dated_editions_give_way_to_a_current_layer_of_the_same_department() -> None:
    entries = [
        {"id": "d69-b", "departement": "69", "millesime": True},
        {"id": "d69-a", "departement": "69", "millesime": False},
        # Aucun flux courant dans le 38 : son édition datée est la seule, on la garde.
        {"id": "d38-a", "departement": "38", "millesime": True},
    ]
    kept = discover.current_editions(entries)
    assert [entry["id"] for entry in kept] == ["d38-a", "d69-a"]
    assert all("millesime" not in entry for entry in kept)


def test_manual_deactivations_survive_a_new_census(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    previous = tmp_path / "sources.json"
    previous.write_text(
        json.dumps({"sources": [{"id": "d08-x", "actif": False, "note": "HTTP 500 durable"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(discover, "SOURCES_FILE", previous)
    entries: list[dict[str, str | bool]] = [{"id": "d08-x"}, {"id": "d49-y"}]
    discover.keep_manual_settings(entries)
    assert entries == [{"id": "d08-x", "actif": False, "note": "HTTP 500 durable"}, {"id": "d49-y"}]


# --- Sélection des sources ---------------------------------------------------------------


@pytest.fixture
def sources_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "sources.json"
    entry = {"type": "wfs", "url": "https://exemple.invalid/wfs"}
    path.write_text(
        json.dumps(
            {
                "sources": [
                    {**entry, "id": "d49-a", "departement": "49", "couche": "A"},
                    {**entry, "id": "d49-b", "departement": "49", "couche": "B", "actif": False},
                    {**entry, "id": "d2a-a", "departement": "2A", "emprise": [8, 41, 9, 42]},
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(ingest, "SOURCES_FILE", path)
    return path


def test_disabled_sources_are_skipped_unless_asked_by_name(sources_file: Path) -> None:
    assert [source.id for source in ingest.load_sources(None, None)] == ["d49-a", "d2a-a"]
    assert [source.id for source in ingest.load_sources("49", None)] == ["d49-a"]
    assert [source.id for source in ingest.load_sources(None, ["d49-b"])] == ["d49-b"]
    [corsica] = ingest.load_sources("2a", None)
    assert corsica.bbox == (8, 41, 9, 42)
    assert ingest.all_source_ids() == ["d49-a", "d49-b", "d2a-a"]


def test_infrastructure_falls_back_on_the_layer_name() -> None:
    assert SOURCE.default_infrastructure == "route"
    rail = ingest.Source("d75-x", "wfs", "u", "75", "N_BRUIT_ZBR_INFRA_F_A_LD_S_075")
    assert rail.default_infrastructure == "fer"
    assert ingest.Source("d75-ratp_a_ld", "wfs", "u", "75").default_infrastructure == "fer"


# --- Pages du service --------------------------------------------------------------------


def test_an_empty_page_is_read_again_in_halves(monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[tuple[int, int]] = []

    def fetch_page(url: str, params: dict[str, str]) -> bytes:
        start, count = int(params["STARTINDEX"]), int(params["COUNT"])
        asked.append((start, count))
        if count > 2:
            raise ingest.EmptyResponseError("vide")
        return f"{start}+{count}".encode()

    monkeypatch.setattr(ingest, "fetch_page", fetch_page)
    pages = ingest.fetch_split("u", {"STARTINDEX": "0", "COUNT": "8"})
    assert pages == [b"0+2", b"2+2", b"4+2", b"6+2"]
    assert asked[0] == (0, 8)


def test_a_single_unreadable_feature_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def always_empty(url: str, params: dict[str, str]) -> bytes:
        raise ingest.EmptyResponseError("vide")

    monkeypatch.setattr(ingest, "fetch_page", always_empty)
    with pytest.raises(ingest.EmptyResponseError):
        ingest.fetch_split("u", {"STARTINDEX": "0", "COUNT": "1"})


# --- Conversion des zones ----------------------------------------------------------------


def test_repaired_geometries_keep_their_surfaces_only() -> None:
    assert ingest.to_multipolygon(None) is None
    assert ingest.to_multipolygon(Polygon()) is None
    assert ingest.to_multipolygon(LineString([(0, 0), (1, 1)])) is None

    repaired = ingest.to_multipolygon(BOWTIE)
    assert isinstance(repaired, MultiPolygon) and repaired.is_valid
    assert len(repaired.geoms) == 2

    mixed = GeometryCollection([MultiPolygon([SQUARE]), LineString([(0, 0), (5, 5)])])
    assert ingest.polygons_of(mixed) == [SQUARE]


def frame(rows: list[dict[str, object]]) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")


def test_zones_are_converted_whatever_the_producer_calls_its_columns() -> None:
    rows = ingest.to_rows(
        frame(
            [
                # Attributs normalisés, en majuscules.
                {
                    "geometry": SQUARE,
                    "LEGENDE": "65-70",
                    "TYPESOURCE": "F",
                    "IDZONBRUIT": "Z1",
                    "CODEDEPT": "049",
                    "ANNEE": "2022",
                    "CODINFRA": "L515",
                },
                # Autoroute concédée : minuscules, classe dans ISOPHONE, infrastructure tue.
                {"geometry": SQUARE, "isophone": "LD75", "idzonbruit": "Z2"},
                # RATP : borne basse dans DB_LO.
                {"geometry": SQUARE, "Db_lo": "60"},
            ]
        ),
        SOURCE,
    )
    assert [(row["db_min"], row["infrastructure"], row["code_dept"]) for row in rows] == [
        (65, "fer", "49"),
        (75, "route", "49"),
        (60, "route", "49"),
    ]
    assert rows[0]["annee"] == 2022 and rows[0]["code_infra"] == "L515"
    assert rows[1]["annee"] is None
    # Le rang distingue les entités qui partagent un identifiant de zone.
    assert [row["id_zone"] for row in rows] == [
        "d49-infra_r_a_ld_s_049:Z1:0",
        "d49-infra_r_a_ld_s_049:Z2:1",
        "d49-infra_r_a_ld_s_049:zone:2",
    ]
    assert all(row["source_id"] == SOURCE.id and row["wkb"] for row in rows)


def test_unusable_zones_are_dropped() -> None:
    rows = ingest.to_rows(
        frame(
            [
                {"geometry": SQUARE, "LEGENDE": "55-60", "INDICETYPE": "LN"},  # indice de nuit
                {"geometry": SQUARE, "LEGENDE": "02"},  # code sans niveau sonore
                {"geometry": SQUARE, "LEGENDE": "150"},  # hors de l'échelle
                {"geometry": SQUARE, "LEGENDE": None},
                {"geometry": LineString([(0, 0), (1, 1)]), "LEGENDE": "65"},
                {"geometry": SQUARE, "LEGENDE": "55-60", "INDICETYPE": "ld"},
            ]
        ),
        SOURCE,
    )
    assert [row["db_min"] for row in rows] == [55]


def test_a_bounding_box_keeps_only_part_of_the_layer() -> None:
    far = Polygon([(50, 50), (51, 50), (51, 51), (50, 51)])
    boxed = ingest.Source("d2a-a", "wfs", "u", "2A", None, (-1, -1, 20, 20))
    rows = ingest.to_rows(
        frame([{"geometry": SQUARE, "LEGENDE": "60"}, {"geometry": far, "LEGENDE": "70"}]), boxed
    )
    assert [row["db_min"] for row in rows] == [60]
    assert rows[0]["code_dept"] == "2A"
