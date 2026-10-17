"""Runtime settings. Read from environment variables (and `.env` in development)."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

API_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    log_level: str = "INFO"

    # Store (one PostgreSQL, decision S.1)
    database_url: str = (
        "postgresql://agent_analytics:agent_analytics@localhost:5432/agent_analytics"
    )
    db_pool_max_size: int = 10  # Cap to fit the database connection limit (7.10)

    # Inbox (S3-compatible storage, decision 1.19)
    s3_endpoint_url: str | None = None  # None = AWS S3
    s3_region: str = "us-east-1"
    s3_bucket: str = "agent-analytics-inbox"
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None

    # Ingest (decisions 1.15–1.17)
    ingest_max_bytes: int = 50 * 1024 * 1024
    upload_max_bytes: int = 2 * 1024 * 1024 * 1024
    ingest_chunk_bytes: int = 64 * 1024

    # Worker and pipeline (Flow 7)
    tick_seconds: int = 60
    work_limit_bytes: int = 200 * 1024 * 1024
    work_limit_lines: int = 2_000_000
    health_stale_minutes: int = 15
    failed_runs_alert: int = 3

    # Import and alerts (Flow 1)
    raw_retention_days: int = 7
    no_data_alert_minutes: int = 60

    # Recommendations (Flow 5)
    recommendation_window: str = "6h"
    llm_api_key: str | None = None  # None = template text only

    # Offline mode (on-prem.md, PROPOSED)
    offline: bool = False

    # YAML data: CDN field maps, bot registry, site config
    config_dir: Path = API_ROOT / "config"


@lru_cache
def get_settings() -> Settings:
    return Settings()
