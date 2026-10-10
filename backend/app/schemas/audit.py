"""Contrats d'entrée/sortie de l'API d'audit."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Identifiants BAN : commune ("75101"), voie ("75101_8909"), numéro ("75101_8909_00008_bis").
_BAN_ID_PATTERN = r"^$|^[0-9][0-9AB][0-9]{3}(_[0-9A-Za-z]{1,12}){0,3}$"

SourceStatus = Literal["ok", "partial", "empty", "error", "timeout", "unavailable"]
FAILED_STATUSES: frozenset[SourceStatus] = frozenset({"partial", "error", "timeout", "unavailable"})


class AuditQuery(BaseModel):
    """Paramètres de recherche, issus de la sélection d'une adresse BAN côté client."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    lat: float = Field(ge=-90, le=90, description="Latitude WGS84")
    lon: float = Field(ge=-180, le=180, description="Longitude WGS84")
    ban_id: str = Field(default="", max_length=64, pattern=_BAN_ID_PATTERN)

    @field_validator("lat", "lon")
    @classmethod
    def _round_coordinate(cls, value: float) -> float:
        # 6 décimales (~11 cm) : précision de la BAN, et clé de cache stable.
        return round(value, 6)


class StreetInfo(BaseModel):
    """Voie analysée en mode « rue »."""

    id: str
    nom: str
    nb_numeros: int
    longueur_m: int
    # [lon, lat] de numéros répartis le long de la voie, pour la carte.
    points: list[tuple[float, float]]


class Location(BaseModel):
    """Localisation résolue côté serveur (jamais reprise telle quelle du client)."""

    lat: float
    lon: float
    label: str
    citycode: str
    postcode: str | None = None
    city: str | None = None
    region: str | None = None
    ban_id: str = ""
    # Identifiant BAN de l'adresse la plus proche du point, résolu par le serveur. À la
    # différence de `ban_id` (repris de la requête), il peut fonder un droit d'accès.
    adresse_id: str | None = None
    # Voie et numéro de cette adresse, pour les référentiels décrits par tronçon de voie.
    voie: str | None = None
    numero: int | None = None
    # Présent quand l'audit porte sur une voie entière plutôt que sur un point.
    rue: StreetInfo | None = None
    # Vrai quand une voie était demandée mais n'a pas pu être vérifiée (service d'adresses
    # indisponible) : l'analyse porte alors sur le point, et le rapport n'est pas conservé.
    voie_non_verifiee: bool = False


class SourceResult(BaseModel):
    """Résultat normalisé d'une source de données."""

    status: SourceStatus
    data: dict[str, Any] | None = None
    # Sous-parties de la source restées sans réponse (statut "partial").
    missing: list[str] = Field(default_factory=list)
    error: str | None = None
    duration_ms: int = 0
    # Date d'interrogation de la source : chaque source a sa propre durée de validité en cache.
    fetched_at: datetime | None = None


class Finding(BaseModel):
    """Constat de la synthèse ; en version restreinte, seul le thème reste lisible."""

    theme: str
    titre: str
    detail: str


class Synthesis(BaseModel):
    alertes: list[Finding] = []
    points_forts: list[Finding] = []


class ReportMeta(BaseModel):
    generated_at: datetime
    cached: bool = False
    # Vrai si au moins une source n'a pas (entièrement) répondu ; le rapport reste exploitable.
    is_partial: bool
    # Noms des sources concernées, pour que l'interface dise précisément ce qui manque.
    failed_sources: list[str] = Field(default_factory=list)
    # "teaser" : valeurs sensibles remplacées par "***LOCKED***" ; "full" : rapport complet.
    access: Literal["full", "teaser", "demo"] = "full"
    report_version: int
    duration_ms: int
    # Alertes et points forts les plus marquants ; absent des rapports antérieurs à la v7.
    synthese: Synthesis | None = None


class AuditReport(BaseModel):
    """Réponse consolidée : une entrée par source, toujours présente."""

    location: Location
    sources: dict[str, SourceResult]
    meta: ReportMeta
