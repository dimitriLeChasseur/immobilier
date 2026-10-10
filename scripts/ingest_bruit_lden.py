#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "geopandas>=1.0",
#   "pyogrio>=0.9",
#   "requests>=2.32",
#   "sqlalchemy>=2.0",
#   "psycopg[binary]>=3.2",
# ]
# ///
"""Ingestion des cartes de bruit stratégiques (indice Lden) dans PostGIS.

Script autonome, indépendant du backend, prévu pour une tâche planifiée :

    uv run scripts/ingest_bruit_lden.py                    # toutes les sources
    uv run scripts/ingest_bruit_lden.py --departement 49
    uv run scripts/ingest_bruit_lden.py --source d49-infra_r_a_ld_s_049

Exemple de crontab (le 2 de chaque mois à 4 h) :

    0 4 2 * * cd /opt/project-immobilier && uv run scripts/ingest_bruit_lden.py >> /var/log/immo-bruit.log 2>&1

Pour chaque source de infra/bruit/sources.json (écrit par discover_bruit_sources.py) :
  1. lecture du flux WFS par pages ou, à défaut, d'un fichier Shapefile zippé / GeoJSON ;
  2. simplification légère puis reprojection vers EPSG:4326 (flux publiés en Lambert 93) ;
  3. upsert par lots dans immo.geo_bruit_lden, puis purge des zones disparues de la source.
Un passage complet retire aussi les zones des sources qui ne figurent plus dans le fichier.

Connexion : variable BRUIT_DATABASE_URL, sinon reconstruite depuis le fichier .env du projet
(rôle immo_app sur le port local de la base).
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import os
import re
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import requests
from pyogrio.errors import DataSourceError
from pyproj import Transformer
from shapely import make_valid
from shapely.errors import GEOSException
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger("ingest_bruit_lden")

ROOT = Path(__file__).resolve().parent.parent
SOURCES_FILE = ROOT / "infra" / "bruit" / "sources.json"
USER_AGENT = "AuditImmobilier/0.1 (ingestion bruit)"
HTTP_TIMEOUT_S = 300
BATCH_SIZE = 200
WFS_PAGE_SIZE = 500
# Une page restée vide est relue en morceaux de plus en plus petits, jusqu'à l'entité seule :
# certaines couches tiennent en quelques polygones couvrant tout le département.
WFS_MIN_PAGE_SIZE = 1
# Les contours sont issus d'un modèle : un mètre d'écart est sans effet, et allège la base.
SIMPLIFY_TOLERANCE_M = 1.0
EMPTY_RETRIES = 3
EMPTY_RETRY_DELAY_S = 4
WGS84, LAMBERT93 = 4326, 2154

# Schéma COVADIS des zones de bruit : TYPESOURCE -> nature de l'infrastructure.
INFRASTRUCTURES = {"R": "route", "F": "fer", "A": "air", "I": "industrie"}
DB_RANGE = range(30, 101)

UPSERT = text(
    """
    INSERT INTO immo.geo_bruit_lden
        (id_zone, source_id, code_dept, infrastructure, code_infra, annee, db_min, geom)
    VALUES (:id_zone, :source_id, :code_dept, :infrastructure, :code_infra, :annee, :db_min,
            extensions.ST_Multi(extensions.ST_GeomFromWKB(:wkb, 4326)))
    ON CONFLICT (id_zone) DO UPDATE SET
        source_id = EXCLUDED.source_id,
        code_dept = EXCLUDED.code_dept,
        infrastructure = EXCLUDED.infrastructure,
        code_infra = EXCLUDED.code_infra,
        annee = EXCLUDED.annee,
        db_min = EXCLUDED.db_min,
        geom = EXCLUDED.geom,
        imported_at = now()
    """
)
PURGE = text(
    "DELETE FROM immo.geo_bruit_lden WHERE source_id = :source_id AND NOT (id_zone = ANY(:kept))"
)
PURGE_UNKNOWN_SOURCES = text("DELETE FROM immo.geo_bruit_lden WHERE NOT (source_id = ANY(:known))")


class EmptyResponseError(ValueError):
    """Le service a répondu 200 sans contenu (requête trop lourde pour lui)."""


@dataclass(frozen=True)
class Source:
    id: str
    kind: str
    url: str
    departement: str
    layer: str | None = None
    # (ouest, sud, est, nord) pour ne garder qu'une partie de la couche ; None : tout.
    bbox: tuple[float, float, float, float] | None = None

    @property
    def default_infrastructure(self) -> str:
        """Nature de l'infrastructure d'après le nom de la couche, si l'entité ne la dit pas."""
        name = (self.layer or self.id).upper()
        return "fer" if re.search(r"_F_|SNCF|RATP|FER", name) else "route"


def all_source_ids() -> list[str]:
    config = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
    return [entry["id"] for entry in config["sources"]]


