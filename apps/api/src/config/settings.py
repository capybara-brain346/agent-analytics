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
    max_decompressed_bytes: int = 20 * 1024**3  # One file larger than this after gunzip fails
    ingest_rate_per_minute: int = 120  # Requests for each site (1.16)
    ingest_bytes_per_day: int = 20 * 1024 * 1024 * 1024  # Byte quota for each site (1.16)

    # Bucket reader (1.17)
    bucket_reader_enabled: bool = False
    bucket_reader_interval_seconds: int = 60
    bucket_reader_prefix: str = ""

    # Worker and pipeline
    tick_seconds: int = 60
    work_limit_bytes: int = 200 * 1024 * 1024
    work_limit_lines: int = 2_000_000
    health_stale_minutes: int = 15
    stale_run_minutes: int = 30  # A running run older than this with a free lock = crashed
    failed_runs_alert: int = 3

    # Import and alerts
    raw_retention_days: int = 7
    events_retention_days: int = 30
    no_data_alert_minutes: int = 60  # Default; a site file can override

    # Pair
    pair_window_seconds: int = 5  # +/- N s around the CDN time
    pair_wait_minutes: int = 10  # An unpaired event waits this long, then stays single
    # While the other source still has queued files, rows keep waiting, up to this limit
    pair_hard_limit_hours: int = 24

    # Verify
    rdns_ttl_hours: int = 24
    unverified_retry_minutes: int = 60  # A DNS error is retried after this time, not after 24 h
    dns_timeout_seconds: float = 2.0
    ip_list_dir: Path = API_ROOT / "config" / "registry" / "ip-lists"

    # Activity reconstruction
    session_gap_minutes: int = 30
    agent_session_gap_minutes: int = 2
    delivery_margin_minutes: int = 10
    retry_window_seconds: int = 60
    loop_repeat_count: int = 5

    # Recommendations
    recommendation_window: str = "6h"
    p1_min_key_pages: int = 3
    p2_min_blocks: int = 5
    p3_min_sessions: int = 3
    frequency_mid_min: int = 5  # sessions < 5 = 1; 5..50 = 2; > 50 = 3
    frequency_high_over: int = 50
    p4_bytes_ratio: float = 0.3  # AI median bytes below this share of the browser median
    openrouter_api_key: str | None = None  # None = template text only
    llm_base_url: str = "https://openrouter.ai/api/v1"  # OpenRouter or a compatible gateway
    llm_model: str | None = None  # OpenRouter model ID; None = template text only
    llm_prompt_version: str = "1"
    llm_timeout_seconds: float = 30.0

    # Dashboard API (/api/*): Bearer token. None = open (dev only; a warning is logged)
    api_token: str | None = None

    # Offline mode (docs/modules/deployment/README.md)
    offline: bool = False

    # YAML data: CDN field maps, bot registry, site config
    config_dir: Path = API_ROOT / "config"


@lru_cache
def get_settings() -> Settings:
    return Settings()
