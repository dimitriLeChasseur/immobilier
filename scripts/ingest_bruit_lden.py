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
    uv run scripts/ingest_bruit_lden.py --metropole angers
    uv run scripts/ingest_bruit_lden.py --source ddt49-route

Exemple de crontab (le 2 de chaque mois à 4 h) :

    0 4 2 * * cd /opt/project-immobilier && uv run scripts/ingest_bruit_lden.py >> /var/log/immo-bruit.log 2>&1

Pour chaque source de infra/bruit/sources.json :
  1. lecture du flux WFS (GetFeature limité à l'emprise de la métropole) ou, à défaut,
     d'un fichier Shapefile zippé / GeoJSON téléchargé ;
  2. reprojection vers EPSG:4326 (les flux sont publiés en Lambert 93, EPSG:2154) ;
  3. upsert par lots dans immo.geo_bruit_lden, puis purge des zones disparues de la source.

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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import requests
from pyogrio.errors import DataSourceError
from pyproj import Transformer
from shapely import make_valid
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry
from sqlalchemy import Engine, create_engine, text

logger = logging.getLogger("ingest_bruit_lden")

ROOT = Path(__file__).resolve().parent.parent
SOURCES_FILE = ROOT / "infra" / "bruit" / "sources.json"
USER_AGENT = "AuditImmobilier/0.1 (ingestion bruit)"
HTTP_TIMEOUT_S = 300
BATCH_SIZE = 200
WFS_PAGE_SIZE = 500
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


class EmptyResponseError(ValueError):
    """Le service a répondu 200 sans contenu (requête trop lourde pour lui)."""


@dataclass(frozen=True)
class Source:
    id: str
    kind: str
    url: str
    bbox: tuple[float, float, float, float]
    layer: str | None = None


def load_sources(metropole: str | None, source_id: str | None) -> list[Source]:
    config = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
    sources = []
    for entry in config["sources"]:
        if metropole and entry["metropole"] != metropole:
            continue
        if source_id and entry["id"] != source_id:
            continue
        # Une source désactivée n'est traitée que si elle est demandée nommément.
        if not entry.get("actif", True) and entry["id"] != source_id:
            continue
        bbox = tuple(config["metropoles"][entry["metropole"]]["bbox"])
        sources.append(
            Source(entry["id"], entry["type"], entry["url"], bbox, entry.get("couche"))  # type: ignore[arg-type]
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
    capabilities = http_get(url, {"SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetCapabilities"})
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


def feature_count(url: str, layer: str) -> int | None:
    """Nombre d'entités de la couche, tel qu'annoncé par le service."""
    content = http_get(
        url,
        {"SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature", "TYPENAMES": layer, "RESULTTYPE": "hits"},
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


def fetch_tolerant_page(source: Source, params: dict[str, str], total: int | None) -> bytes | None:
    """Contenu de la page, ou None si la dernière page de la couche reste vide.

    Observé sur de très grosses couches : on garde alors le reste plutôt que de tout
    abandonner, en le signalant. Une page vide ailleurs reste une erreur.
    """
    start = int(params["STARTINDEX"])
    try:
        return fetch_page(source.url, params)
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


def wfs_pages(source: Source, layer: str, bbox_filter: str | None) -> list[gpd.GeoDataFrame]:
    # Sans filtre spatial, on connaît le total : une dernière page vide peut être tolérée.
    total = None if bbox_filter else feature_count(source.url, layer)
    pages: list[gpd.GeoDataFrame] = []
    while True:
        params = page_params(layer, len(pages) * WFS_PAGE_SIZE, bbox_filter)
        content = fetch_tolerant_page(source, params, total)
        if content is None or b"<wfs:member>" not in content:
            if content is not None and b"ExceptionReport" in content[:2000]:
                raise ValueError(f"le service WFS a refusé la requête : {content[:300]!r}")
            return pages
        page = gpd.read_file(io.BytesIO(content))
        pages.append(page.set_crs(LAMBERT93) if page.crs is None else page)
        if len(page) < WFS_PAGE_SIZE:
            return pages


def read_wfs(source: Source) -> gpd.GeoDataFrame:
    """Lit la couche par pages : les gros départements font échouer une requête unique."""
    layer = source.layer or wfs_layer(source.url)
    to_lambert = Transformer.from_crs(WGS84, LAMBERT93, always_xy=True)
    west, south, east, north = source.bbox
    xmin, ymin = to_lambert.transform(west, south)
    xmax, ymax = to_lambert.transform(east, north)
    bbox_filter = f"{xmin:.0f},{ymin:.0f},{xmax:.0f},{ymax:.0f},urn:ogc:def:crs:EPSG::{LAMBERT93}"
    try:
        pages = wfs_pages(source, layer, bbox_filter)
    except EmptyResponseError:
        # Certains services échouent sur le filtre spatial : on lit alors toute la couche,
        # le découpage à l'emprise de la métropole étant refait après reprojection.
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
    valid = geometry if geometry.is_valid else make_valid(geometry)
    polygons = [part for part in getattr(valid, "geoms", [valid]) if isinstance(part, Polygon)]
    return MultiPolygon(polygons) if polygons else None


def attribute(row: Any, name: str) -> str | None:
    """Valeur d'un attribut sans tenir compte de la casse (Shapefile : noms tronqués en majuscules)."""
    for key in (name, name.lower()):
        value = row.get(key)
        if value is not None and str(value) not in {"", "nan", "None", "NaT"}:
            return str(value).strip()
    return None


def to_row(row: Any, source: Source, suffix: str) -> dict[str, Any] | None:
    """Ligne prête à insérer ; None si l'entité n'est pas une zone Lden exploitable."""
    if (attribute(row, "INDICETYPE") or "LD").upper() != "LD":
        return None
    geometry = to_multipolygon(row.geometry)
    level = re.search(r"\d{2,3}", attribute(row, "LEGENDE") or "")
    infrastructure = INFRASTRUCTURES.get((attribute(row, "TYPESOURCE") or "")[:1].upper())
    if geometry is None or level is None or infrastructure is None:
        return None
    if int(level.group()) not in DB_RANGE:
        return None
    year = attribute(row, "ANNEE")
    return {
        "id_zone": f"{source.id}:{attribute(row, 'IDZONBRUIT') or 'zone'}:{suffix}",
        "source_id": source.id,
        "code_dept": (attribute(row, "CODEDEPT") or "")[-3:].lstrip("0") or "?",
        "infrastructure": infrastructure,
        "code_infra": attribute(row, "CODINFRA"),
        "annee": int(year) if year and year.isdigit() else None,
        "db_min": int(level.group()),
        "wkb": geometry.wkb,
    }


def to_rows(frame: gpd.GeoDataFrame, source: Source) -> list[dict[str, Any]]:
    """Reprojette, découpe à l'emprise de la métropole et ne garde que les zones exploitables."""
    west, south, east, north = source.bbox
    clipped = frame.to_crs(WGS84).cx[west:east, south:north]
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
        connection.execute(PURGE, {"source_id": source.id, "kept": [row["id_zone"] for row in rows]})


def ingest(engine: Engine, source: Source) -> int:
    frame = read_wfs(source) if source.kind == "wfs" else read_file(source)
    rows = to_rows(frame, source)
    if not rows:
        # Une source vide est plus probablement une panne qu'une disparition du bruit :
        # on conserve les données déjà chargées.
        raise ValueError(f"aucune zone exploitable sur {len(frame)} entités lues")
    store(engine, source, rows)
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--metropole", help="ne traiter que cette métropole (clé de sources.json)")
    parser.add_argument("--source", help="ne traiter que cette source (id de sources.json)")
    arguments = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    sources = load_sources(arguments.metropole, arguments.source)
    if not sources:
        logger.error("Aucune source ne correspond à la sélection")
        return 2
    engine = create_engine(database_url())
    failures = 0
    for source in sources:
        try:
            count = ingest(engine, source)
        # OSError couvre les erreurs réseau de requests (RequestException en dérive).
        except (DataSourceError, ValueError, OSError) as exc:
            logger.exception("%s : échec (%s)", source.id, type(exc).__name__)
            failures += 1
            continue
        logger.info("%s : %d zones de bruit chargées", source.id, count)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
