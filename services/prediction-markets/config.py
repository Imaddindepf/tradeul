"""
Prediction Markets Service Configuration
"""

from typing import Optional, List, Set
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    """Service configuration loaded from environment variables"""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow"
    )
    
    # Service
    service_name: str = Field(default="prediction-markets")
    service_port: int = Field(default=8021)
    log_level: str = Field(default="INFO")
    
    # Database (PostgreSQL/TimescaleDB)
    postgres_host: str = Field(default="timescaledb")
    postgres_port: int = Field(default=5432)
    postgres_user: str = Field(default="tradeul_user")
    postgres_password: Optional[str] = Field(default=None)
    postgres_db: str = Field(default="tradeul")
    
    # Redis
    redis_host: str = Field(default="redis")
    redis_port: int = Field(default=6379)
    redis_password: Optional[str] = Field(default=None)
    
    # Cache TTL (seconds)
    events_cache_ttl: int = Field(default=300, description="Events cache TTL (5 min)")
    price_history_cache_ttl: int = Field(default=600, description="Price history cache TTL (10 min)")
    tags_cache_ttl: int = Field(default=3600, description="Tags cache TTL (1 hour)")
    
    # Polymarket API
    polymarket_gamma_url: str = Field(default="https://gamma-api.polymarket.com")
    polymarket_clob_url: str = Field(default="https://clob.polymarket.com")
    polymarket_data_url: str = Field(default="https://data-api.polymarket.com")
    polymarket_timeout: int = Field(default=30)
    
    # Fetch limits
    max_events_fetch: int = Field(default=200, description="Max events to fetch per request")
    max_markets_for_history: int = Field(default=100, description="Max markets to fetch price history")
    
    # Polling interval
    refresh_interval_seconds: int = Field(default=300, description="Background refresh interval")
    
    def get_redis_url(self) -> str:
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/0"
        return f"redis://{self.redis_host}:{self.redis_port}/0"
    
    @property
    def database_url(self) -> Optional[str]:
        """Get PostgreSQL connection URL"""
        if not self.postgres_password:
            return None
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
