"""
Benzinga Earnings Service Configuration

Real-time earnings data streaming from Polygon/Benzinga API.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    """Configuration settings for Benzinga Earnings service"""
    
    # Polygon API (Benzinga Earnings is accessed through Polygon)
    polygon_api_key: str = Field(..., description="Polygon.io API key")
    
    # Redis
    redis_host: str = Field(default="redis", description="Redis host")
    redis_port: int = Field(default=6379, description="Redis port")
    redis_password: Optional[str] = Field(default=None, description="Redis password")
    
    # TimescaleDB (for persistent storage)
    timescale_host: str = Field(default="timescaledb", description="TimescaleDB host")
    timescale_port: int = Field(default=5432, description="TimescaleDB port")
    timescale_user: str = Field(default="tradeul", description="TimescaleDB user")
    timescale_password: str = Field(default="tradeul", description="TimescaleDB password")
    timescale_database: str = Field(default="tradeul", description="TimescaleDB database")
    
    # Service config
    service_port: int = Field(default=8022, description="Service port")
    poll_interval_seconds: int = Field(default=30, description="Polling interval for earnings updates")
    full_sync_interval_minutes: int = Field(default=60, description="Full sync interval in minutes")
    
    # Cache config
    cache_size_latest: int = Field(default=500, description="Number of earnings to keep in latest cache")
    cache_size_by_date: int = Field(default=200, description="Number of earnings per date to cache")
    cache_ttl_seconds: int = Field(default=3600, description="Cache TTL in seconds")
    
    # API limits
    max_results_per_request: int = Field(default=1000, description="Max results per API request")
    lookback_days: int = Field(default=7, description="Days to look back for earnings")
    lookahead_days: int = Field(default=14, description="Days to look ahead for earnings")
    
    # Logging
    log_level: str = Field(default="INFO", description="Log level")
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
