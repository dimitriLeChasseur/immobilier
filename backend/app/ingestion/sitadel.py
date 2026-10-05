"""SITADEL : autorisations d'urbanisme récentes, géocodées en masse via la BAN.

Le fichier du SDES ne contient pas de coordonnées, seulement l'adresse du terrain.
Chaque département est téléchargé (filtré côté serveur), géocodé, puis chargé.
"""

import asyncio
import csv
import io
import logging
from dataclasses import dataclass
from datetime import date, timedelta

import aiohttp

from app.core.errors import RepositoryError
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

_DIDO_URL = "https://data.statistiques.developpement-durable.gouv.fr/dido/api/v1/datafiles/{}/csv"
# Les logements sont chargés en dernier : ils priment si un permis figure dans les deux fichiers.
_DATAFILES: tuple[tuple[str, str], ...] = (
    ("locaux", "f8f0700f-806c-40a7-83b1-f21cf507e7c4"),
    ("logement", "8b35affb-55fc-4c1f-915b-7750f974446a"),
)
_BAN_CSV_URL = "https://api-adresse.data.gouv.fr/search/csv/"
_GEOCODING_BATCH = 2000
_MIN_GEOCODING_SCORE = 0.5
_PRECISION_BY_RESULT_TYPE = {"housenumber": "numero", "street": "voie"}

_STATES = {2: "autorise", 4: "annule", 5: "commence", 6: "termine"}
_NATURES = {1: "construction neuve", 2: "travaux sur existant"}
_PERMIT_TYPES = {"PC", "PA", "DP", "PD"}
# Le fichier source contient des valeurs aberrantes (niveaux négatifs, 239 étages).
_MAX_LEVELS = 100
_CONCURRENT_DEPARTEMENTS = 3

METROPOLITAN_DEPARTEMENTS: tuple[str, ...] = tuple(
    code for number in range(1, 96) if (code := f"{number:02d}") != "20"
) + ("2A", "2B")
OVERSEAS_DEPARTEMENTS: tuple[str, ...] = ("971", "972", "973", "974", "976")
ALL_DEPARTEMENTS = METROPOLITAN_DEPARTEMENTS + OVERSEAS_DEPARTEMENTS


class IncompleteIngestionError(ValueError):
    """Certains départements n'ont pas pu être chargés ; les autres le sont."""


@dataclass(frozen=True, slots=True)
class Permit:
    """Autorisation en attente de géocodage."""

    values: Row
    street_address: str
    postcode: str
    citycode: str


def _bounded(value: int | None, maximum: int) -> int | None:
    return value if value is not None and 0 <= value <= maximum else None


def parse_permit_row(row: dict[str, str], destination: str) -> Permit | None:
    number, code = row.get("NUM_DAU", "").strip(), row.get("COMM", "").strip()
    kind = row.get("TYPE_DAU", "").strip()
    state = _STATES.get(to_integer(row.get("ETAT_DAU")) or 0)
    authorized_on = to_date(row.get("DATE_REELLE_AUTORISATION"))
    street = " ".join(
        part for key in ("ADR_NUM_TER", "ADR_LIBVOIE_TER") if (part := row.get(key, "").strip())
    )
    street = street or row.get("ADR_LIEUDIT_TER", "").strip()
    usable = number and state and authorized_on and street and kind in _PERMIT_TYPES
    if not usable or not is_insee_code(code):
        return None
    locality = row.get("ADR_LOCALITE_TER", "").strip()
    surface = (to_number(row.get("SURF_HAB_CREEE")) or 0.0) + (
        to_number(row.get("SURF_LOC_CREEE")) or 0.0
    )
    return Permit(
        values=(
            number,
            kind,
            state,
            authorized_on,
            to_date(row.get("DATE_REELLE_DOC")),
            to_date(row.get("DATE_REELLE_DAACT")),
            code,
            f"{street}, {locality}" if locality else street,
            _NATURES.get(to_integer(row.get("NATURE_PROJET_DECLAREE")) or 0),
            destination,
            _bounded(to_integer(row.get("NB_LGT_TOT_CREES")), 100_000),
            _bounded(to_integer(row.get("NB_NIV_MAX")), _MAX_LEVELS),
            max(surface, 0.0),
        ),
        street_address=street,
        postcode=row.get("ADR_CODPOST_TER", "").strip(),
        citycode=code,
    )


