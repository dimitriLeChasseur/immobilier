"""Étape 6 : bâtiment, copropriété, risques complémentaires, servitudes, zonage, loyers."""

from typing import Any

import pytest

from app.core.errors import NoDataError, SourceError
from app.schemas.audit import SourceResult
from app.services.providers.apicarto import CadastreProvider, UrbanismeProvider, parse_parcel_id
from app.services.providers.base import AuditContext
from app.services.providers.building import BuildingProvider
from app.services.providers.georisques import GeorisquesProvider
from app.services.providers.housing import RentalMarketProvider
from app.services.providers.market import RentsProvider
from app.services.street import Street
from app.services.synthesis import build_synthesis

CTX = AuditContext(lat=47.47408, lon=-0.55107, citycode="49007", address_id="49007_1350_00008")


class FakeHttp:
    """Répond selon l'adresse appelée ; une exception enregistrée est levée."""

    def __init__(self, routes: dict[str, Any]) -> None:
        self._routes = routes
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def get_json(self, source: str, url: str, *, params: Any = None) -> Any:
        self.calls.append((url, dict(params or {})))
        for fragment, outcome in self._routes.items():
            if fragment in url:
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome(params or {}) if callable(outcome) else outcome
        raise AssertionError(f"appel inattendu : {url}")


BUILDING = {
    "libelle_adr_principale_ban": "17 Rue Saint-Aubin 49100 Angers",
    "l_libelle_adr": ["17 rue saint aubin, 49100, Angers"],
    "annee_construction": 1850,
    "usage_niveau_1_txt": "Résidentiel collectif",
    "nb_niveau": 5,
    "hauteur_mean": 15,
    "nb_log": 8,
    "mat_mur_txt": "AUTRES",
    "mat_toit_txt": "ARDOISES",
    "type_energie_chauffage": "electricite",
    "type_installation_chauffage": "individuel",
    "classe_bilan_dpe": "C",
    "nb_classe_bilan_dpe_c": 3,
    "nb_classe_bilan_dpe_g": 0,
    "perimetre_bat_historique": True,
    "denomination_monument_historique": "Immeuble",
    "distance_monument_historique": 28,
}
CONDO = {
    "l_nom_copro": ["17 RUE SAINT AUBIN"],
    "numero_immat_principal": "AC7157225",
    "nb_lot_tot": 18.0,
    "nb_log": 8.0,
    "nb_lot_garpark": 0.0,
    "nb_lot_tertiaire": 1.0,
    "l_annee_construction": ["1850"],
}


async def test_building_is_found_through_the_server_resolved_address() -> None:
    http = FakeHttp(
        {
            "rel_batiment_groupe_adresse": [{"batiment_groupe_id": "bdnb-bg-1"}],
            "batiment_groupe_complet": [BUILDING],
            "batiment_groupe_rnc": [CONDO],
        }
    )
    data = (await BuildingProvider(http).fetch(CTX)).data  # type: ignore[arg-type]

    assert http.calls[0][1]["cle_interop_adr"] == "eq.49007_1350_00008"
    assert http.calls[1][1]["batiment_groupe_id"] == "eq.bdnb-bg-1"
    assert data["annee_construction"] == 1850
    assert data["nb_niveaux"] == 5
    # « AUTRES » : la base ne sait pas, on n'affiche pas un faux matériau.
    assert data["materiaux"] == {"murs": None, "toit": "Ardoises"}
    assert data["chauffage"] == {"energie": "Électricité", "installation": "Individuel"}
    assert data["dpe"] == {"classe": "C", "repartition": {"C": 3}}
    assert data["monument_historique"] == {
        "dans_perimetre": True,
        "nom": "Immeuble",
        "distance_m": 28,
    }
    assert data["copropriete"] == {
        "nom": "17 RUE SAINT AUBIN",
        "immatriculation": "AC7157225",
        "nb_lots": 18,
        "nb_logements": 8,
        "nb_lots_stationnement": 0,
        "nb_lots_tertiaires": 1,
        "annee_construction": 1850,
    }


