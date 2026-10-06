"""Règles métier de la couche Service et nouvelles sources (ANFR, bruit, itinéraires)."""

from typing import Any

import pytest

from app.core.errors import NoDataError, RepositoryError, SourceError
from app.services import insights
from app.services.providers.base import AuditContext
from app.services.providers.environment import AirQualityProvider
from app.services.providers.housing import MobileNetworkProvider, NoiseProvider
from app.services.providers.poi import ESTIMATED, OVERPASS_ENDPOINTS, ROUTED, PoiProvider

ANGERS = AuditContext(lat=47.4706, lon=-0.5517, citycode="49007")


def test_clay_and_radon_recommendations_use_the_agreed_wording() -> None:
    advice = insights.risk_recommendations(
        {"argiles": {"code": "2"}, "radon": {"classe_potentiel": "3"}}
    )
    assert advice == {
        "argiles": (
            "Sol sensible : recherchez des fissures sur les façades. "
            "Étude de sol exigée pour terrain à bâtir."
        ),
        "radon": "Niveau maximal maîtrisable : aérez chaque jour, posez un dosimètre en hiver.",
    }


@pytest.mark.parametrize(
    "risks",
    [
        {},
        {"argiles": {"code": "1"}, "radon": {"classe_potentiel": "1"}},
        {"argiles": {"code": None}, "radon": None},
        {"sismicite": {"code": "2"}},
    ],
)
def test_no_recommendation_below_the_thresholds(risks: dict[str, Any]) -> None:
    assert insights.risk_recommendations(risks) == {}


def test_flood_and_seismic_recommendations() -> None:
    advice = insights.risk_recommendations(
        {"inondation": {"concerne": True}, "sismicite": {"code": "4"}, "argiles": {"code": "3"}}
    )
    assert set(advice) == {"inondation", "sismicite", "argiles"}


@pytest.mark.parametrize(
    ("distribution", "share", "leverage"),
    [
        ({"C": 29, "D": 31, "E": 23, "F": 10, "G": 7}, 40.0, False),  # 40 % pile : pas au-delà
        ({"C": 20, "D": 30, "E": 25, "F": 15, "G": 10}, 50.0, True),
        ({"A": 10, "B": 10}, 0.0, False),
        ({}, None, False),
    ],
)
def test_energy_flag_requires_more_than_40_percent_of_efg(
    distribution: dict[str, int], share: float | None, leverage: bool
) -> None:
    result = insights.energy_assessment(distribution)
    assert result["part_efg_pct"] == share
    assert result["levier_negociation"] is leverage
    assert (result["message"] is not None) is leverage


def test_relief_summary() -> None:
    flat = {"N": 20.0, "E": 1.0, "SE": 2.0, "S": 0.5, "SO": 1.0, "O": 3.0}
    assert insights.relief_summary(flat).startswith("Horizon dégagé de l'est à l'ouest")
    alpine = {"N": 13.6, "E": 19.2, "SE": 24.5, "S": 13.4, "SO": 1.6, "O": 20.2}
    summary = insights.relief_summary(alpine)
    assert "Relief marqué au sud-est (24°" in summary
    assert summary.endswith("Meilleur dégagement au sud-ouest.")


def test_flood_atlas_silence_is_never_presented_as_safe() -> None:
    advice = insights.risk_recommendations({"inondation": {"concerne": False}})
    assert "PPRI" in advice["inondation"]
    assert "remontées de nappe" in advice["inondation"]
    assert (
        insights.risk_recommendations({"inondation": {"concerne": True}})["inondation"]
        != (advice["inondation"])
    )


def test_noise_message_only_speaks_for_the_mapped_infrastructures() -> None:
    quiet = insights.noise_message(None, ["fer"])
    assert "infrastructures ferroviaires." in quiet
    assert "routières" not in quiet
    assert "Bruit routier non cartographié" in quiet
    loud = insights.noise_message(70, ["route"])
    assert loud.startswith("Exposition très forte")
    assert "Bruit ferroviaire non cartographié" in loud
    complete = insights.noise_message(None, ["fer", "route"])
    assert "routières et ferroviaires." in complete
    assert "non cartographié" not in complete


