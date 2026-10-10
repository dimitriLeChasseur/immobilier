"""Référentiels communaux et scolaires : SSMSI, DGFiP, IPS."""

import csv
import io
import json
import logging
import zipfile
from collections.abc import Iterator
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
from app.services.street import normalize_street_name

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
    if total and options.departements is None:
        # Une commune sortie de la nouvelle édition ne garde pas son loyer de l'ancienne.
        removed = await repository.delete_stale_rents(options.rent_year)
        if removed:
            logger.info("loyers : %d lignes d'un millésime antérieur retirées", removed)
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


# Carte des loyers : un fichier par type de bien (liens stables de data.gouv), en latin-1.
_RENT_URL = "https://www.data.gouv.fr/api/1/datasets/r/{}"


def parse_rent_row(row: dict[str, str], kind: str, year: int) -> Row | None:
    code, rent = row.get("INSEE_C", ""), to_number(row.get("loypredm2"))
    if rent is None or rent <= 0 or not is_insee_code(code):
        return None
    low, high = to_number(row.get("lwr.IPm2")), to_number(row.get("upr.IPm2"))
    return (
        code,
        kind,
        rent,
        low,
        high,
        to_integer(row.get("nbobs_com")),
        row.get("TYPPRED") or None,
        year,
    )


async def ingest_rents(
    downloader: Downloader, repository: IngestionRepository, options: IngestionOptions
) -> int:
    if not options.rent_resources or not options.rent_year:
        raise ValueError("fichiers ou millésime de la carte des loyers absents de la configuration")
    total = 0
    for kind, resource in options.rent_resources.items():
        content = await downloader.content(_RENT_URL.format(resource))
        rows = [
            parsed
            for row in read_csv(content.decode("latin-1"))
            if (parsed := parse_rent_row(row, kind, options.rent_year)) is not None
            and options.accepts(parsed[0])
        ]
        for batch in batched(rows, _BATCH_SIZE):
            await repository.upsert_rents(batch)
        total += len(rows)
    if total and options.departements is None:
        # Une commune sortie de la nouvelle édition ne garde pas son loyer de l'ancienne.
        removed = await repository.delete_stale_rents(options.rent_year)
        if removed:
            logger.info("loyers : %d lignes d'un millésime antérieur retirées", removed)
    return total


# Zonage TLV : la dernière colonne « Zonage TLV … » est la liste en vigueur.
_TENSE_ZONE_COLUMN = "Zonage TLV"
_TENSE_ZONE_CATEGORIES = {"1": "tendue", "2": "touristique", "3": "non_tendue"}


def parse_tense_zone_row(row: dict[str, str]) -> Row | None:
    code = next((value for column, value in row.items() if column.startswith("CODGEO")), "")
    columns = [column for column in row if column.startswith(_TENSE_ZONE_COLUMN)]
    if not columns or not is_insee_code(code):
        return None
    # Valeurs « 1. Zone tendue », « 2. Zone touristique et tendue », « 3. Non tendue ».
    category = _TENSE_ZONE_CATEGORIES.get((row.get(columns[-1]) or "").strip()[:1])
    if category is None:
        return None
    return (code, category, columns[-1].removeprefix(_TENSE_ZONE_COLUMN).strip())


async def ingest_tense_zones(
    downloader: Downloader, repository: IngestionRepository, options: IngestionOptions
) -> int:
    if not options.tense_zone_resource:
        raise ValueError("fichier du zonage des zones tendues absent de la configuration")
    text = await downloader.text(_RENT_URL.format(options.tense_zone_resource))
    rows = [
        parsed
        for row in read_csv(text.removeprefix("\ufeff"))
        if (parsed := parse_tense_zone_row(row)) is not None and options.accepts(parsed[0])
    ]
    for batch in batched(rows, _BATCH_SIZE):
        await repository.upsert_tense_zones(batch)
    return len(rows)


_SCHOOL_MAP_URL = (
    "https://data.education.gouv.fr/api/explore/v2.1/catalog/datasets/"
    "fr-en-carte-scolaire-colleges-publics/exports/csv"
)


def parse_school_sector_row(row: dict[str, str]) -> Row | None:
    code, uai = row.get("code_insee", ""), (row.get("code_rne") or "").strip().upper()
    if not uai or not is_insee_code(code):
        return None
    if row.get("secteur_unique") == "O":
        return (code, "", None, None, None, uai, True)
    street = normalize_street_name(row.get("type_et_libelle"))
    if not street:
        # Secteur décrit par un lieu-dit seul : inexploitable à partir d'une adresse.
        return None
    return (
        code,
        street,
        to_integer(row.get("n_de_voie_debut")),
        to_integer(row.get("n_de_voie_fin")),
        (row.get("parite") or "").strip().upper() or None,
        uai,
        False,
    )


