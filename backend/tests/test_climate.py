"""Source climat_air_energie : inventaires d'émissions et de consommations de l'intercommunalité."""

from typing import Any

import pytest

from app.core.errors import NoDataError, SourceError
from app.services.providers.base import AuditContext
from app.services.providers.environment import ClimateAirEnergyProvider

LYON = AuditContext(lat=45.76, lon=4.835, citycode="69123")
EPCI = {"code": "200046977", "nom": "Métropole de Lyon"}


def inventory(year: int, sector: str, **values: float | str) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "code": EPCI["code"],
        "annee": year,
        "code_pcaet": sector,
        "population": 1000,
        "superficie": 10.0,
        "source": "Atmo Auvergne-Rhône-Alpes",
        "versioning_inventaire": "M2024",
    }
    properties.update(values)
    return {"properties": properties}


LATEST = [
    inventory(2022, "All", ges=4000.0, nox=20.0, pm25=5.0),
    inventory(2022, "6", ges=1500.0, nox=12.0, pm25=1.0),
    inventory(
        2022,
        "34",
        ges=1200.0,
        nox=5.0,
        pm25=3.5,
        conso=100.0,
        conso_elec=40.0,
        conso_gn=30.0,
        conso_pp=20.0,
        conso_bois=10.0,
        conso_chaleur=0.0,
        conso_cms=0.0,
        conso_autres_enr=0.0,
        conso_autres=0.0,
    ),
    inventory(2022, "219", ges=1300.0, nox=3.0, pm25=0.5),
    inventory(2018, "All", ges=5000.0, nox=25.0, pm25=6.0),
]


class InventoryHttp:
    """Flux des inventaires simulé, et intercommunalité de la commune (API Géo)."""

    def __init__(self, rows: list[dict[str, Any]] | Exception, epci: Any = EPCI) -> None:
        self._rows, self._epci = rows, epci
        self.filters: list[str] = []

    async def get_json(self, source: str, url: str, *, params: Any = None) -> Any:
        if source == "geo_api":
            return {"codeEpci": self._epci and self._epci["code"], "epci": self._epci}
        self.filters.append(params["CQL_FILTER"])
        if isinstance(self._rows, Exception):
            raise self._rows
        return {"features": self._rows}


async def test_climate_describes_the_latest_inventory_of_the_intercommunality() -> None:
    http = InventoryHttp(LATEST)
    data = (await ClimateAirEnergyProvider(http).fetch(LYON)).data  # type: ignore[arg-type]

    assert data["territoire"] == EPCI
    assert (data["millesime"], data["version_inventaire"]) == (2022, "M2024")
    assert data["producteur"] == "Atmo Auvergne-Rhône-Alpes"
    assert data["ges"] == {
        "t_par_habitant": 4.0,
        "evolution_depuis_2018_pct": -20.0,
        "repere_t_par_habitant": 5.73,
    }
    assert data["nox"] == {
        "t_par_km2": 2.0,
        "secteur_dominant": "Transport routier",
        "repere_t_par_km2": 1.212,
    }
    assert data["pm2_5"]["secteur_dominant"] == "Résidentiel et tertiaire"
    assert data["energie_residentiel_tertiaire"] == {
        "electricite": 40.0,
        "gaz": 30.0,
        "produits_petroliers": 20.0,
        "bois": 10.0,
        "reseau_chaleur": 0.0,
        "autres": 0.0,
    }
    assert data["repere"]["territoire"] == "France métropolitaine"
    assert data["repere"]["millesime"] == 2022
    assert data["repere"]["energie_residentiel_tertiaire"]["bois"] == 12.5
    assert http.filters == ["code = '200046977'"]


async def test_climate_compares_overseas_with_mainland_france_the_same_year() -> None:
    # Outre-mer : dernier millésime 2018, sans détail par secteur ici.
    fort_de_france = AuditContext(lat=14.6, lon=-61.07, citycode="97209")
    http = InventoryHttp([inventory(2018, "All", ges=3000.0, nox=10.0, pm25=2.0)])
    data = (await ClimateAirEnergyProvider(http).fetch(fort_de_france)).data  # type: ignore[arg-type]

    assert data["millesime"] == 2018
    assert data["ges"] == {
        "t_par_habitant": 3.0,
        "evolution_depuis_2018_pct": None,
        "repere_t_par_habitant": 6.44,
    }
    assert data["nox"]["secteur_dominant"] is None
    assert data["energie_residentiel_tertiaire"] is None
    assert data["repere"]["millesime"] == 2018


async def test_climate_has_no_benchmark_for_a_year_without_one() -> None:
    http = InventoryHttp([inventory(2010, "All", ges=3000.0, nox=10.0, pm25=2.0)])
    data = (await ClimateAirEnergyProvider(http).fetch(LYON)).data  # type: ignore[arg-type]
    assert (data["repere"], data["ges"]["repere_t_par_habitant"]) == (None, None)


@pytest.mark.parametrize(
    "http",
    [
        # Intercommunalité créée après le dernier inventaire : absente du flux.
        InventoryHttp([]),
        # Commune sans intercommunalité (îles monocommunales).
        InventoryHttp(LATEST, epci=None),
        # Inventaire non communiqué (Martinique) : des zéros partout, pas des émissions nulles.
        InventoryHttp([inventory(2018, "All", ges=0.0, nox=0.0, pm25=0.0)]),
    ],
)
async def test_climate_is_empty_without_an_inventory_for_the_intercommunality(
    http: InventoryHttp,
) -> None:
    with pytest.raises(NoDataError):
        await ClimateAirEnergyProvider(http).fetch(LYON)  # type: ignore[arg-type]


async def test_climate_fails_when_the_inventory_feed_fails() -> None:
    http = InventoryHttp(SourceError("timeout"))
    with pytest.raises(SourceError):
        await ClimateAirEnergyProvider(http).fetch(LYON)  # type: ignore[arg-type]


async def test_climate_does_not_benchmark_scope_one_greenhouse_gases() -> None:
    # Occitanie : GES de l'intercommunalité sans le scope 2, plus bas par construction que
    # le repère métropolitain, qui l'inclut.
    occitanie = [inventory(2022, "All", ges=3000.0, nox=10.0, pm25=2.0, aasqa="76")]
    data = (await ClimateAirEnergyProvider(InventoryHttp(occitanie)).fetch(LYON)).data  # type: ignore[arg-type]
    assert data["ges"]["t_par_habitant"] == 3.0
    assert data["ges"]["repere_t_par_habitant"] is None
    assert data["nox"]["repere_t_par_km2"] == 1.212
