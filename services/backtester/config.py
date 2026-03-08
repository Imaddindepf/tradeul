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

    # Redis (for cached splits + scanner enrichment)
    redis_url: str = "redis://redis:6379"

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