def load_sources(departement: str | None, source_ids: list[str] | None) -> list[Source]:
    config = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
    sources = []
    for entry in config["sources"]:
        if departement and entry["departement"].upper() != departement.upper():
            continue
        if source_ids and entry["id"] not in source_ids:
            continue
        # Une source désactivée n'est traitée que si elle est demandée nommément.
        if not entry.get("actif", True) and entry["id"] not in (source_ids or []):
            continue
        bbox = tuple(entry["emprise"]) if entry.get("emprise") else None
        sources.append(
            Source(
                entry["id"],
                entry["type"],
                entry["url"],
                entry["departement"],
                entry.get("couche"),
                bbox,  # type: ignore[arg-type]
            )
        )
    return sources


def database_url() -> str:
    explicit = os.environ.get("BRUIT_DATABASE_URL")
    if explicit:
        return explicit
    env: dict[str, str] = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip().strip('"')
    password, port = env["IMMO_APP_DB_PASSWORD"], env.get("DB_HOST_PORT", "5433")
    return f"postgresql+psycopg://immo_app:{password}@127.0.0.1:{port}/{env.get('POSTGRES_DB', 'postgres')}"


def http_get(url: str, params: dict[str, str] | None = None) -> bytes:
    response = requests.get(
        url, params=params, timeout=HTTP_TIMEOUT_S, headers={"User-Agent": USER_AGENT}
    )
    response.raise_for_status()
    return response.content


def wfs_layer(url: str) -> str:
    """Nom de la première couche annoncée par le service (un flux Géo-IDE = une couche)."""
    capabilities = http_get(
        url, {"SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetCapabilities"}
    )
    match = re.search(rb"<FeatureType>.*?<Name>([^<]+)</Name>", capabilities, re.DOTALL)
    if match is None:
        raise ValueError("aucune couche annoncée par le service WFS")
    return match.group(1).decode()


def fetch_page(url: str, params: dict[str, str]) -> bytes:
    """Une page WFS ; les réponses vides (200 sans contenu) sont retentées, car souvent passagères."""
    for attempt in range(1, EMPTY_RETRIES + 1):
        content = http_get(url, params)
        if content.strip():
            return content
        if attempt < EMPTY_RETRIES:
            time.sleep(EMPTY_RETRY_DELAY_S * attempt)
    raise EmptyResponseError(f"réponse vide du service WFS (page {params['STARTINDEX']})")


def fetch_split(url: str, params: dict[str, str]) -> list[bytes]:
    """Contenu d'une page, relue en deux moitiés tant que le service la rend vide.

    Une page trop lourde pour le service échoue en bloc : ses moitiés passent souvent.
    """
    try:
        return [fetch_page(url, params)]
    except EmptyResponseError:
        start, count = int(params["STARTINDEX"]), int(params["COUNT"])
        if count // 2 < WFS_MIN_PAGE_SIZE:
            raise
        half = count // 2
        first = fetch_split(url, {**params, "COUNT": str(half)})
        second = fetch_split(
            url, {**params, "STARTINDEX": str(start + half), "COUNT": str(count - half)}
        )
        return first + second


def feature_count(url: str, layer: str) -> int | None:
    """Nombre d'entités de la couche, tel qu'annoncé par le service."""
    content = http_get(
        url,
        {
            "SERVICE": "WFS",
            "VERSION": "2.0.0",
            "REQUEST": "GetFeature",
            "TYPENAMES": layer,
            "RESULTTYPE": "hits",
        },
    )
    match = re.search(rb'numberMatched="(\d+)"', content)
    return int(match.group(1)) if match else None


def page_params(layer: str, start: int, bbox_filter: str | None) -> dict[str, str]:
    params = {
        "SERVICE": "WFS",
        "VERSION": "2.0.0",
        "REQUEST": "GetFeature",
        "TYPENAMES": layer,
        "COUNT": str(WFS_PAGE_SIZE),
        "STARTINDEX": str(start),
    }
    if bbox_filter:
        params["BBOX"] = bbox_filter
    return params


def fetch_tolerant_page(
    source: Source, params: dict[str, str], total: int | None
) -> list[bytes] | None:
    """Contenu de la page (en un ou plusieurs morceaux), None si la dernière reste vide.

    Observé sur de très grosses couches : on garde alors le reste plutôt que de tout
    abandonner, en le signalant. Une page vide ailleurs reste une erreur.
    """
    start = int(params["STARTINDEX"])
    try:
        return fetch_split(source.url, params)
    except EmptyResponseError:
        if total is None or start + WFS_PAGE_SIZE < total:
            raise
        logger.warning(
            "%s : dernière page illisible, %d entités sur %d ne sont pas chargées",
            source.id,
            total - start,
            total,
        )
        return None


