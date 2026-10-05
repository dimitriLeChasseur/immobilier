"""Contexte locatif : encadrement des loyers, occupation à l'IRIS, connectivité, copropriété."""

from typing import Any

import pytest

from app.core.errors import NoDataError
from app.services.providers.base import AuditContext
from app.services.providers.dvf import Sale, summarize
from app.services.providers.housing import (
    CondoChargesProvider,
    ConnectivityProvider,
    RentalMarketProvider,
)
from app.services.providers.rental_rules import rent_control

ANGERS = AuditContext(lat=47.47, lon=-0.55, citycode="49007", region="Pays de la Loire")


@pytest.mark.parametrize(
    ("codes", "epci", "status", "territory"),
    [
        (["75111", "75056"], None, "oui", "Paris"),
        (["69383", "69123"], None, "oui", "Lyon"),
        (["93048"], None, "oui", "Est Ensemble"),
        (["93066"], None, "oui", "Plaine Commune"),
        (["59350"], None, "oui", "Lille, Hellemmes et Lomme"),
        (["38185"], "200040715", "partiel", "Grenoble-Alpes Métropole"),
        (["64102"], "200067106", "partiel", "Communauté d'agglomération du Pays Basque"),
        (["49007"], "244900015", "non", None),
        (["13201", "13055"], None, "non", None),
    ],
)
def test_rent_control(
    codes: list[str], epci: str | None, status: str, territory: str | None
) -> None:
    rule = rent_control(codes, epci)
    assert (rule.status, rule.territory) == (status, territory)


class FakeHttp:
    def __init__(self, iris: list[dict[str, Any]], epci: str | None) -> None:
        self._iris, self._epci = iris, epci

    async def get_json(self, source: str, url: str, *, params: Any = None) -> Any:
        if source == "ign_wfs":
            return {"features": [{"properties": zone} for zone in self._iris]}
        return {"codeEpci": self._epci}


class FakeRepository:
    def __init__(self, housing: dict[str, Any] | None = None, fibre: dict[str, Any] | None = None):
        self._housing, self._fibre = housing, fibre

    async def iris_housing(self, code_iris: str) -> dict[str, Any] | None:
        return self._housing

    async def connectivity(self, codes: list[str]) -> dict[str, Any] | None:
        return self._fibre


HOUSING = {
    "annee": 2022,
    "logements": 2000,
    "residences_principales": 1600,
    "residences_secondaires": 100,
    "logements_vacants": 300,
    "proprietaires": 400,
    "locataires": 1120,
    "locataires_hlm": 160,
}


async def test_rental_market_computes_shares_for_the_iris() -> None:
    provider = RentalMarketProvider(
        FakeHttp([{"code_iris": "490070107", "nom_iris": "Ralliement"}], "244900015"),  # type: ignore[arg-type]
        FakeRepository(housing=HOUSING),  # type: ignore[arg-type]
    )
    output = await provider.fetch(ANGERS)
    occupancy = output.data["occupation"]
    assert occupancy["iris"] == {"code": "490070107", "nom": "Ralliement"}
    assert occupancy["part_proprietaires_pct"] == 25.0
    assert occupancy["part_locataires_pct"] == 70.0
    assert occupancy["part_locataires_hlm_pct"] == 10.0
    assert occupancy["part_vacants_pct"] == 15.0
    assert output.data["encadrement_loyers"]["statut"] == "non"
    assert output.data["permis_de_louer"] == {"statut": "inconnu"}


async def test_rental_market_without_iris_still_reports_rent_control() -> None:
    provider = RentalMarketProvider(
        FakeHttp([], None),  # type: ignore[arg-type]
        FakeRepository(),  # type: ignore[arg-type]
    )
    paris = AuditContext(lat=48.85, lon=2.37, citycode="75111", region="Île-de-France")
    output = await provider.fetch(paris)
    assert output.data["occupation"] is None
    assert output.data["encadrement_loyers"]["statut"] == "oui"


async def test_connectivity_shares_and_missing_commune() -> None:
    fibre = {
        "date_donnees": "2026-06-30",
        "nb_locaux": 1000,
        "eligibles_fibre": 973,
        "eligibles_cable": 0,
        "eligibles_4g_fixe": 999,
    }
    output = await ConnectivityProvider(FakeRepository(fibre=fibre)).fetch(ANGERS)  # type: ignore[arg-type]
    assert output.data["part_fibre_pct"] == 97.3
    assert output.data["niveau"] == "commune"
    without_data = ConnectivityProvider(FakeRepository())  # type: ignore[arg-type]
    with pytest.raises(NoDataError):
        await without_data.fetch(ANGERS)


async def test_condo_charges_prefer_city_then_region() -> None:
    provider = CondoChargesProvider()
    nantes = AuditContext(lat=47.2, lon=-1.5, citycode="44109", region="Pays de la Loire")
    paris = AuditContext(lat=48.8, lon=2.3, citycode="75111", region="Île-de-France")
    unknown = AuditContext(lat=0, lon=0, citycode="98818")

    assert (await provider.fetch(nantes)).data["territoire"] == "Nantes"
    assert (await provider.fetch(paris)).data["charges_m2_an"] == 40.28
    region = (await provider.fetch(ANGERS)).data
    assert (region["niveau"], region["charges_m2_an"]) == ("region", 20.06)
    with pytest.raises(NoDataError):
        await provider.fetch(unknown)


def test_dvf_spread_reports_quartiles_and_extremes() -> None:
    sales = [
        Sale(
            date="2025-01-01",
            price=price * 50,
            surface_m2=50,
            kind="appartement",
            distance_m=10,
            rooms=2,
        )
        for price in (2000, 3000, 4000, 5000, 6000)
    ]
    summary = summarize(sales)
    assert summary["dispersion"] == {"min": 2000, "q1": 2500, "q3": 5500, "max": 6000}
    assert summary["dernieres_ventes"][0]["pieces"] == 2
