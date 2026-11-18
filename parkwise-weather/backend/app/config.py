"""
Application settings, read from environment variables (or a .env file).

Why pydantic-settings?
    It validates config the same way Pydantic validates API input, so a typo'd
    or missing setting fails loudly at startup instead of halfway through a
    request. Secrets (NPS key, database password) never live in code.

Lookup order: real environment variables  >  backend/.env  >  project-root .env  >  defaults below.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]       # .../parkwise-weather/backend
PROJECT_DIR = BACKEND_DIR.parent                         # .../parkwise-weather
DEFAULT_SQLITE_PATH = PROJECT_DIR / "data" / "parkwise.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Later files win, so backend/.env overrides the project-root .env
        env_file=(PROJECT_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # SQLite for local development; set DATABASE_URL to a Neon/PostgreSQL URL in production.
    database_url: str = f"sqlite:///{DEFAULT_SQLITE_PATH}"

    # Used from Phase 2 by the park ETL script. Server-side only — never sent to the browser.
    nps_api_key: str = ""

    # Where scripts.train_models saves the climate model and its metrics, and the API reads them.
    model_dir: Path = PROJECT_DIR / "trained_models"

    # Comma-separated list of frontend origins allowed to call this API.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Optional regex for extra allowed origins, e.g. Vercel preview deployments:
    #   ^https://parkwise-weather(-[a-z0-9-]+)?\.vercel\.app$
    cors_origin_regex: str = ""

    # "development" shows error details; "production" hides internals.
    environment: str = "development"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    """Settings are read once and cached for the life of the process."""
    return Settings()
