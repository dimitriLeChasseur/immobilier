"""Référentiels communaux et scolaires : SSMSI, DGFiP, IPS."""

import csv
import io
import logging
import zipfile
from datetime import date

from app.ingestion.common import (
    Downloader,
    IngestionOptions,
    batched,
    is_insee_code,
    read_csv,
    to_date,
    to_integer,
    to_number,
)
from app.repositories.ingestion import IngestionRepository, Row

logger = logging.getLogger(__name__)

_BATCH_SIZE = 5000

# SSMSI — base communale de la délinquance enregistrée (data.gouv, lien stable).
_SSMSI_URL = "https://www.data.gouv.fr/api/1/datasets/r/44ef4323-1097-48d5-8719-3c544b55d294"

# DGFiP — taux votés de fiscalité directe locale, issus du REI (data.economie.gouv.fr).
_DGFIP_URL = (
    "https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets/"
    "fiscalite-locale-des-particuliers/exports/csv"
)
_DGFIP_FIELDS = "exercice,insee_com,libcom,e12vote,e32vote,taux_global_tfb,taux_plein_teom"

# Éducation nationale — IPS par type d'établissement + annuaire géolocalisé.
_EDUCATION_URL = "https://data.education.gouv.fr/api/explore/v2.1/catalog/datasets/{}/exports/csv"
_GEOLOC_DATASET = "fr-en-adresse-et-geolocalisation-etablissements-premier-et-second-degre"
# type -> (jeu de données, colonne IPS, colonne écart-type ou None)
_IPS_DATASETS: dict[str, tuple[str, str, str | None]] = {
    "ecole": ("fr-en-ips-ecoles-ap2022", "ips", None),
    "college": ("fr-en-ips-colleges-ap2023", "ips", "ecart_type_de_l_ips"),
    "lycee": ("fr-en-ips-lycees-ap2023", "ips_etab", "ecart_type_etablissement"),
}


def _code_column(header: dict[str, str]) -> str:
    """La colonne commune est millésimée (CODGEO_2025, CODGEO_2026...)."""
    for name in header:
        if name.upper().startswith("CODGEO"):
            return name
    raise ValueError("colonne CODGEO introuvable dans le fichier SSMSI")


def parse_crime_row(row: dict[str, str], code_column: str, min_year: int) -> Row | None:
    code, year = row[code_column], to_integer(row.get("annee"))
    indicator = row.get("indicateur", "").strip()
    if year is None or year < min_year or not indicator or not is_insee_code(code):
        return None
    return (
        code,
        indicator,
        year,
        row.get("unite_de_compte", "").strip(),
        row.get("est_diffuse") == "diff",
        to_integer(row.get("nombre")),
        to_number(row.get("taux_pour_mille")),
        to_integer(row.get("insee_pop")),
    )


async def ingest_crime(
    downloader: Downloader, repository: IngestionRepository, options: IngestionOptions
) -> int:
    min_year = date.today().year - options.crime_years + 1
    code_column: str | None = None
    batch: list[Row] = []
    total = 0
    async for row in downloader.csv_rows(_SSMSI_URL):
        if code_column is None:
            code_column = _code_column(row)
        parsed = parse_crime_row(row, code_column, min_year)
        if parsed is None or not options.accepts(parsed[0]):
            continue
        batch.append(parsed)
        if len(batch) >= _BATCH_SIZE:
            await repository.upsert_crime(batch)
            total += len(batch)
            batch = []
            if total % 100_000 == 0:
                logger.info("SSMSI : %d lignes chargées", total)
    await repository.upsert_crime(batch)
    return total + len(batch)


def parse_property_tax_row(row: dict[str, str]) -> Row | None:
    code, year = row.get("insee_com", ""), to_integer(row.get("exercice"))
    commune_rate, total_rate = to_number(row.get("e12vote")), to_number(row.get("taux_global_tfb"))
    if year is None or commune_rate is None or total_rate is None or not is_insee_code(code):
        return None
    return (
        code,
        year,
        row.get("libcom", "").strip() or code,
        commune_rate,
        to_number(row.get("e32vote")) or 0.0,
        total_rate,
        to_number(row.get("taux_plein_teom")),
    )


async def ingest_property_tax(
    downloader: Downloader, repository: IngestionRepository, options: IngestionOptions
) -> int:
    text = await downloader.text(_DGFIP_URL, {"select": _DGFIP_FIELDS, "delimiter": ";"})
    rows = [
        parsed
        for row in read_csv(text)
        if (parsed := parse_property_tax_row(row)) is not None and options.accepts(parsed[0])
    ]
    for batch in batched(rows, _BATCH_SIZE):
        await repository.upsert_property_tax(batch)
    return len(rows)


