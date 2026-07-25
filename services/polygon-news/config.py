"""
Polygon News Service Configuration
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    """Configuration settings for Polygon News service"""

    # Polygon API
    polygon_api_key: str = Field(..., description="Polygon.io API key")
    polygon_base_url: str = Field(
        default="https://api.polygon.io",
        description="Polygon API base URL"
    )

    # Redis
    redis_host: str = Field(default="redis", description="Redis host")
    redis_port: int = Field(default=6379, description="Redis port")
    redis_password: Optional[str] = Field(default=None, description="Redis password")

    # Service config
    service_port: int = Field(default=8018, description="Service port")
    poll_interval_seconds: int = Field(default=60, description="News poll interval")
    max_articles_per_poll: int = Field(default=50, description="Max articles fetched per poll")

    # Logging
    log_level: str = Field(default="INFO", description="Log level")

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
