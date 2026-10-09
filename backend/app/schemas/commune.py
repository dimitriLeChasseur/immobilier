"""Fiche publique d'une commune : chiffres communaux uniquement, aucune donnée à l'adresse."""

from pydantic import BaseModel


class Benchmark(BaseModel):
    """Valeur de la commune et repères du département et de la France."""

    valeur: float
    departement: float | None = None
    national: float | None = None


class CommuneTax(BaseModel):
    annee: int
    taux_tfb_total: Benchmark
    taux_teom: float | None = None


class CommuneCrime(BaseModel):
    annee: int
    # Cambriolages de logement pour 1 000 habitants.
    cambriolages: Benchmark
    # Même taux l'année précédente, pour la tendance.
    annee_precedente: float | None = None


class SchoolLevel(BaseModel):
    nb: int
    ips_moyen: float
    moyenne_nationale: float | None = None


class CommuneHousing(BaseModel):
    annee: int
    logements: int
    part_locataires_pct: float | None = None
    part_proprietaires_pct: float | None = None
    part_vacants_pct: float | None = None


class CommuneProfile(BaseModel):
    code: str
    nom: str
    slug: str
    departement_code: str
    departement_nom: str
    population: int | None = None
    codes_postaux: list[str] = []
    # [lon, lat] du centre de la commune, pour lancer un audit depuis la fiche.
    centre: tuple[float, float] | None = None
    taxe_fonciere: CommuneTax | None = None
    delinquance: CommuneCrime | None = None
    ecoles: dict[str, SchoolLevel] = {}
    part_fibre_pct: float | None = None
    # Loyers d'annonce au m², charges comprises, par type de bien (carte des loyers).
    loyers: dict[str, float] = {}
    # Paris, Lyon, Marseille : loyers extrêmes des arrondissements, par type de bien.
    loyers_fourchette: dict[str, tuple[float, float]] = {}
    # Échelle de l'estimation par type de bien : « commune », « EPCI » ou « maille » (groupe
    # de communes voisines), quand les annonces de la commune seule ne suffisent pas.
    loyers_niveau: dict[str, str] = {}
    loyers_millesime: int | None = None
    logement: CommuneHousing | None = None
