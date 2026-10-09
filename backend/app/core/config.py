"""Configuration de l'application, lue exclusivement depuis l'environnement."""

from functools import lru_cache
from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "production"
    database_url: SecretStr
    supabase_jwt_secret: SecretStr
    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)

    # Appels sortants
    # Les API publiques (BAN, Géorisques, IGN) répondent parfois en plusieurs secondes :
    # 3 s provoquait des rapports partiels à répétition. Plage visée : 8 à 10 s.
    http_timeout_s: float = Field(default=9.0, ge=1, le=10)
    http_user_agent: str = "AuditImmobilier/0.1"
    # Garde-fou global par source : une source peut enchaîner deux appels (DVF), il doit
    # donc dépasser deux fois le délai par appel.
    provider_deadline_s: float = Field(default=20.0, gt=0, le=60)
    breaker_failure_threshold: int = Field(default=3, ge=1)
    breaker_reset_after_s: float = Field(default=30.0, gt=0)

    # Cache des rapports
    report_version: int = Field(default=13, ge=1, le=32767)
    cache_ttl_hours: int = Field(default=168, ge=1)
    cache_partial_ttl_minutes: int = Field(default=15, ge=1)
    air_quality_ttl_hours: int = Field(default=12, ge=1)

    # Limitation de débit (par adresse IP)
    rate_limit_requests: int = Field(default=30, ge=1)
    rate_limit_window_s: float = Field(default=60.0, gt=0)

    # Paiement Stripe. Sans clé, les routes de paiement répondent 503 et rien n'est facturé.
    stripe_secret_key: SecretStr | None = None
    stripe_webhook_secret: SecretStr | None = None
    stripe_api_url: str = "https://api.stripe.com"
    # Taux de TVA Stripe (txr_...) appliqué en sus du prix de l'abonnement Pro, affiché HT.
    stripe_pro_tax_rate_id: str | None = None
    # Adresse du frontend : seules destinations de retour possibles après paiement.
    site_url: str = "http://localhost:5173"

    # Suppression de compte : appel d'administration au service d'authentification, sur le
    # réseau interne. Sans clé, la suppression en libre-service est fermée.
    supabase_service_role_key: SecretStr | None = None
    auth_internal_url: str = "http://auth:9999"
    # Destinataire des alertes d'exploitation (sauvegarde ou test de fumée en échec).
    alert_email: str | None = None

    # Envoi d'e-mails (reçus de paiement). Sans serveur configuré, aucun message n'est envoyé.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_pass: SecretStr | None = None
    smtp_admin_email: str | None = None
    smtp_sender_name: str = "Audit Immobilier"

    # OpenRouteService : temps de marche réels si la clé est fournie, estimation sinon.
    ors_api_key: SecretStr | None = None

    # « Carte des loyers » : ressource data.gouv du dernier millésime
    loyers_resource_id: str = "55b34088-0964-415f-9df7-d87dd98a09be"
    loyers_millesime: int = 2025
    # Même millésime, par typologie : appartements de 1-2 pièces, de 3 pièces et plus, maisons.
    loyers_t1_t2_resource_id: str = "14a1fe11-b2d1-49b3-9f6b-83d12df9482c"
    loyers_t3_plus_resource_id: str = "5e3b28a4-cf56-43a3-ae79-43cceeb27f8c"
    loyers_maison_resource_id: str = "129f764d-b613-44e4-952c-5ff50a8c9b73"
    # Zonage ABC des communes (ministère chargé du logement), liste en vigueur.
    zonage_abc_resource_id: str = "13f7282b-8a25-43ab-9713-8bb4e476df55"

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
