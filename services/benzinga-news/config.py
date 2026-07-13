"""
Benzinga News Service Configuration
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    """Configuration settings for Benzinga News service"""
    
    # Fuente de noticias: OpenOutcrier (feed Benzinga vía canal `bz`)
    ooc_base_url: str = Field(default="https://openoutcrier.com", description="OpenOutcrier base URL")
    ooc_session_hash: str = Field(..., description="Cookie `hash` de la sesión Pro de OpenOutcrier")
    ooc_endpoint: str = Field(default="/load", description="Endpoint del feed OpenOutcrier")

    # Polygon API — ya NO se usa para noticias. Solo lo usa el catalyst engine
    # como fallback de precio de mercado (dato de mercado, no de Benzinga).
    polygon_api_key: Optional[str] = Field(default=None, description="Polygon.io API key (solo precios, opcional)")
    
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