async def test_building_without_registered_condominium_or_with_a_failing_part() -> None:
    routes: dict[str, Any] = {
        "rel_batiment_groupe_adresse": [{"batiment_groupe_id": "bdnb-bg-1"}],
        "batiment_groupe_complet": [BUILDING],
        "batiment_groupe_rnc": [],
    }
    house = (await BuildingProvider(FakeHttp(routes)).fetch(CTX)).data  # type: ignore[arg-type]
    assert house["copropriete"] is None

    routes["batiment_groupe_rnc"] = SourceError("timeout")
    partial = await BuildingProvider(FakeHttp(routes)).fetch(CTX)  # type: ignore[arg-type]
    assert partial.missing == ("copropriete",)
    assert "copropriete" not in partial.data
    assert partial.data["nb_logements"] == 8


@pytest.mark.parametrize(
    "ctx",
    [
        AuditContext(lat=47.47, lon=-0.55, citycode="49007"),
        AuditContext(
            lat=47.47,
            lon=-0.55,
            citycode="49007",
            address_id="49007_7050_00017",
            street=Street(id="49007_7050", name="x", points=((0.0, 0.0), (1.0, 1.0))),
        ),
    ],
)
async def test_building_needs_a_single_resolved_address(ctx: AuditContext) -> None:
    http = FakeHttp({})
    with pytest.raises(NoDataError):
        await BuildingProvider(http).fetch(ctx)  # type: ignore[arg-type]
    assert http.calls == []


async def test_unknown_address_has_no_building() -> None:
    with pytest.raises(NoDataError):
        await BuildingProvider(FakeHttp({"rel_batiment_groupe_adresse": []})).fetch(CTX)  # type: ignore[arg-type]


def test_parcel_identifiers_published_by_the_address_base() -> None:
    assert parse_parcel_id("490007   BR0335") == ("BR", "0335")
    assert parse_parcel_id("750101000A 0012") == ("0A", "0012")
    assert parse_parcel_id("49007000BR0335") == ("BR", "0335")
    assert parse_parcel_id("49007000BR335") is None
    assert parse_parcel_id(None) is None


async def test_parcel_falls_back_to_the_one_declared_for_the_address() -> None:
    def parcels(params: dict[str, Any]) -> dict[str, Any]:
        if "geom" in params:
            return {"features": []}
        assert params == {"code_insee": "49007", "section": "BR", "numero": "0335"}
        feature = {"idu": "49007000BR0335", "section": "BR", "numero": "0335", "contenance": 171}
        return {"features": [{"properties": feature}]}

    http = FakeHttp({"lookup": {"parcelles": ["490007   BR0335"]}, "cadastre/parcelle": parcels})
    data = (await CadastreProvider(http).fetch(CTX)).data  # type: ignore[arg-type]
    assert data["identifiant"] == "49007000BR0335"
    assert data["origine"] == "adresse"

    nothing = FakeHttp({"lookup": SourceError("timeout"), "cadastre/parcelle": {"features": []}})
    with pytest.raises(NoDataError):
        await CadastreProvider(nothing).fetch(CTX)  # type: ignore[arg-type]


def features(*properties: dict[str, Any]) -> dict[str, Any]:
    return {"features": [{"properties": item} for item in properties]}


async def test_zoning_lists_easements_and_prescriptions() -> None:
    http = FakeHttp(
        {
            "zone-urba": features({"libelle": "UA", "idurba": "doc"}),
            "assiette-sup-s": features(
                {"suptype": "ac1", "typeass": "Périmètre des abords"},
                {"suptype": "ac1", "typeass": "Périmètre des abords"},
                {"suptype": "zz9", "nomass": "Divers"},
            ),
            "prescription-surf": features({"libelle": "Immeuble protégé"}, {"libelle": None}),
        }
    )
    data = (await UrbanismeProvider(http).fetch(CTX)).data  # type: ignore[arg-type]
    assert [zone["libelle"] for zone in data["zones"]] == ["UA"]
    assert data["servitudes"] == [
        {
            "code": "AC1",
            "categorie": "Abords de monument historique",
            "detail": "Périmètre des abords",
        },
        {"code": "ZZ9", "categorie": "Servitude ZZ9", "detail": "Divers"},
    ]
    assert data["prescriptions"] == ["Immeuble protégé"]