def read_gml(content: bytes) -> gpd.GeoDataFrame:
    try:
        return gpd.read_file(io.BytesIO(content))
    except (DataSourceError, IndexError) as exc:
        # Réponse tronquée ou sans couche lisible : la source échoue, pas tout le passage.
        raise ValueError(f"réponse WFS illisible ({type(exc).__name__})") from exc


def wfs_pages(source: Source, layer: str, bbox_filter: str | None) -> list[gpd.GeoDataFrame]:
    # Sans filtre spatial, on connaît le total : une dernière page vide peut être tolérée.
    total = None if bbox_filter else feature_count(source.url, layer)
    pages: list[gpd.GeoDataFrame] = []
    while True:
        params = page_params(layer, len(pages) * WFS_PAGE_SIZE, bbox_filter)
        chunks = fetch_tolerant_page(source, params, total)
        if chunks is None:
            return pages
        if any(b"ExceptionReport" in chunk[:2000] for chunk in chunks):
            raise ValueError(f"le service WFS a refusé la requête : {chunks[0][:300]!r}")
        frames = [read_gml(chunk) for chunk in chunks if b"<wfs:member>" in chunk]
        if not frames:
            return pages
        page = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=frames[0].crs)
        pages.append(page.set_crs(LAMBERT93) if page.crs is None else page)
        if len(page) < WFS_PAGE_SIZE:
            return pages


def read_wfs(source: Source) -> gpd.GeoDataFrame:
    """Lit la couche par pages : les gros départements font échouer une requête unique."""
    layer = source.layer or wfs_layer(source.url)
    if source.bbox is None:
        pages = wfs_pages(source, layer, None)
    else:
        to_lambert = Transformer.from_crs(WGS84, LAMBERT93, always_xy=True)
        west, south, east, north = source.bbox
        xmin, ymin = to_lambert.transform(west, south)
        xmax, ymax = to_lambert.transform(east, north)
        bbox_filter = (
            f"{xmin:.0f},{ymin:.0f},{xmax:.0f},{ymax:.0f},urn:ogc:def:crs:EPSG::{LAMBERT93}"
        )
        try:
            pages = wfs_pages(source, layer, bbox_filter)
        except EmptyResponseError:
            # Certains services échouent sur le filtre spatial : on lit alors toute la
            # couche, le découpage à l'emprise étant refait après reprojection.
            logger.warning("%s : filtre BBOX refusé, lecture de la couche entière", source.id)
            pages = wfs_pages(source, layer, None)
    if not pages:
        return gpd.GeoDataFrame({"geometry": []}, geometry="geometry", crs=LAMBERT93)
    return gpd.GeoDataFrame(pd.concat(pages, ignore_index=True), crs=pages[0].crs)


def read_file(source: Source) -> gpd.GeoDataFrame:
    """Repli sans WFS : archive Shapefile (.zip) ou GeoJSON, locale ou distante."""
    if not source.url.startswith(("http://", "https://")):
        return gpd.read_file(source.url)
    suffix = ".zip" if source.url.lower().split("?")[0].endswith(".zip") else ".geojson"
    with tempfile.NamedTemporaryFile(suffix=suffix) as handle:
        handle.write(http_get(source.url))
        handle.flush()
        # GDAL lit directement le Shapefile contenu dans une archive zip.
        return gpd.read_file(f"zip://{handle.name}" if suffix == ".zip" else handle.name)


def to_multipolygon(geometry: BaseGeometry | None) -> MultiPolygon | None:
    if geometry is None or geometry.is_empty:
        return None
    try:
        valid = geometry if geometry.is_valid else make_valid(geometry)
    except GEOSException:
        # Géométrie que GEOS ne sait pas réparer : la zone est écartée, pas la couche.
        return None
    polygons = polygons_of(valid)
    return MultiPolygon(polygons) if polygons else None


def polygons_of(geometry: BaseGeometry) -> list[Polygon]:
    """Polygones d'une géométrie, y compris ceux qu'une réparation a rangés dans une collection.

    Réparer un multipolygone invalide rend souvent une collection mêlant multipolygone et
    lignes résiduelles : seules les surfaces sont gardées.
    """
    if isinstance(geometry, Polygon):
        return [geometry]
    return [polygon for part in getattr(geometry, "geoms", []) for polygon in polygons_of(part)]


def attribute(row: Any, name: str) -> str | None:
    """Valeur d'un attribut sans tenir compte de la casse (LEGENDE, legende ou Legende)."""
    for key in (name, name.lower(), name.capitalize()):
        value = row.get(key)
        if value is not None and str(value) not in {"", "nan", "None", "NaT"}:
            return str(value).strip()
    return None