def geocoding_request(permits: list[Permit]) -> str:
    """CSV envoyé au géocodeur ; l'index de ligne sert d'identifiant de rapprochement."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["idx", "adresse", "postcode", "citycode"])
    for index, permit in enumerate(permits):
        writer.writerow([index, permit.street_address, permit.postcode, permit.citycode])
    return buffer.getvalue()


def merge_geocoding(permits: list[Permit], response_csv: str) -> list[Row]:
    """Lignes prêtes à charger : uniquement les permis localisés au numéro ou à la voie."""
    rows: list[Row] = []
    for result in read_csv(response_csv, delimiter=","):
        index = to_integer(result.get("idx"))
        precision = _PRECISION_BY_RESULT_TYPE.get(result.get("result_type", ""))
        lat, lon = to_number(result.get("latitude")), to_number(result.get("longitude"))
        score = to_number(result.get("result_score")) or 0.0
        located = precision and lat is not None and lon is not None
        if index is None or not located or score < _MIN_GEOCODING_SCORE:
            continue
        if 0 <= index < len(permits):
            rows.append((*permits[index].values, precision, lon, lat))
    return rows


def _geocoding_form(permits: list[Permit]) -> aiohttp.FormData:
    form = aiohttp.FormData()
    form.add_field(
        "data", geocoding_request(permits), filename="permis.csv", content_type="text/csv"
    )
    form.add_field("columns", "adresse")
    form.add_field("postcode", "postcode")
    form.add_field("citycode", "citycode")
    for column in ("latitude", "longitude", "result_score", "result_type"):
        form.add_field("result_columns", column)
    return form


async def _geocode(downloader: Downloader, permits: list[Permit]) -> list[Row]:
    response = await downloader.post_form(_BAN_CSV_URL, lambda: _geocoding_form(permits))
    return merge_geocoding(permits, response)


async def _ingest_departement(
    downloader: Downloader, repository: IngestionRepository, departement: str, since: date
) -> tuple[int, int]:
    read = loaded = 0
    for destination, datafile in _DATAFILES:
        text = await downloader.text(
            _DIDO_URL.format(datafile),
            {
                "withColumnName": "true",
                "withColumnDescription": "false",
                "withColumnUnit": "false",
                "DEP_CODE": f"eq:{departement}",
                "DATE_REELLE_AUTORISATION": f"gte:{since.isoformat()}",
            },
        )
        permits = [
            permit
            for row in read_csv(text)
            if (permit := parse_permit_row(row, destination)) is not None
        ]
        read += len(permits)
        for batch in batched(permits, _GEOCODING_BATCH):
            rows = await _geocode(downloader, batch)
            await repository.upsert_permits(rows)
            loaded += len(rows)
    return read, loaded


async def ingest_permits(
    downloader: Downloader, repository: IngestionRepository, options: IngestionOptions
) -> int:
    since = date.today() - timedelta(days=365 * options.permit_years)
    limiter = asyncio.Semaphore(_CONCURRENT_DEPARTEMENTS)
    failed: list[str] = []

    async def ingest_one(departement: str) -> int:
        async with limiter:
            try:
                read, loaded = await _ingest_departement(downloader, repository, departement, since)
            except (aiohttp.ClientError, TimeoutError, RepositoryError):
                # Un département en échec n'interrompt pas les autres : relancer le rattrape.
                logger.exception("SITADEL %s : échec, département ignoré", departement)
                failed.append(departement)
                return 0
        share = round(100 * loaded / read) if read else 0
        logger.info(
            "SITADEL %s : %d permis géocodés sur %d (%d %%)", departement, loaded, read, share
        )
        return loaded

    departements = sorted(options.departements or ALL_DEPARTEMENTS)
    totals = await asyncio.gather(*(ingest_one(departement) for departement in departements))
    await repository.purge_permits_before(since)
    if failed:
        raise IncompleteIngestionError(
            f"{sum(totals)} permis chargés, mais départements en échec à relancer : "
            f"--departements {','.join(sorted(failed))}"
        )
    return sum(totals)
