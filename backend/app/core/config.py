"""Configuration centralisée de l'application (Pydantic Settings v2).

Toutes les valeurs proviennent de variables d'environnement (.env).
Aucune valeur métier n'est codée en dur ici : les règles métier vivent
en base (tables business_rules / settings), cf. PRINCIPE FONDATEUR #2.
"""

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Paramètres applicatifs chargés depuis l'environnement."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Application ---------------------------------------------------
    APP_ENV: str = "development"  # "development" | "production"
    APP_NAME: str = "Kimia"
    APP_URL: str = "http://localhost:8000"
    DEBUG: bool = False

    # --- Base de données / cache ---------------------------------------
    DATABASE_URL: str = "postgresql+asyncpg://kimia:kimia@localhost:5432/kimia"
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- Sécurité / JWT -------------------------------------------------
    SECRET_KEY: str = "change-me-in-production"
    JWT_SECRET: str = "change-me-jwt-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # --- Intégrations externes (optionnelles) ---------------------------
    KIMIA_API_URL: Optional[str] = None
    KIMIA_API_KEY: Optional[str] = None
    ONESIGNAL_APP_ID: Optional[str] = None
    ONESIGNAL_KEY: Optional[str] = None
    SENTRY_DSN: Optional[str] = None

    # --- Divers ----------------------------------------------------------
    CORS_ORIGINS: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    STORAGE_PATH: str = "./data/media"
    PASSWORD_MIN_LENGTH: int = 8

    @property
    def is_production(self) -> bool:
        """Vrai si l'app tourne en production."""
        return self.APP_ENV == "production"


@lru_cache
def get_settings() -> Settings:
    """Retourne les paramètres (mis en cache)."""
    return Settings()


settings = get_settings()
