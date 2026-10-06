"""Géocodage : adresse la plus proche, et adresse choisie par l'utilisateur une fois vérifiée."""

from typing import Any

import pytest

from app.core.errors import SourceError
from app.services.geocoding import BanGeocoder

POINT = (47.47408, -0.55107)
NEAREST = {
    "features": [
        {
            "properties": {
                "id": "49007_1350_00008",
                "label": "8 Rue du Canal 49100 Angers",
                "citycode": "49007",
                "postcode": "49100",
                "city": "Angers",
                "context": "49, Maine-et-Loire, Pays de la Loire",
            }
        }
    ]
}


def number(lon: float, lat: float, kind: str = "numero") -> dict[str, Any]:
    return {
        "type": kind,
        "position": {"type": "Point", "coordinates": [lon, lat]},
        "numero": 10,
        "suffixe": None,
        "codePostal": "49100",
        "voie": {"nomVoie": "Rue du Canal"},
        "commune": {"nom": "Angers"},
    }


class FakeHttp:
    def __init__(self, lookup: Any) -> None:
        self._lookup = lookup
        self.lookups: list[str] = []

    async def get_json(self, source: str, url: str, *, params: Any = None) -> Any:
        if source == "ban":
            return NEAREST
        self.lookups.append(url)
        if isinstance(self._lookup, Exception):
            raise self._lookup
        return self._lookup


async def test_the_address_chosen_by_the_user_wins_when_it_stands_at_the_point() -> None:
    http = FakeHttp(number(-0.55110, 47.47410))
    location = await BanGeocoder(http).reverse(*POINT, "49007_1350_00010")  # type: ignore[arg-type]
    assert location is not None
    assert location.adresse_id == "49007_1350_00010"
    # Le rapport porte le nom de l'adresse choisie, pas celui de sa voisine.
    assert location.label == "10 Rue du Canal 49100 Angers"
    assert http.lookups[0].endswith("/lookup/49007_1350_00010")


@pytest.mark.parametrize(
    "lookup",
    [
        number(2.3522, 48.8566),  # un numéro existant, mais à Paris
        # Le numéro voisin, à une vingtaine de mètres : ce n'est pas l'adresse du point.
        number(-0.55083, 47.47390),
        number(-0.55110, 47.47410, kind="voie"),
        {"type": "numero"},
        SourceError("timeout"),
    ],
)
async def test_an_unverified_identifier_falls_back_to_the_nearest_address(lookup: Any) -> None:
    http = FakeHttp(lookup)
    location = await BanGeocoder(http).reverse(*POINT, "49007_1350_00010")  # type: ignore[arg-type]
    assert location is not None
    assert location.adresse_id == "49007_1350_00008"
    assert location.label == "8 Rue du Canal 49100 Angers"


@pytest.mark.parametrize("ban_id", ["", "49007", "49007_1350", "49007_1350_00010/../x"])
async def test_only_house_number_identifiers_are_looked_up(ban_id: str) -> None:
    http = FakeHttp(number(-0.55110, 47.47410))
    location = await BanGeocoder(http).reverse(*POINT, ban_id)  # type: ignore[arg-type]
    assert location is not None
    assert location.adresse_id == "49007_1350_00008"
    assert http.lookups == []
