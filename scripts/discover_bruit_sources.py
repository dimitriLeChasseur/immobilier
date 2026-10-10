#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["requests>=2.32"]
# ///
"""Recense les flux des cartes de bruit stratégiques et écrit infra/bruit/sources.json.

Il n'existe pas de flux national : chaque direction départementale des territoires publie
ses cartes sur Géo-IDE, dont data.gouv.fr moissonne une partie des fiches. Ce script :

  1. cherche ces fiches dans le catalogue Géo-IDE et sur data.gouv.fr, et relève l'adresse
     de leur service WFS ;
  2. demande à chaque service la liste de ses couches ;
  3. garde les couches « type A, indice Lden » (zones exposées, sur 24 h), reconnues à leur
     nom normalisé (N_BRUIT_ZBR_…_A_LD_…_<département>), en écartant les éditions
     antérieures quand le département publie une couche courante.

    uv run scripts/discover_bruit_sources.py

À relancer quand de nouvelles cartes sont publiées, puis `uv run scripts/ingest_bruit_lden.py`.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

logger = logging.getLogger("discover_bruit_sources")

SOURCES_FILE = Path(__file__).resolve().parent.parent / "infra" / "bruit" / "sources.json"
USER_AGENT = "AuditImmobilier/0.1 (ingestion bruit)"
CATALOGUE_URL = "https://www.data.gouv.fr/api/1/datasets/"
QUERIES = (
    "carte de bruit stratégique",
    "zones de bruit",
    "bruit Lden",
    "CBS bruit",
    "bruit infrastructures",
    "bruit routier",
    "bruit ferroviaire",
    "bruit 4e échéance",
)
MAX_PAGES = 12
# Catalogue du ministère (GeoNetwork) : recherche plein texte, paginée par rang.
GEOIDE_URL = "https://catalogue.geo-ide.developpement-durable.gouv.fr/catalogue/srv/fre/q"
GEOIDE_PAGE_SIZE = 100
GEOIDE_MAX_RECORDS = 6000
WORKERS = 8

WFS_URL = re.compile(r"https?://ogc\.geo-ide[^\s\"'|]*?\.internet\.map")
RECORD_COUNT = re.compile(r'"@count":\s*"(\d+)"')
LAYER_NAME = re.compile(rb"<FeatureType>.*?<Name>([^<]+)</Name>", re.DOTALL)
# Zones de bruit de type A en Lden ; le type C (dépassement de seuil) et l'indice de nuit
# (LN) ne sont pas retenus.
TYPE_A_LDEN = re.compile(r"N_BRUIT_ZBR.*_A_(LD|LDEN|LDN)(_|$)", re.IGNORECASE)
# Code du département en fin de nom, éventuellement suivi d'un millésime (« _069_2017 »).
DEPARTEMENT = re.compile(r"_(\d{3}|0?2[AB]|\d{2})(_[A-Z0-9]+)?$", re.IGNORECASE)

COMMENT = (
    "Flux des cartes de bruit stratégiques (type A, indice Lden) publiés sur Géo-IDE par les "
    "directions départementales. Fichier écrit par scripts/discover_bruit_sources.py : le "
    'relancer plutôt que de l\'éditer. Une source peut être désactivée à la main ("actif": '
    "false) ; elle est alors conservée telle quelle par le recensement."
)


def get(url: str, params: dict[str, str | int] | None = None, timeout: int = 60) -> bytes:
    response = requests.get(url, params=params, timeout=timeout, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return response.content


def wfs_urls() -> set[str]:
    """Adresses des services WFS cités par les fiches « bruit » de data.gouv.fr."""
    urls: set[str] = set()
    for query in QUERIES:
        for page in range(1, MAX_PAGES + 1):
            payload = json.loads(get(CATALOGUE_URL, {"q": query, "page_size": 100, "page": page}))
            for dataset in payload["data"]:
                for resource in dataset["resources"]:
                    urls.update(WFS_URL.findall(resource.get("url") or ""))
            if not payload.get("next_page"):
                break
        logger.info("« %s » : %d services relevés", query, len(urls))
    return urls


def geoide_wfs_urls() -> set[str]:
    """Adresses des services WFS des fiches « bruit » du catalogue Géo-IDE."""
    urls: set[str] = set()
    total = GEOIDE_PAGE_SIZE
    for first in range(1, GEOIDE_MAX_RECORDS, GEOIDE_PAGE_SIZE):
        if first > total:
            break
        params: dict[str, str | int] = {
            "any": "bruit",
            "_content_type": "json",
            "fast": "index",
            "from": first,
            "to": first + GEOIDE_PAGE_SIZE - 1,
        }
        try:
            body = get(GEOIDE_URL, params, timeout=120).decode("utf-8", "replace")
        except requests.RequestException as exc:
            logger.warning("Catalogue Géo-IDE illisible au rang %d (%s)", first, type(exc).__name__)
            continue
        count = RECORD_COUNT.search(body)
        total = int(count.group(1)) if count else total
        urls.update(WFS_URL.findall(body))
    logger.info("Catalogue Géo-IDE : %d services relevés", len(urls))
    return urls


def layers_of(url: str) -> tuple[str, list[str]]:
    try:
        capabilities = get(
            url, {"SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetCapabilities"}, timeout=45
        )
    except requests.RequestException as exc:
        logger.warning("Service illisible (%s) : %s", type(exc).__name__, url)
        return url, []
    return url, [name.decode() for name in LAYER_NAME.findall(capabilities)]


def departement_of(layer: str) -> tuple[str, bool] | None:
    """(code du département, vrai si le nom porte un millésime), None s'il est illisible."""
    match = DEPARTEMENT.search(layer)
    if match is None:
        return None
    code = match.group(1).upper()
    # « 049 » -> « 49 », « 02A » -> « 2A » ; les départements d'outre-mer gardent trois chiffres.
    code = code[1:] if len(code) == 3 and code.startswith("0") else code  # noqa: PLR2004
    return code, match.group(2) is not None


