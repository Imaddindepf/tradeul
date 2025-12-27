"""
Screener Service Configuration
"""
from pydantic_settings import BaseSettings
from pathlib import Path
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings"""
    
    # Service
    service_name: str = "screener"
    debug: bool = False
    
    # Data paths
    data_path: Path = Path("/data/polygon")
    daily_data_pattern: str = "day_aggs/*.csv.gz"
    
    # DuckDB
    duckdb_memory_limit: str = "4GB"
    duckdb_threads: int = 4
    
    # Cache
    redis_url: str = "redis://localhost:6379"
    cache_ttl_seconds: int = 60
    cache_enabled: bool = True
    
    # API
    api_prefix: str = "/api/v1/screener"
    max_results: int = 500
    default_limit: int = 50
    
    # Indicators
    default_lookback_days: int = 252  # 1 year of trading days
    
    class Config:
        env_prefix = "SCREENER_"
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

