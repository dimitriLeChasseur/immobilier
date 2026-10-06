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
    report_version: int = Field(default=5, ge=1, le=32767)
    cache_ttl_hours: int = Field(default=168, ge=1)
    cache_partial_ttl_minutes: int = Field(default=15, ge=1)

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

    # OpenRouteService : temps de marche réels si la clé est fournie, estimation sinon.
    ors_api_key: SecretStr | None = None

    # « Carte des loyers » : ressource data.gouv du dernier millésime
    loyers_resource_id: str = "55b34088-0964-415f-9df7-d87dd98a09be"
    loyers_millesime: int = 2025

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