async def test_zoning_survives_a_failing_easement_layer() -> None:
    http = FakeHttp(
        {
            "zone-urba": features({"libelle": "UA", "idurba": "doc"}),
            "assiette-sup-s": SourceError("timeout"),
            "prescription-surf": features(),
        }
    )
    result = await UrbanismeProvider(http).fetch(CTX)  # type: ignore[arg-type]
    assert result.missing == ("servitudes",)
    assert result.data["servitudes"] == []
    assert result.data["zones"]


def rows(*items: dict[str, Any], results: int | None = None) -> dict[str, Any]:
    return {"data": list(items), "results": len(items) if results is None else results}


async def test_georisques_adds_plans_industrial_past_and_cavities() -> None:
    http = FakeHttp(
        {
            "gaspar/risques": rows(),
            "gaspar/azi": rows(),
            "rga": {"codeExposition": "2", "exposition": "Exposition moyenne"},
            "zonage_sismique": rows({"code_zone": "2", "zone_sismicite": "2 - FAIBLE"}),
            "radon": rows({"classe_potentiel": "3"}),
            "installations_classees": rows(),
            "gaspar/catnat": rows(
                {"libelle_risque_jo": "Inondations", "date_debut_evt": "15/07/2003"},
                {"libelle_risque_jo": "Inondations", "date_debut_evt": "02/02/2021"},
                {"libelle_risque_jo": "Sécheresse", "date_debut_evt": "01/07/2018"},
            ),
            "gaspar/pprn": {
                "content": [
                    {"libPpr": "PPRi-Confluence de Maine", "modeleProcedure": "PPRN-I"},
                    {"libPpr": "PPRN-Mvt - Ardoisières", "modeleProcedure": "PPRN-Mvt"},
                ]
            },
            "gaspar/tri": rows({"libelle_tri": "Angers - Authion - Saumur"}),
            "ssp/casias": rows(
                {
                    "adresse": "loin",
                    "statut": "En arrêt",
                    "geom": {"coordinates": [-0.555, 47.477]},
                },
                {
                    "adresse": "4 rue du Canal",
                    "statut": "En arrêt",
                    "geom": {"coordinates": [-0.5515, 47.4742]},
                },
                results=30,
            ),
            "cavites": rows(
                {"type": "carrière", "nom": "Ardoisière", "longitude": -0.551, "latitude": 47.475}
            ),
            "mvt": rows(results=0),
        }
    )
    result = await GeorisquesProvider(http).fetch(CTX)  # type: ignore[arg-type]
    data = result.data

    assert result.missing == ()
    assert data["catastrophes_naturelles"]["par_type"] == [
        {"type": "Inondations", "nb_arretes": 2, "dernier": 2021},
        {"type": "Sécheresse", "nb_arretes": 1, "dernier": 2018},
    ]
    assert [plan["type"] for plan in data["plans_prevention"]] == ["PPRN-I", "PPRN-Mvt"]
    assert data["tri"] == ["Angers - Authion - Saumur"]
    sites = data["anciens_sites_industriels"]
    assert sites["nb_sites"] == 30
    assert sites["plus_proches"][0]["adresse"] == "4 rue du Canal"
    assert sites["plus_proches"][0]["distance_m"] < 50
    assert data["cavites"]["plus_proche"]["nom"] == "Ardoisière"
    assert data["mouvements_terrain"] == {"rayon_m": 500, "nb_evenements": 0}

    synthesis = build_synthesis({"georisques": SourceResult(status="ok", data=data)})
    # Les constats propres à l'adresse passent devant ceux de la commune (radon, inondation).
    assert [item.titre for item in synthesis.alertes] == [
        "Cavité souterraine à 102 m",
        "Ancien site industriel à 35 m",
        "Radon : potentiel maximal",
    ]


