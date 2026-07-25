"""
FMP News Service Configuration
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    """Configuration settings for FMP News service"""

    # FMP API
    fmp_api_key: str = Field(..., description="Financial Modeling Prep API key")
    fmp_base_url: str = Field(
        default="https://financialmodelingprep.com/stable",
        description="FMP stable API base URL"
    )

    # Redis
    redis_host: str = Field(default="redis", description="Redis host")
    redis_port: int = Field(default=6379, description="Redis port")
    redis_password: Optional[str] = Field(default=None, description="Redis password")

    # Service config
    service_port: int = Field(default=8017, description="Service port")
    max_articles_per_poll: int = Field(default=50, description="Max articles fetched per poll")

    # Intervalos de polling por feed (segundos). Escalonados para no quemar
    # el rate limit del plan FMP (~5 feeds => <15 req/min en total).
    poll_interval_stock: int = Field(default=20, description="Stock news poll interval")
    poll_interval_press: int = Field(default=20, description="Press releases poll interval")
    poll_interval_general: int = Field(default=60, description="General news poll interval")
    poll_interval_forex: int = Field(default=120, description="Forex news poll interval")
    poll_interval_articles: int = Field(default=300, description="FMP articles poll interval")

    # Logging
    log_level: str = Field(default="INFO", description="Log level")

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
