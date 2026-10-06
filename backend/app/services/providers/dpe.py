"""ADEME : diagnostics de performance énergétique des logements voisins."""

import math
from collections import Counter
from itertools import takewhile
from typing import Any

from app.core.errors import NoDataError
from app.core.http import HttpClient
from app.services.insights import energy_assessment
from app.services.providers.base import AuditContext, ProviderData, as_rows, to_float
from app.services.street import Street

_URL = "https://data.ademe.fr/data-fair/api/v1/datasets/dpe03existant/lines"
_RADIUS_M = 150
_SAMPLE_SIZE = 100
_NEAREST = 5
_FIELDS = "etiquette_dpe,etiquette_ges,date_etablissement_dpe"
_STREET_FIELDS = f"{_FIELDS},numero_voie_ban,annee_construction"
_STREET_SAMPLE_SIZE = 1000
_MAX_NUMBERS = 80


class DpeProvider:
    name = "dpe"

    def __init__(self, http: HttpClient) -> None:
        self._http = http

    async def fetch(self, ctx: AuditContext) -> ProviderData:
        if ctx.street is not None:
            along_street = await self._fetch_street(ctx.street)
            if along_street is not None:
                return along_street
            # Aucun diagnostic rattaché à la voie : analyse au rayon, comme pour une adresse.
        payload = await self._http.get_json(
            "ademe",
            _URL,
            params={
                "geo_distance": f"{ctx.lon},{ctx.lat},{_RADIUS_M}",
                "size": _SAMPLE_SIZE,
                "select": _FIELDS,
            },
        )
        rows = as_rows(payload, "results")
        if not rows:
            raise NoDataError
        # L'API renvoie les diagnostics du plus proche au plus lointain : l'échantillon
        # couvre donc un rayon réel souvent bien inférieur au rayon demandé.
        distances = [d for row in rows if (d := to_float(row.get("_geo_distance"))) is not None]
        data = _distribution(rows, payload.get("total"))
        data["perimetre"] = "rayon"
        data["rayon_m"] = _RADIUS_M
        data["rayon_effectif_m"] = math.ceil(max(distances)) if distances else None
        data["plus_proches"] = [_nearest(row) for row in rows[:_NEAREST]]
        return ProviderData(data=data)

    async def _fetch_street(self, street: Street) -> ProviderData | None:
        """Diagnostics rattachés aux numéros de la voie (identifiant BAN du logement)."""
        payload = await self._http.get_json(
            "ademe",
            _URL,
            params={
                "identifiant_ban_starts": f"{street.id}_",
                "size": _STREET_SAMPLE_SIZE,
                "select": _STREET_FIELDS,
                "sort": "-date_etablissement_dpe",
            },
        )
        rows = as_rows(payload, "results")
        if not rows:
            return None
        data = _distribution(rows, payload.get("total"))
        data["perimetre"] = "rue"
        data["rue"] = street.name
        data["par_numero"] = _by_number(rows)
        return ProviderData(data=data)


def _distribution(rows: list[dict[str, Any]], total: Any) -> dict[str, Any]:
    energy = Counter(str(row["etiquette_dpe"]) for row in rows if row.get("etiquette_dpe"))
    climate = Counter(str(row["etiquette_ges"]) for row in rows if row.get("etiquette_ges"))
    return {
        "nb_dpe_total": total,
        "nb_dpe_analyses": len(rows),
        "repartition_dpe": dict(sorted(energy.items())),
        "repartition_ges": dict(sorted(climate.items())),
        "etiquette_dominante": energy.most_common(1)[0][0] if energy else None,
        "analyse": energy_assessment(energy),
    }


def _leading_number(label: str) -> int:
    """Partie numérique d'un numéro de voie (« 19bis » -> 19), pour le tri."""
    digits = "".join(takewhile(str.isdigit, label))
    return int(digits) if digits else 0


def _by_number(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Synthèse par numéro de la voie : nombre de diagnostics, étiquette la plus fréquente."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        number = str(row.get("numero_voie_ban") or "").strip()
        if number:
            groups.setdefault(number, []).append(row)
    summary = []
    for number, items in groups.items():
        labels = Counter(str(item["etiquette_dpe"]) for item in items if item.get("etiquette_dpe"))
        years = [y for item in items if (y := to_float(item.get("annee_construction")))]
        summary.append(
            {
                "numero": number,
                "nb_dpe": len(items),
                "etiquette_dominante": labels.most_common(1)[0][0] if labels else None,
                "annee_construction": round(min(years)) if years else None,
            }
        )
    summary.sort(key=lambda entry: (_leading_number(str(entry["numero"])), str(entry["numero"])))
    return summary[:_MAX_NUMBERS]


def _nearest(row: dict[str, Any]) -> dict[str, Any]:
    distance = to_float(row.get("_geo_distance"))
    return {
        "etiquette_dpe": row.get("etiquette_dpe"),
        "etiquette_ges": row.get("etiquette_ges"),
        "date": row.get("date_etablissement_dpe"),
        "distance_m": round(distance) if distance is not None else None,
    }