async def ingest_school_sectors(
    downloader: Downloader, repository: IngestionRepository, options: IngestionOptions
) -> int:
    text = await downloader.text(_SCHOOL_MAP_URL, params={"delimiter": ";"})
    rows = [
        parsed
        for row in read_csv(text.removeprefix("\ufeff"))
        if (parsed := parse_school_sector_row(row)) is not None and options.accepts(parsed[0])
    ]
    if rows:
        await repository.replace_school_sectors(rows, everything=options.departements is None)
    return len(rows)


# INSEE Filosofi — revenus disponibles par IRIS (« Revenus, pauvreté et niveau de vie »).
# Diffusé pour les IRIS des communes d'au moins 5 000 habitants environ.
_IRIS_INCOME_URL = (
    "https://www.insee.fr/fr/statistiques/fichier/8229323/BASE_TD_FILO_IRIS_2021_DISP_CSV.zip"
)
_IRIS_INCOME_YEAR = 2021
_INCOME_SUFFIX = f"{_IRIS_INCOME_YEAR % 100}"

# INSEE Filosofi — mêmes revenus par commune et arrondissement municipal. L'archive sépare
# la distribution des niveaux de vie et les taux de pauvreté en deux fichiers.
_COMMUNE_INCOME_URL = (
    "https://www.insee.fr/fr/statistiques/fichier/7756855/"
    "indic-struct-distrib-revenu-2021-COMMUNES_csv.zip"
)
_COMMUNE_INCOME_YEAR = 2021
_COMMUNE_INCOME_FILE = "FILO2021_DISP_COM.csv"
_COMMUNE_POVERTY_FILE = "FILO2021_DISP_PAUVRES_COM.csv"
_COMMUNE_INCOME_COLUMNS = ("Q221", "Q121", "Q321")
_COMMUNE_POVERTY_COLUMN = "TP6021"

# INSEE — recensement, base communale « Évolution et structure de la population ».
_POPULATION_URL = (
    "https://www.insee.fr/fr/statistiques/fichier/8581696/base-cc-evol-struct-pop-2022_csv.zip"
)
_POPULATION_YEAR = 2022
_POPULATION_COLUMNS = ("P22_POP", "P16_POP", "P11_POP")

# ANCT — périmètres des quartiers prioritaires 2024, hexagone et outre-mer en WGS84.
_QPV_URL = "https://www.data.gouv.fr/api/1/datasets/r/942d4ee8-8142-4556-8ea1-335537ce1119"
_QPV_FILE_SUFFIX = "wgs84.geojson"
_QPV_GEOMETRIES = frozenset({"Polygon", "MultiPolygon"})
_QPV_MINIMUM = 1000


def _data_file(archive: zipfile.ZipFile) -> str:
    """Fichier de données d'une archive INSEE, livrée avec un fichier de métadonnées."""
    return next(name for name in archive.namelist() if not name.lower().startswith("meta"))


def parse_iris_income_row(row: dict[str, str]) -> Row | None:
    """Revenus d'un IRIS ; « ns », « nd » et « s » (secret statistique) deviennent None."""
    code_iris = row.get("IRIS", "").strip()
    if len(code_iris) != _IRIS_CODE_LENGTH:
        return None

    def euros(column: str) -> int | None:
        value = to_number(row.get(f"DISP_{column}{_INCOME_SUFFIX}"))
        return round(value) if value is not None and value > 0 else None

    poverty = to_number(row.get(f"DISP_TP60{_INCOME_SUFFIX}"))
    median = euros("MED")
    if median is None and poverty is None:
        return None
    return (code_iris, _IRIS_INCOME_YEAR, median, euros("Q1"), euros("Q3"), poverty)


async def ingest_iris_income(
    downloader: Downloader, repository: IngestionRepository, options: IngestionOptions
) -> int:
    archive = zipfile.ZipFile(io.BytesIO(await downloader.content(_IRIS_INCOME_URL)))
    with archive.open(_data_file(archive)) as raw:
        reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8"), delimiter=";")
        rows = [
            parsed
            for row in reader
            # Les cinq premiers caractères d'un code IRIS sont le code de sa commune.
            if (parsed := parse_iris_income_row(row)) is not None
            and options.accepts(str(parsed[0])[:5])
        ]
    for batch in batched(rows, _BATCH_SIZE):
        await repository.upsert_iris_income(batch)
    return len(rows)


def _columns(
    archive: zipfile.ZipFile, name: str, columns: tuple[str, ...]
) -> Iterator[tuple[str, list[str]]]:
    """Code de la commune et colonnes voulues d'un fichier INSEE, lues par rang."""
    with archive.open(name) as raw:
        reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8"), delimiter=";")
        header = next(reader)
        code_at = header.index("CODGEO")
        wanted = [header.index(column) for column in columns]
        for line in reader:
            yield line[code_at], [line[at] for at in wanted]


