from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    database_url: str = "postgresql+asyncpg://underlock:underlock@localhost:5433/underlock"
    redis_url: str = "redis://localhost:6380/0"
    jwt_secret_key: str = ""
    jwt_access_token_minutes: int = 60
    api_cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    log_level: str = "INFO"
    worker_batch_size: int = 100
    worker_block_ms: int = 1000
    worker_recovery_interval_ms: int = 30000
    worker_min_idle_ms: int = 60000
    worker_max_deliveries: int = 5

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()
