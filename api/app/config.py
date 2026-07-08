"""
Kubera — Pydantic Settings config.
All values read from environment / .env file.
Never import secrets directly — always use `get_settings()`.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env.test", ".env"),  # .env.test takes precedence when present
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # ignore POSTGRES_* and other docker-compose vars
    )

    # ── Database ──────────────────────────────────────────────────────────
    database_url: str
    sync_database_url: str = ""  # populated at runtime if not set

    # ── Redis / Celery ────────────────────────────────────────────────────
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/1"

    # ── JWT ───────────────────────────────────────────────────────────────
    secret_key: str
    refresh_secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # ── Internal API key ──────────────────────────────────────────────────
    internal_api_key: str

    # ── App ───────────────────────────────────────────────────────────────
    app_env: str = "development"

    # ── DocVault ──────────────────────────────────────────────────────────
    vault_kek: str
    vault_storage_path: str = "/data/vault"
    backup_destination_path: str = "/data/backup"


@lru_cache
def get_settings() -> Settings:
    return Settings()
