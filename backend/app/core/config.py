"""Typed application settings (techspec §4). The only place configuration is read."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    app_name: str = "GeoGuard-EO"
    environment: Literal["dev", "test", "prod"] = "dev"
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://postgres:CHANGE_ME@localhost:5432/geoguard_db"
    test_database_url: str = "postgresql+psycopg://postgres:CHANGE_ME@localhost:5432/geoguard_test"
    # Optional schema for the *test* suite when TEST_DATABASE_URL is the same database as
    # DATABASE_URL (Supabase free tier: one database per project). Ignored when empty.
    test_database_schema: str = "geoguard_test"
    jwt_secret: SecretStr = SecretStr("CHANGE_ME")
    jwt_expire_minutes: int = Field(default=480, ge=5, le=24 * 60)
    data_dir: Path = Path("./data")

    imagery_provider: Literal["stac_public", "local_folder"] = "stac_public"
    stac_api_url: str = ""
    cloud_cover_max: int = Field(default=30, ge=0, le=100)

    alert_provider: Literal["console", "telegram", "email"] = "console"
    telegram_bot_token: SecretStr = SecretStr("")
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_from: str = ""

    basemap_url: str = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
    basemap_attribution: str = "© OpenStreetMap contributors"

    scheduler_enabled: bool = True
    first_admin_email: str = ""
    first_admin_password: SecretStr = SecretStr("CHANGE_ME")

    cors_origins: list[str] = ["http://localhost:5173"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [o.strip() for o in value.split(",") if o.strip()]
        return value

    @property
    def jwt_secret_is_placeholder(self) -> bool:
        return self.jwt_secret.get_secret_value() in {"", "CHANGE_ME"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