def parse_school_row(
    row: dict[str, str],
    kind: str,
    ips_column: str,
    deviation_column: str | None,
    coordinates: dict[str, tuple[float, float]],
) -> Row | None:
    uai, code = row.get("uai", "").strip().upper(), row.get("code_insee_de_la_commune", "")
    year = to_integer(row.get("rentree_scolaire", "")[:4])
    score = to_number(row.get(ips_column))
    position = coordinates.get(uai)
    if year is None or score is None or position is None or not is_insee_code(code):
        return None
    lat, lon = position
    return (
        uai,
        year,
        row.get("nom_de_l_etablissement", "").strip() or uai,
        kind,
        "public" if row.get("secteur", "").strip().lower() == "public" else "prive",
        code,
        score,
        to_number(row.get(deviation_column)) if deviation_column else None,
        lon,
        lat,
    )


async def _school_coordinates(downloader: Downloader) -> dict[str, tuple[float, float]]:
    text = await downloader.text(
        _EDUCATION_URL.format(_GEOLOC_DATASET),
        {"select": "numero_uai,latitude,longitude", "delimiter": ";"},
    )
    coordinates: dict[str, tuple[float, float]] = {}
    for row in read_csv(text):
        lat, lon = to_number(row.get("latitude")), to_number(row.get("longitude"))
        if lat is not None and lon is not None:
            coordinates[row["numero_uai"].strip().upper()] = (lat, lon)
    return coordinates


async def ingest_schools(
    downloader: Downloader, repository: IngestionRepository, options: IngestionOptions
) -> int:
    coordinates = await _school_coordinates(downloader)
    logger.info("IPS : %d établissements géolocalisés dans l'annuaire", len(coordinates))
    total = 0
    for kind, (dataset, ips_column, deviation_column) in _IPS_DATASETS.items():
        text = await downloader.text(_EDUCATION_URL.format(dataset), {"delimiter": ";"})
        source_rows = read_csv(text)
        rows = [
            parsed
            for row in source_rows
            if (parsed := parse_school_row(row, kind, ips_column, deviation_column, coordinates))
            is not None
            and options.accepts(parsed[5])
        ]
        for batch in batched(rows, _BATCH_SIZE):
            await repository.upsert_schools(batch)
        logger.info("IPS %s : %d lignes chargées sur %d lues", kind, len(rows), len(source_rows))
        total += len(rows)
    return total


# INSEE — recensement de la population, base infracommunale « Logement » (un IRIS par ligne).
_IRIS_HOUSING_URL = (
    "https://www.insee.fr/fr/statistiques/fichier/8647012/base-ic-logement-2022_csv.zip"
)
_IRIS_HOUSING_YEAR = 2022
_IRIS_PREFIX = f"P{_IRIS_HOUSING_YEAR % 100}"
_IRIS_CODE_LENGTH = 9

# ARCEP — « Ma connexion internet », éligibilité des locaux par technologie et par commune.
_ARCEP_URL = (
    "https://data.arcep.fr/fixe/maconnexioninternet/statistiques/last/commune/commune_techno.csv"
)


def parse_iris_housing_row(row: dict[str, str]) -> Row | None:
    code_iris, code_insee = row.get("IRIS", "").strip(), row.get("COM", "").strip()
    counts = [
        to_integer(row.get(f"{_IRIS_PREFIX}_{column}"))
        for column in ("LOG", "RP", "RSECOCC", "LOGVAC", "RP_PROP", "RP_LOC", "RP_LOCHLMV")
    ]
    if len(code_iris) != _IRIS_CODE_LENGTH or not is_insee_code(code_insee) or None in counts:
        return None
    return (code_iris, _IRIS_HOUSING_YEAR, code_insee, *(max(count or 0, 0) for count in counts))


async def ingest_iris_housing(
    downloader: Downloader, repository: IngestionRepository, options: IngestionOptions
) -> int:
    archive = zipfile.ZipFile(io.BytesIO(await downloader.content(_IRIS_HOUSING_URL)))
    data_file = next(name for name in archive.namelist() if not name.lower().startswith("meta"))
    with archive.open(data_file) as raw:
        reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8"), delimiter=";")
        rows = (
            parsed
            for row in reader
            if (parsed := parse_iris_housing_row(row)) is not None and options.accepts(parsed[2])
        )
        total = 0
        for batch in batched(rows, _BATCH_SIZE):
            await repository.upsert_iris_housing(batch)
            total += len(batch)
    return total


def parse_connectivity_row(row: dict[str, str]) -> Row | None:
    code, premises = row.get("code_insee", "").strip(), to_integer(row.get("nbr"))
    measured_on = to_date(row.get("date"))
    if row.get("type") != "all" or not premises or measured_on is None or not is_insee_code(code):
        return None
    return (
        code,
        measured_on,
        premises,
        to_integer(row.get("elig_ftth")) or 0,
        to_integer(row.get("elig_coax")) or 0,
        to_integer(row.get("elig_4gf")) or 0,
    )


async def ingest_connectivity(
    downloader: Downloader, repository: IngestionRepository, options: IngestionOptions
) -> int:
    rows = [
        parsed
        for row in read_csv(await downloader.text(_ARCEP_URL))
        if (parsed := parse_connectivity_row(row)) is not None and options.accepts(parsed[0])
    ]
    for batch in batched(rows, _BATCH_SIZE):
        await repository.upsert_connectivity(batch)
    return len(rows)
