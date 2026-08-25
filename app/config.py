"""Application settings, loaded from environment variables or a local .env file."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Every field maps to an `APP_`-prefixed env var."""

    model_config = SettingsConfigDict(env_prefix="APP_", env_file=".env", extra="ignore")

    env: str = "local"
    log_level: str = "INFO"

    # Share of seats we expect to be in use on a given day; drives `meets_target`.
    target_utilization: float = 0.75

    # Days of seeded occupancy history the in-memory store starts with.
    seed_history_days: int = 14


@lru_cache
def get_settings() -> Settings:
    return Settings()