def parse_commune_income_row(code: str, incomes: list[str], poverty: str | None) -> Row | None:
    """Revenus d'une commune ; « s » (secret statistique) et « nd » deviennent None."""
    if not is_insee_code(code):
        return None
    median, first, third = (
        round(value) if (value := to_number(text)) is not None and value > 0 else None
        for text in incomes
    )
    rate = to_number(poverty)
    if median is None and rate is None:
        return None
    return (code, _COMMUNE_INCOME_YEAR, median, first, third, rate)


async def ingest_commune_income(
    downloader: Downloader, repository: IngestionRepository, options: IngestionOptions
) -> int:
    archive = zipfile.ZipFile(io.BytesIO(await downloader.content(_COMMUNE_INCOME_URL)))
    poverty = {
        code: values[0]
        for code, values in _columns(archive, _COMMUNE_POVERTY_FILE, (_COMMUNE_POVERTY_COLUMN,))
    }
    rows = (
        parsed
        for code, incomes in _columns(archive, _COMMUNE_INCOME_FILE, _COMMUNE_INCOME_COLUMNS)
        if (parsed := parse_commune_income_row(code, incomes, poverty.get(code))) is not None
        and options.accepts(str(parsed[0]))
    )
    total = 0
    for batch in batched(rows, _BATCH_SIZE):
        await repository.upsert_commune_income(batch)
        total += len(batch)
    return total


def parse_population_row(code: str, counts: list[str]) -> Row | None:
    """Population d'une commune aux trois recensements ; None sans population courante."""
    current, six_years_ago, eleven_years_ago = (to_number(value) for value in counts)
    if not is_insee_code(code) or current is None or current < 0:
        return None

    def whole(value: float | None) -> int | None:
        return round(value) if value is not None and value >= 0 else None

    return (code, _POPULATION_YEAR, round(current), whole(six_years_ago), whole(eleven_years_ago))


async def ingest_population(
    downloader: Downloader, repository: IngestionRepository, options: IngestionOptions
) -> int:
    archive = zipfile.ZipFile(io.BytesIO(await downloader.content(_POPULATION_URL)))
    total = 0
    with archive.open(_data_file(archive)) as raw:
        # Trois colonnes utiles sur plus de trois cents : lecture par rang, sans dictionnaire.
        reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8"), delimiter=";")
        header = next(reader)
        code_at = header.index("CODGEO")
        counts_at = [header.index(column) for column in _POPULATION_COLUMNS]
        rows = (
            parsed
            for line in reader
            if (parsed := parse_population_row(line[code_at], [line[at] for at in counts_at]))
            is not None
            and options.accepts(str(parsed[0]))
        )
        for batch in batched(rows, _BATCH_SIZE):
            await repository.upsert_population(batch)
            total += len(batch)
    return total


def parse_priority_district(feature: dict[str, object]) -> Row | None:
    properties, geometry = feature.get("properties"), feature.get("geometry")
    if not isinstance(properties, dict) or not isinstance(geometry, dict):
        return None
    code, name = properties.get("code_qp"), properties.get("lib_qp")
    if not isinstance(code, str) or not isinstance(name, str) or not code.strip():
        return None
    if geometry.get("type") not in _QPV_GEOMETRIES:
        return None
    commune_code, commune = properties.get("insee_com"), properties.get("lib_com")
    return (
        code.strip(),
        name.strip(),
        commune_code if isinstance(commune_code, str) else None,
        commune if isinstance(commune, str) else None,
        json.dumps(geometry),
    )


async def ingest_priority_districts(
    downloader: Downloader, repository: IngestionRepository, options: IngestionOptions
) -> int:
    """Périmètres des quartiers prioritaires : toujours la France entière, le fichier est petit."""
    archive = zipfile.ZipFile(io.BytesIO(await downloader.content(_QPV_URL)))
    name = next(name for name in archive.namelist() if name.lower().endswith(_QPV_FILE_SUFFIX))
    collection = json.loads(archive.read(name))
    features = collection.get("features") if isinstance(collection, dict) else None
    if not isinstance(features, list):
        raise ValueError("fichier des quartiers prioritaires illisible")
    rows = [
        parsed
        for feature in features
        if isinstance(feature, dict) and (parsed := parse_priority_district(feature)) is not None
    ]
    # Un fichier presque vide signale une édition cassée : on garde les périmètres en place.
    if len(rows) < _QPV_MINIMUM:
        raise ValueError(f"seulement {len(rows)} quartiers prioritaires lus")
    await repository.replace_priority_districts(rows)
    return len(rows)
