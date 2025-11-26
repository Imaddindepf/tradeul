"""
Benzinga News Service Configuration
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    """Configuration settings for Benzinga News service"""
    
    # Polygon API (Benzinga News is accessed through Polygon)
    polygon_api_key: str = Field(..., description="Polygon.io API key")
    
    # Redis
    redis_host: str = Field(default="redis", description="Redis host")
    redis_port: int = Field(default=6379, description="Redis port")
    redis_password: Optional[str] = Field(default=None, description="Redis password")
    
    # Service config
    service_port: int = Field(default=8015, description="Service port")
    poll_interval_seconds: int = Field(default=5, description="Polling interval for news")
    max_articles_per_poll: int = Field(default=50, description="Max articles per poll")
    
    # Cache TTLs
    cache_ttl_latest: int = Field(default=3600, description="TTL for latest news cache")
    cache_ttl_by_ticker: int = Field(default=86400, description="TTL for news by ticker cache")
    
    # Logging
    log_level: str = Field(default="INFO", description="Log level")
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()