def candidates(urls: set[str]) -> list[dict[str, str | bool]]:
    """Une entrée par couche de type A en Lden, sans doublon entre services."""
    found: dict[str, dict[str, str | bool]] = {}
    with ThreadPoolExecutor(WORKERS) as pool:
        for url, layers in pool.map(layers_of, sorted(urls)):
            for layer in layers:
                located = departement_of(layer)
                if located is None or not TYPE_A_LDEN.search(layer):
                    continue
                short = layer.split(":", 1)[-1].lower()
                found.setdefault(
                    short,
                    {
                        "id": f"d{located[0].lower()}-{short.removeprefix('n_bruit_zbr_')}",
                        "departement": located[0],
                        "type": "wfs",
                        "url": url,
                        "couche": layer,
                        "millesime": located[1],
                    },
                )
    return list(found.values())


def current_editions(entries: list[dict[str, str | bool]]) -> list[dict[str, str | bool]]:
    """Écarte les couches millésimées d'un département qui publie une couche courante."""
    with_current = {entry["departement"] for entry in entries if not entry["millesime"]}
    kept = [
        {key: value for key, value in entry.items() if key != "millesime"}
        for entry in entries
        if not entry["millesime"] or entry["departement"] not in with_current
    ]
    return sorted(kept, key=lambda entry: (str(entry["departement"]), str(entry["id"])))


def keep_manual_settings(entries: list[dict[str, str | bool]]) -> None:
    """Reporte les désactivations faites à la main dans le fichier existant."""
    if not SOURCES_FILE.exists():
        return
    previous = {
        entry["id"]: entry
        for entry in json.loads(SOURCES_FILE.read_text(encoding="utf-8")).get("sources", [])
    }
    for entry in entries:
        old = previous.get(entry["id"], {})
        for key in ("actif", "note"):
            if key in old:
                entry[key] = old[key]


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    entries = current_editions(candidates(wfs_urls() | geoide_wfs_urls()))
    if not entries:
        logger.error("Aucune couche trouvée : le fichier existant est conservé")
        return 1
    keep_manual_settings(entries)
    SOURCES_FILE.write_text(
        json.dumps({"_commentaire": COMMENT, "sources": entries}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    departements = sorted({str(entry["departement"]) for entry in entries})
    logger.info(
        "%d couches dans %d départements : %s",
        len(entries),
        len(departements),
        ", ".join(departements),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
