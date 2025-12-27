"""
Polygon Data Service Configuration
"""
from pydantic_settings import BaseSettings
from pathlib import Path
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings"""
    
    # Service
    service_name: str = "polygon-data"
    debug: bool = False
    
    # Polygon S3
    polygon_s3_endpoint: str = "https://files.polygon.io"
    polygon_s3_bucket: str = "flatfiles"
    polygon_s3_access_key: str = ""
    polygon_s3_secret_key: str = ""
    
    # Data paths
    data_dir: Path = Path("/data/polygon")
    minute_aggs_dir: str = "minute_aggs"
    day_aggs_dir: str = "day_aggs"
    
    # Download settings
    default_lookback_days: int = 365  # 1 year
    max_parallel_downloads: int = 4
    
    # Scheduler
    daily_update_hour: int = 6  # UTC - after market close
    daily_update_minute: int = 0
    
    class Config:
        env_prefix = "POLYGON_DATA_"
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

