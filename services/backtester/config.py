"""Backtester Service Configuration"""
from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "backtester"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8060

    # Polygon
    polygon_api_key: str = ""
    polygon_data_dir: Path = Path("/data/polygon")
    day_aggs_subdir: str = "day_aggs"
    minute_aggs_dir: Path = Path("/data/backtester/minute_aggs_adjusted")

    # Redis (queue + job storage)
    redis_url: str = "redis://redis:6379"
    # Redis DB 0 — where live snapshots (snapshot:enriched:*) live
    redis_snapshot_url: str = ""
    jobs_queue_name: str = "backtester:jobs"
    job_result_ttl_seconds: int = 7 * 24 * 3600  # 7 days
    max_concurrent_jobs_per_user: int = 2
    max_jobs_per_day_per_user: int = 50  # 0 = sin límite diario

    # Defaults
    default_initial_capital: float = 100_000.0
    default_slippage_bps: float = 10.0
    default_risk_free_rate: float = 0.05
    max_execution_seconds: int = 120
    max_symbols_per_backtest: int = 2000

    # Splits cache
    splits_cache_dir: Path = Path("/data/polygon/splits_cache")
    splits_cache_ttl_hours: int = 24

    class Config:
        env_prefix = "BACKTESTER_"
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