def to_row(row: Any, source: Source, suffix: str) -> dict[str, Any] | None:
    """Ligne prête à insérer ; None si l'entité n'est pas une zone Lden exploitable."""
    if (attribute(row, "INDICETYPE") or "LD").upper() != "LD":
        return None
    geometry = to_multipolygon(row.geometry)
    # La classe se lit dans LEGENDE ; quelques producteurs la nomment ISOPHONE (autoroutes
    # concédées) ou DB_LO, borne basse de la classe (RATP).
    level = re.search(
        r"\d{2,3}",
        attribute(row, "LEGENDE") or attribute(row, "ISOPHONE") or attribute(row, "DB_LO") or "",
    )
    infrastructure = INFRASTRUCTURES.get(
        (attribute(row, "TYPESOURCE") or "")[:1].upper(), source.default_infrastructure
    )
    if geometry is None or level is None:
        return None
    if int(level.group()) not in DB_RANGE:
        return None
    year = attribute(row, "ANNEE")
    return {
        "id_zone": f"{source.id}:{attribute(row, 'IDZONBRUIT') or 'zone'}:{suffix}",
        "source_id": source.id,
        "code_dept": (attribute(row, "CODEDEPT") or "")[-3:].lstrip("0") or source.departement,
        "infrastructure": infrastructure,
        "code_infra": attribute(row, "CODINFRA"),
        "annee": int(year) if year and year.isdigit() else None,
        "db_min": int(level.group()),
        "wkb": geometry.wkb,
    }


def to_rows(frame: gpd.GeoDataFrame, source: Source) -> list[dict[str, Any]]:
    """Simplifie, reprojette, découpe à l'emprise éventuelle et garde les zones exploitables."""
    if frame.crs is not None and frame.crs.to_epsg() == LAMBERT93:
        frame = frame.set_geometry(frame.geometry.simplify(SIMPLIFY_TOLERANCE_M))
    clipped = frame.to_crs(WGS84)
    if source.bbox is not None:
        west, south, east, north = source.bbox
        clipped = clipped.cx[west:east, south:north]
    rows: list[dict[str, Any]] = []
    for _, row in clipped.iterrows():
        # Le rang rend l'identifiant unique : plusieurs entités partagent un IDZONBRUIT.
        converted = to_row(row, source, str(len(rows)))
        if converted is not None:
            rows.append(converted)
    return rows


def store(engine: Engine, source: Source, rows: list[dict[str, Any]]) -> None:
    with engine.begin() as connection:
        for start in range(0, len(rows), BATCH_SIZE):
            connection.execute(UPSERT, rows[start : start + BATCH_SIZE])
        connection.execute(
            PURGE, {"source_id": source.id, "kept": [row["id_zone"] for row in rows]}
        )


def ingest(engine: Engine, source: Source) -> int:
    frame = read_wfs(source) if source.kind == "wfs" else read_file(source)
    rows = to_rows(frame, source)
    if not rows:
        # Une source vide est plus probablement une panne qu'une disparition du bruit :
        # on conserve les données déjà chargées.
        raise ValueError(f"aucune zone exploitable sur {len(frame)} entités lues")
    store(engine, source, rows)
    return len(rows)


def run(engine: Engine, source: Source) -> bool:
    """Charge une source ; son échec n'interrompt pas les autres."""
    try:
        count = ingest(engine, source)
    # OSError couvre les erreurs réseau de requests (RequestException en dérive).
    except (DataSourceError, ValueError, OSError, GEOSException, SQLAlchemyError) as exc:
        logger.error("%s : échec (%s) %s", source.id, type(exc).__name__, str(exc)[:200])
        return False
    except Exception:
        # Plusieurs centaines de flux hétérogènes : une surprise sur l'un ne doit pas
        # faire perdre les autres. La trace complète part au journal.
        logger.exception("%s : échec inattendu", source.id)
        return False
    logger.info("%s : %d zones de bruit chargées", source.id, count)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--departement", help="ne traiter que ce département (ex. 49, 2A)")
    parser.add_argument(
        "--source",
        action="append",
        help="ne traiter que cette source (id de sources.json) ; l'option peut être répétée",
    )
    parser.add_argument(
        "--parallele", type=int, default=4, help="sources lues en même temps (défaut : 4)"
    )
    arguments = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    sources = load_sources(arguments.departement, arguments.source)
    if not sources:
        logger.error("Aucune source ne correspond à la sélection")
        return 2
    engine = create_engine(database_url())
    with ThreadPoolExecutor(max(1, arguments.parallele)) as pool:
        results = list(pool.map(lambda source: run(engine, source), sources))
    failures = results.count(False)
    if not arguments.departement and not arguments.source:
        # Passage complet : les zones d'une source retirée du fichier n'ont plus lieu d'être.
        with engine.begin() as connection:
            connection.execute(PURGE_UNKNOWN_SOURCES, {"known": all_source_ids()})
    logger.info("%d source(s) chargée(s), %d en échec", len(sources) - failures, failures)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