def test_noise_message_by_level() -> None:
    assert "moins de 55 dB" in insights.noise_message(None)
    assert insights.noise_message(55).startswith("Exposition modérée")
    assert insights.noise_message(65).startswith("Exposition forte")
    assert insights.noise_message(75).startswith("Exposition très forte")


class FakeHttp:
    """Renvoie des réponses préparées par source et mémorise les appels."""

    def __init__(self, responses: dict[str, Any]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def _answer(self, source: str, **kwargs: Any) -> Any:
        self.calls.append((source, kwargs))
        response = self._responses[source]
        if isinstance(response, Exception):
            raise response
        return response

    async def get_json(self, source: str, url: str, *, params: Any = None) -> Any:
        return await self._answer(source, params=params)

    async def post_form_json(
        self, source: str, url: str, *, data: Any, timeout_s: float | None = None
    ) -> Any:
        return await self._answer(source, url=url, data=data, timeout_s=timeout_s)

    async def post_json(self, source: str, url: str, *, payload: Any, headers: Any = None) -> Any:
        return await self._answer(source, payload=payload, headers=headers)


def antenna(
    operator: str, generation: str, site: int, lat: float, status: str = "En service"
) -> dict[str, Any]:
    return {
        "fields": {
            "adm_lb_nom": operator,
            "generation": generation,
            "sup_id": site,
            "statut": status,
            "coordonnees": f"{lat} , -0.5517",
        }
    }


async def test_mobile_network_groups_active_antennas_by_operator() -> None:
    http = FakeHttp(
        {
            "anfr": {
                "nhits": 5,
                "records": [
                    antenna("ORANGE", "4G", 1, 47.4715),
                    antenna("ORANGE", "5G", 1, 47.4715, "Techniquement opérationnel"),
                    antenna("ORANGE", "4G", 2, 47.4760),
                    antenna("FREE MOBILE", "4G", 3, 47.4730),
                    antenna("SFR", "5G", 4, 47.4720, "Projet approuvé"),
                ],
            }
        }
    )
    output = await MobileNetworkProvider(http).fetch(ANGERS)  # type: ignore[arg-type]

    operators = {op["nom"]: op for op in output.data["operateurs"]}
    assert set(operators) == {"Orange", "Free Mobile"}, "une antenne en projet n'est pas comptée"
    assert operators["Orange"]["generations"] == ["4G", "5G"]
    assert operators["Orange"]["nb_sites"] == 2
    assert operators["Orange"]["site_le_plus_proche_m"] == pytest.approx(100, abs=5)
    assert output.data["operateurs_5g"] == ["Orange"]
    assert output.data["nb_sites"] == 3
    assert http.calls[0][1]["params"]["geofilter.distance"] == "47.4706,-0.5517,1000"


async def test_mobile_network_without_antenna_is_empty() -> None:
    http = FakeHttp({"anfr": {"nhits": 0, "records": []}})
    provider = MobileNetworkProvider(http)  # type: ignore[arg-type]
    with pytest.raises(NoDataError):
        await provider.fetch(ANGERS)


class NoiseRepository:
    def __init__(self, levels: list[dict[str, Any]], covered: list[str]) -> None:
        self._levels, self._covered = levels, covered

    async def noise_levels(self, lat: float, lon: float) -> list[dict[str, Any]]:
        return self._levels

    async def noise_coverage(self, lat: float, lon: float) -> list[str]:
        return self._covered


async def test_noise_reports_the_loudest_class_and_its_sources() -> None:
    repository = NoiseRepository(
        [{"infrastructure": "fer", "db_min": 70}, {"infrastructure": "route", "db_min": 55}],
        ["fer", "route"],
    )
    data = (await NoiseProvider(repository).fetch(ANGERS)).data  # type: ignore[arg-type]
    assert data["niveau_max_db"] == 70
    assert data["sources"][0] == {"infrastructure": "fer", "db_min": 70, "db_max": 75}
    assert data["message"].startswith("Exposition très forte")


async def test_noise_distinguishes_quiet_from_unmapped() -> None:
    repository = NoiseRepository([], ["fer", "route"])
    quiet = (await NoiseProvider(repository).fetch(ANGERS)).data  # type: ignore[arg-type]
    assert quiet["niveau_max_db"] is None
    assert "moins de 55 dB" in quiet["message"]
    assert quiet["infrastructures_couvertes"] == ["fer", "route"]

    # Nantes : seul le ferroviaire est ingéré, le constat ne doit rien dire de la rocade.
    rail_only = NoiseRepository([], ["fer"])
    partial = (await NoiseProvider(rail_only).fetch(ANGERS)).data  # type: ignore[arg-type]
    assert "routières" not in partial["message"]
    assert "Bruit routier non cartographié" in partial["message"]

    unmapped = NoiseProvider(NoiseRepository([], []))  # type: ignore[arg-type]
    with pytest.raises(NoDataError):
        await unmapped.fetch(ANGERS)


OVERPASS = {
    "elements": [
        {"lat": 47.4715, "lon": -0.5517, "tags": {"shop": "bakery", "name": "Boulangerie"}},
        {"lat": 47.4742, "lon": -0.5517, "tags": {"highway": "bus_stop", "name": "Ralliement"}},
    ]
}


async def test_walking_times_are_estimated_without_api_key() -> None:
    http = FakeHttp({"overpass_1": OVERPASS})
    data = (await PoiProvider(http).fetch(ANGERS)).data  # type: ignore[arg-type]

    assert data["methode_temps"] == ESTIMATED
    bakery = data["categories"]["commerces"]["plus_proche"]
    # 100 m à vol d'oiseau x 1,3 de détour, à 80 m/min.
    assert (bakery["distance_m"], bakery["marche_min"]) == (100, 2)
    assert "position" not in bakery
    assert [source for source, _ in http.calls] == ["overpass_1"]


async def test_walking_times_come_from_openrouteservice_when_a_key_is_set() -> None:
    http = FakeHttp({"overpass_1": OVERPASS, "openrouteservice": {"durations": [[540.0, 250.0]]}})
    data = (await PoiProvider(http, ors_api_key="cle").fetch(ANGERS)).data  # type: ignore[arg-type]

    assert data["methode_temps"] == ROUTED
    assert data["categories"]["transports"]["plus_proche"]["marche_min"] == 9
    assert data["categories"]["commerces"]["plus_proche"]["marche_min"] == 4
    request = http.calls[1][1]
    assert request["headers"] == {"Authorization": "cle"}
    assert request["payload"]["locations"][0] == [-0.5517, 47.4706]
    assert request["payload"]["destinations"] == [1, 2]


async def test_openrouteservice_failure_falls_back_to_the_estimate() -> None:
    http = FakeHttp({"overpass_1": OVERPASS, "openrouteservice": SourceError("timeout")})
    data = (await PoiProvider(http, ors_api_key="cle").fetch(ANGERS)).data  # type: ignore[arg-type]

    assert data["methode_temps"] == ESTIMATED
    assert data["categories"]["commerces"]["plus_proche"]["marche_min"] == 2


async def test_overpass_falls_back_to_the_next_endpoint_on_504_or_timeout() -> None:
    http = FakeHttp(
        {
            "overpass_1": SourceError("http_error", "504"),
            "overpass_2": SourceError("timeout"),
            "overpass_3": OVERPASS,
        }
    )
    provider = PoiProvider(http)  # type: ignore[arg-type]

    data = (await provider.fetch(ANGERS)).data

    assert data["categories"]["commerces"]["nb"] == 1
    assert [source for source, _ in http.calls] == ["overpass_1", "overpass_2", "overpass_3"]
    assert [call["url"] for _, call in http.calls] == list(OVERPASS_ENDPOINTS)
    assert all(call["timeout_s"] == 5.0 for _, call in http.calls)


async def test_overpass_starts_with_the_endpoint_that_last_answered() -> None:
    http = FakeHttp(
        {"overpass_1": SourceError("timeout"), "overpass_2": OVERPASS, "overpass_3": OVERPASS}
    )
    provider = PoiProvider(http)  # type: ignore[arg-type]
    await provider.fetch(ANGERS)
    http.calls.clear()

    await provider.fetch(ANGERS)

    assert [source for source, _ in http.calls] == ["overpass_2"]


async def test_overpass_reports_the_failure_when_every_endpoint_is_down() -> None:
    http = FakeHttp(
        {
            "overpass_1": SourceError("http_error", "504"),
            "overpass_2": SourceError("circuit_open"),
            "overpass_3": SourceError("timeout"),
        }
    )
    provider = PoiProvider(http)  # type: ignore[arg-type]
    with pytest.raises(SourceError) as error:
        await provider.fetch(ANGERS)
    assert error.value.kind == "timeout"
    assert len(http.calls) == 3


class PoiRepository:
    def __init__(self, rows: list[dict[str, Any]] | None | Exception) -> None:
        self._rows = rows
        self.calls: list[tuple[float, float, int, int]] = []

    async def pois_nearby(
        self, lat: float, lon: float, radius_m: int, limit: int
    ) -> list[dict[str, Any]] | None:
        self.calls.append((lat, lon, radius_m, limit))
        if isinstance(self._rows, Exception):
            raise self._rows
        return self._rows


LOCAL_POIS: list[dict[str, Any]] = [
    {
        "categorie": "commerces",
        "type": "bakery",
        "nom": "Fournil",
        "lon": -0.55,
        "lat": 47.47,
        "distance_m": 99.6,
    },
    {
        "categorie": "transports",
        "type": "bus_stop",
        "nom": "Ralliement",
        "lon": -0.551,
        "lat": 47.472,
        "distance_m": 180.2,
    },
    {
        "categorie": "transports",
        "type": "tram_stop",
        "nom": None,
        "lon": -0.552,
        "lat": 47.473,
        "distance_m": 320.0,
    },
]


async def test_pois_come_from_the_local_reference_without_calling_overpass() -> None:
    http = FakeHttp({})
    repository = PoiRepository([dict(row) for row in LOCAL_POIS])
    data = (await PoiProvider(http, repository=repository).fetch(ANGERS)).data  # type: ignore[arg-type]

    assert http.calls == []
    assert repository.calls == [(ANGERS.lat, ANGERS.lon, 500, 400)]
    assert data["categories"]["transports"] == {
        "nb": 2,
        "plus_proche": {
            "type": "bus_stop",
            "nom": "Ralliement",
            "distance_m": 180,
            "marche_min": 3,
        },
    }
    assert data["categories"]["commerces"]["plus_proche"]["distance_m"] == 100
    assert data["categories"]["sante"] == {"nb": 0, "plus_proche": None}
    assert data["methode_temps"] == ESTIMATED


async def test_platforms_of_the_same_stop_count_once() -> None:
    def stop(name: str | None, distance: float) -> dict[str, Any]:
        return {
            "categorie": "transports",
            "type": "bus_stop",
            "nom": name,
            "lon": -0.55,
            "lat": 47.47,
            "distance_m": distance,
        }

    rows = [stop("Ralliement", 80), stop("ralliement", 95), stop("Foch", 200), stop(None, 250)]
    rows += [stop(None, 260), {**stop("Fournil", 60), "categorie": "commerces"}]
    rows += [{**stop("Fournil", 300), "categorie": "commerces"}]
    data = (await PoiProvider(FakeHttp({}), repository=PoiRepository(rows)).fetch(ANGERS)).data  # type: ignore[arg-type]

    # Ralliement (deux quais), Foch, et deux arrêts sans nom, comptés séparément.
    assert data["categories"]["transports"]["nb"] == 4
    assert data["categories"]["transports"]["plus_proche"]["distance_m"] == 80
    # Deux boulangeries d'une même enseigne restent deux commerces.
    assert data["categories"]["commerces"]["nb"] == 2


async def test_ingested_area_without_poi_is_an_answer_not_a_fallback() -> None:
    http = FakeHttp({})
    data = (await PoiProvider(http, repository=PoiRepository([])).fetch(ANGERS)).data  # type: ignore[arg-type]

    assert http.calls == []
    assert all(summary["nb"] == 0 for summary in data["categories"].values())


@pytest.mark.parametrize("rows", [None, RepositoryError("base indisponible")])
async def test_overpass_is_the_fallback_for_an_area_not_ingested(
    rows: None | Exception,
) -> None:
    http = FakeHttp({"overpass_1": OVERPASS})
    provider = PoiProvider(http, repository=PoiRepository(rows))  # type: ignore[arg-type]
    data = (await provider.fetch(ANGERS)).data

    assert [source for source, _ in http.calls] == ["overpass_1"]
    assert data["categories"]["commerces"]["nb"] == 1


def atmo(
    code: str, day: str, level: int, zone_type: str = "commune", **extra: Any
) -> dict[str, Any]:
    properties = {
        "code_zone": code,
        "lib_zone": "Angers",
        "type_zone": zone_type,
        "date_ech": day,
        "code_qual": level,
        "code_no2": 1,
        "code_o3": level,
        "code_pm10": 1,
        "code_pm25": 2,
        "code_so2": 0,
        "source": "Air Pays de la Loire",
    }
    properties.update(extra)
    return {"properties": properties}


class AtmoHttp:
    """Flux Atmo France simulé : une réponse par liste de codes interrogée."""

    def __init__(self, by_codes: dict[str, list[dict[str, Any]]], epci: Any = "200071553") -> None:
        self._by_codes, self._epci = by_codes, epci
        self.filters: list[str] = []

    async def get_json(self, source: str, url: str, *, params: Any = None) -> Any:
        if source == "geo_api":
            if isinstance(self._epci, Exception):
                raise self._epci
            return {"codeEpci": self._epci}
        self.filters.append(params["CQL_FILTER"])
        for codes, features in self._by_codes.items():
            if codes in params["CQL_FILTER"]:
                return {"features": features}
        return {"features": []}


async def test_air_quality_returns_todays_atmo_index_and_tomorrows_forecast() -> None:
    http = AtmoHttp({"'49007'": [atmo("49007", "2099-01-02", 2), atmo("49007", "2099-01-01", 3)]})
    data = (await AirQualityProvider(http).fetch(ANGERS)).data  # type: ignore[arg-type]

    assert (data["indice"], data["qualificatif"], data["date"]) == (3, "Dégradé", "2099-01-01")
    assert data["demain"] == {"indice": 2, "qualificatif": "Moyen"}
    assert data["zone"] == {"code": "49007", "nom": "Angers", "type": "commune"}
    assert data["sous_indices"] == {"pm2_5": 2, "pm10": 1, "no2": 1, "o3": 3, "so2": None}
    assert data["polluants_dominants"] == ["ozone"]
    assert data["producteur"] == "Air Pays de la Loire"
    assert "code_zone IN ('49007') AND date_ech >= '" in http.filters[0]


async def test_air_quality_prefers_the_district_over_the_whole_city() -> None:
    paris = AuditContext(lat=48.85, lon=2.37, citycode="75111")
    http = AtmoHttp(
        {"'75111', '75056'": [atmo("75056", "2099-01-01", 4), atmo("75111", "2099-01-01", 3)]}
    )
    data = (await AirQualityProvider(http).fetch(paris)).data  # type: ignore[arg-type]
    assert (data["zone"]["code"], data["indice"]) == ("75111", 3)


async def test_air_quality_falls_back_to_the_intercommunality() -> None:
    rural = AuditContext(lat=47.35, lon=-0.75, citycode="49063")
    http = AtmoHttp({"'200071553'": [atmo("200071553", "2099-01-01", 3, "EPCI")]})
    data = (await AirQualityProvider(http).fetch(rural)).data  # type: ignore[arg-type]

    assert data["zone"]["type"] == "epci"
    assert data["indice"] == 3
    assert len(http.filters) == 2


async def test_air_quality_is_empty_when_no_level_is_published() -> None:
    # 0 = indice absent, 7 = évènement : ni l'un ni l'autre n'est un niveau de qualité.
    unusable = AtmoHttp(
        {"'49007'": [atmo("49007", "2099-01-01", 0), atmo("49007", "2099-01-02", 7)]}
    )
    provider = AirQualityProvider(unusable)  # type: ignore[arg-type]
    with pytest.raises(NoDataError):
        await provider.fetch(ANGERS)

    epci_lookup_down = AirQualityProvider(AtmoHttp({}, epci=SourceError("timeout")))  # type: ignore[arg-type]
    with pytest.raises(NoDataError):
        await epci_lookup_down.fetch(ANGERS)


@pytest.mark.parametrize(
    ("level", "label"),
    [(1, "Bon"), (2, "Moyen"), (3, "Dégradé"), (4, "Mauvais"), (5, "Très mauvais"),
     (6, "Extrêmement mauvais")],
)  # fmt: skip
def test_atmo_label(level: int, label: str) -> None:
    assert insights.atmo_label(level) == label
