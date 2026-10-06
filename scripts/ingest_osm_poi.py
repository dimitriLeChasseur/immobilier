#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "osmium>=4.0",
#   "requests>=2.32",
#   "psycopg[binary]>=3.2",
# ]
# ///
"""Ingestion des points d'intérêt OpenStreetMap (transports, commerces, santé, écoles, parcs).

Script autonome, indépendant du backend, prévu pour une tâche planifiée :

    uv run scripts/ingest_osm_poi.py                          # France entière (~5 Go téléchargés)
    uv run scripts/ingest_osm_poi.py --region pays-de-la-loire
    uv run scripts/ingest_osm_poi.py --fichier extrait.osm.pbf --source essai

Exemple de crontab (le 3 de chaque mois à 4 h) :

    0 4 3 * * cd /opt/project-immobilier && uv run scripts/ingest_osm_poi.py >> /var/log/immo-osm.log 2>&1

L'extrait Geofabrik (.osm.pbf) est lu en plusieurs passes filtrées, sans index des nœuds en
mémoire : seuls les objets retenus et les nœuds qui les dessinent sont conservés. Un chemin ou
une relation (parc, école) est enregistré par les sommets de son contour : il est « à portée »
dès que son bord l'est, comme avec Overpass.

Connexion : variable OSM_DATABASE_URL, sinon reconstruite depuis le fichier .env du projet
(rôle immo_app sur le port local de la base).

Données © les contributeurs d'OpenStreetMap, licence ODbL.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import tempfile
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import osmium
import psycopg
import requests

logger = logging.getLogger("ingest_osm_poi")

ROOT = Path(__file__).resolve().parent.parent
GEOFABRIK = "https://download.geofabrik.de/europe"
_CHUNK_BYTES = 1 << 20
_DOWNLOAD_TIMEOUT_S = 60
_DOWNLOAD_RETRIES = 20

# catégorie -> clé OSM -> valeurs retenues.
# À garder identique à _CATEGORIES de backend/app/services/providers/poi.py.
CATEGORIES: dict[str, dict[str, frozenset[str]]] = {
    "transports": {
        "railway": frozenset({"station", "tram_stop"}),
        "highway": frozenset({"bus_stop"}),
    },
    "commerces": {"shop": frozenset({"supermarket", "bakery", "convenience"})},
    "sante": {"amenity": frozenset({"pharmacy", "doctors"})},
    "education": {"amenity": frozenset({"school", "kindergarten"})},
    "espaces_verts": {"leisure": frozenset({"park"})},
}
KEYS = sorted({key for tags in CATEGORIES.values() for key in tags})

# (type OSM, identifiant, catégorie, type, nom, géométrie WKT)
Row = tuple[str, int, str, str, str | None, str]


@dataclass(slots=True)
class Shape:
    """Chemin ou relation retenu, en attente des coordonnées de ses nœuds."""

    osm_type: str
    osm_id: int
    category: str
    kind: str
    name: str | None
    node_ids: list[int]


def classify(tags: osmium.osm.TagList) -> tuple[str, str] | None:
    """(catégorie, type) d'un objet OSM, None s'il ne nous intéresse pas."""
    for category, keys in CATEGORIES.items():
        for key, values in keys.items():
            value = tags.get(key)
            if value in values:
                return category, value
    return None


def extract(path: str) -> Iterator[Row]:
    """Lit l'extrait et produit une ligne par point d'intérêt."""
    key_filter = osmium.filter.KeyFilter(*KEYS)

    # 1. Relations retenues (parcs ou écoles en plusieurs morceaux) et leurs chemins.
    relations: list[tuple[int, str, str, str | None, list[int]]] = []
    member_ways: set[int] = set()
    for relation in osmium.FileProcessor(path, osmium.osm.RELATION).with_filter(key_filter):
        kind = classify(relation.tags)
        if kind is None:
            continue
        way_ids = [member.ref for member in relation.members if member.type == "w"]
        if way_ids:
            relations.append((relation.id, kind[0], kind[1], relation.tags.get("name"), way_ids))
            member_ways.update(way_ids)
    logger.info("Relations retenues : %d", len(relations))

    # 2. Chemins retenus, et nœuds des chemins composant les relations.
    shapes: list[Shape] = []
    for way in osmium.FileProcessor(path, osmium.osm.WAY).with_filter(key_filter):
        kind = classify(way.tags)
        if kind is not None:
            node_ids = [node.ref for node in way.nodes]
            shapes.append(Shape("w", way.id, kind[0], kind[1], way.tags.get("name"), node_ids))
    way_nodes: dict[int, list[int]] = {}
    if member_ways:
        id_filter = osmium.filter.IdFilter(member_ways)
        for way in osmium.FileProcessor(path, osmium.osm.WAY).with_filter(id_filter):
            way_nodes[way.id] = [node.ref for node in way.nodes]
    for osm_id, category, kind_name, name, way_ids in relations:
        node_ids = [ref for way_id in way_ids for ref in way_nodes.get(way_id, ())]
        if node_ids:
            shapes.append(Shape("r", osm_id, category, kind_name, name, node_ids))
    logger.info("Chemins et relations à localiser : %d", len(shapes))

    # 3. Nœuds retenus : ce sont directement des points d'intérêt.
    count = 0
    for node in osmium.FileProcessor(path, osmium.osm.NODE).with_filter(key_filter):
        kind = classify(node.tags)
        if kind is not None and node.location.valid():
            count += 1
            wkt = f"POINT({node.lon:.7f} {node.lat:.7f})"
            yield ("n", node.id, kind[0], kind[1], node.tags.get("name"), wkt)
    logger.info("Nœuds retenus : %d", count)

    # 4. Coordonnées des nœuds dessinant les chemins et relations.
    needed = {ref for shape in shapes for ref in shape.node_ids}
    coordinates: dict[int, tuple[float, float]] = {}
    if needed:
        id_filter = osmium.filter.IdFilter(needed)
        for node in osmium.FileProcessor(path, osmium.osm.NODE).with_filter(id_filter):
            if node.location.valid():
                coordinates[node.id] = (node.lon, node.lat)
    for shape in shapes:
        # dict.fromkeys : un contour fermé répète son premier nœud.
        points = [coordinates[ref] for ref in dict.fromkeys(shape.node_ids) if ref in coordinates]
        if not points:
            continue
        vertices = ",".join(f"({lon:.7f} {lat:.7f})" for lon, lat in points)
        yield (
            shape.osm_type,
            shape.osm_id,
            shape.category,
            shape.kind,
            shape.name,
            f"MULTIPOINT({vertices})",
        )


def database_url() -> str:
    explicit = os.environ.get("OSM_DATABASE_URL")
    if explicit:
        return explicit
    env: dict[str, str] = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip().strip('"')
    password, port = env["IMMO_APP_DB_PASSWORD"], env.get("DB_HOST_PORT", "5433")
    return f"postgresql://immo_app:{password}@127.0.0.1:{port}/{env.get('POSTGRES_DB', 'postgres')}"


def download(url: str, target: Path) -> None:
    """Télécharge l'extrait ; une coupure reprend à l'octet atteint (requête Range)."""
    logger.info("Téléchargement de %s", url)
    # L'adresse « latest » redirige vers le fichier daté : on s'y tient pour toutes les reprises.
    head = requests.head(url, allow_redirects=True, timeout=_DOWNLOAD_TIMEOUT_S)
    head.raise_for_status()
    url, total = head.url, int(head.headers.get("Content-Length", 0))
    failures = 0
    while True:
        done = target.stat().st_size if target.exists() else 0
        if total and done >= total:
            break
        try:
            _download_from(url, target, done)
        except requests.RequestException as exc:
            failures += 1
            if failures > _DOWNLOAD_RETRIES:
                raise
            logger.warning("Coupure à %.0f Mo (%s) : reprise n° %d", done / 1e6, exc, failures)
            time.sleep(min(60, 5 * failures))
            continue
        if not total:
            break
    logger.info("Extrait téléchargé : %.0f Mo", target.stat().st_size / 1e6)


def _download_from(url: str, target: Path, offset: int) -> None:
    headers = {"Range": f"bytes={offset}-"} if offset else {}
    with requests.get(url, stream=True, timeout=_DOWNLOAD_TIMEOUT_S, headers=headers) as response:
        response.raise_for_status()
        # 200 au lieu de 206 : le serveur ignore la reprise et renvoie tout le fichier.
        mode = "ab" if offset and response.status_code == requests.codes.partial_content else "wb"
        with target.open(mode) as handle:
            for chunk in response.iter_content(_CHUNK_BYTES):
                handle.write(chunk)


def load(rows: Iterator[Row], source: str) -> tuple[int, int]:
    """Remplace les points de cette source en une transaction. Renvoie (écrits, purgés)."""
    with psycopg.connect(database_url(), options="-c search_path=immo,extensions") as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "CREATE TEMP TABLE poi_stage (osm_type text, osm_id bigint, categorie text,"
                " type text, nom text, wkt text)"
                " ON COMMIT DROP"
            )
            with cursor.copy("COPY poi_stage FROM STDIN") as copy:
                for row in rows:
                    copy.write_row(row)
            cursor.execute(
                "INSERT INTO geo_osm_poi (osm_type, osm_id, categorie, type, nom, source, geom)"
                " SELECT DISTINCT ON (osm_type, osm_id) osm_type, osm_id, categorie, type,"
                "        nullif(left(nom, 200), ''), %s, ST_GeomFromText(wkt, 4326)"
                " FROM poi_stage"
                " ON CONFLICT (osm_type, osm_id) DO UPDATE SET"
                "   categorie = EXCLUDED.categorie, type = EXCLUDED.type, nom = EXCLUDED.nom,"
                "   source = EXCLUDED.source, geom = EXCLUDED.geom, imported_at = now()",
                (source,),
            )
            written = cursor.rowcount
            # now() est l'heure de début de transaction : les lignes non réécrites sont
            # celles que l'extrait ne contient plus.
            cursor.execute(
                "DELETE FROM geo_osm_poi WHERE source = %s AND imported_at < now()", (source,)
            )
            purged = cursor.rowcount
        connection.commit()
    return written, purged


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--region", help="région Geofabrik (ex. pays-de-la-loire, ile-de-france)")
    parser.add_argument("--fichier", type=Path, help="extrait .osm.pbf déjà téléchargé")
    parser.add_argument("--source", help="étiquette des lignes (défaut : région ou « france »)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    source = args.source or args.region or "france"
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="osm-poi-") as workdir:
        path = args.fichier
        if path is None:
            path = Path(workdir) / "extrait.osm.pbf"
            name = f"france/{args.region}" if args.region else "france"
            try:
                download(f"{GEOFABRIK}/{name}-latest.osm.pbf", path)
            except requests.RequestException as exc:
                logger.error("Téléchargement impossible : %s", exc)
                return 1
        if not path.is_file():
            logger.error("Fichier introuvable : %s", path)
            return 1
        try:
            written, purged = load(extract(str(path)), source)
        except (psycopg.Error, RuntimeError) as exc:
            # Transaction annulée : les données précédentes restent en place.
            logger.error("Ingestion interrompue, base inchangée : %s", exc)
            return 1
    logger.info(
        "Source %s : %d points écrits, %d purgés, en %.0f s",
        source,
        written,
        purged,
        time.monotonic() - started,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