def test_heritage_perimeter_and_building_label_feed_the_synthesis() -> None:
    building = SourceResult(
        status="ok",
        data={"monument_historique": {"dans_perimetre": True}, "dpe": {"classe": "B"}},
    )
    synthesis = build_synthesis({"batiment": building})
    assert [item.titre for item in synthesis.alertes] == ["Abords d'un monument historique"]
    assert [item.titre for item in synthesis.points_forts] == ["Bâtiment classé B"]


def rent(value: float) -> dict[str, Any]:
    return {"data": [{"loypredm2": value, "nbobs_com": 100, "TYPPRED": "commune"}]}


async def test_rents_are_detailed_by_dwelling_type() -> None:
    http = FakeHttp(
        {
            "principal": rent(14.6),
            "petits": rent(16.57),
            "grands": rent(12.1),
            "maisons": SourceError("timeout"),
        }
    )
    provider = RentsProvider(
        http,  # type: ignore[arg-type]
        resource_id="principal",
        millesime=2025,
        typology_resources={"t1_t2": "petits", "t3_plus": "grands", "maison": "maisons"},
    )
    result = await provider.fetch(CTX)
    assert result.data["loyer_m2_charges_comprises"] == 14.6
    assert result.data["par_typologie"] == {
        "t1_t2": {"loyer_m2_charges_comprises": 16.57, "nb_observations": 100},
        "t3_plus": {"loyer_m2_charges_comprises": 12.1, "nb_observations": 100},
    }
    assert result.missing == ("maison",)


class LocalRents:
    def __init__(self, rents: dict[str, dict[str, Any]]) -> None:
        self.rents = rents

    async def commune_rents(self, code: str) -> dict[str, dict[str, Any]]:
        return self.rents


async def test_rents_are_read_locally_before_any_online_call() -> None:
    row = {"borne_basse": 11.2, "borne_haute": 18.9, "niveau_prediction": "commune"}
    local = LocalRents(
        {
            "appartement": {**row, "loyer_m2": 14.5737, "nb_observations": 812, "millesime": 2025},
            "maison": {**row, "loyer_m2": 11.04, "nb_observations": 90, "millesime": 2025},
        }
    )
    http = FakeHttp({})
    provider = RentsProvider(http, resource_id="principal", millesime=2025, repository=local)  # type: ignore[arg-type]
    data = (await provider.fetch(CTX)).data
    assert data["loyer_m2_charges_comprises"] == 14.57
    assert data["intervalle_prediction"] == [11.2, 18.9]
    assert data["par_typologie"] == {
        "maison": {
            "loyer_m2_charges_comprises": 11.04,
            "nb_observations": 90,
            "niveau_prediction": "commune",
        }
    }

    # Référentiel vide : l'API en ligne reprend la main.
    fallback = RentsProvider(
        FakeHttp({"principal": rent(14.6)}),  # type: ignore[arg-type]
        resource_id="principal",
        millesime=2025,
        repository=LocalRents({}),  # type: ignore[arg-type]
    )
    assert (await fallback.fetch(CTX)).data["loyer_m2_charges_comprises"] == 14.6


class NoHousing:
    async def iris_housing(self, code_iris: str) -> None:
        return None

    async def tense_zone(self, codes: list[str]) -> None:
        return None


async def test_abc_zone_reads_the_dated_column_and_flags_tense_markets() -> None:
    column = "Zonage ABC en vigueur depuis le 26 juin 2026"
    http = FakeHttp(
        {
            "wfs": {"features": []},
            "geo.api.gouv.fr": [],
            "tabular-api": {"data": [{"CODGEO": "49007", column: "B1"}]},
        }
    )
    provider = RentalMarketProvider(http, NoHousing(), abc_resource_id="abc")  # type: ignore[arg-type]
    data = (await provider.fetch(CTX)).data
    assert data["zonage_abc"] == {"zone": "B1", "tendu": True}
