"""
Configuración del servicio SEC Filings
"""
import os
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configuración del servicio"""
    
    # SEC API
    SEC_API_KEY: str = os.getenv("SEC_API_KEY", "")
    SEC_STREAM_URL: str = "wss://stream.sec-api.io"
    SEC_QUERY_URL: str = "https://api.sec-api.io"
    
    # Database
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "timescale")
    POSTGRES_PORT: int = int(os.getenv("POSTGRES_PORT", "5432"))
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "tradeul_user")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "tradeul")
    
    # Redis
    REDIS_HOST: str = os.getenv("REDIS_HOST", "redis")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_PASSWORD: Optional[str] = os.getenv("REDIS_PASSWORD")
    
    # Service
    SERVICE_NAME: str = "sec-filings"
    SERVICE_PORT: int = 8012
    LOG_LEVEL: str = "INFO"
    
    # Stream settings
    STREAM_ENABLED: bool = True
    STREAM_RECONNECT_DELAY: int = 5  # segundos
    STREAM_PING_TIMEOUT: int = 30  # segundos
    
    # Query settings
    BACKFILL_ENABLED: bool = True
    BACKFILL_BATCH_SIZE: int = 50
    BACKFILL_DAYS_BACK: int = 30  # días hacia atrás para backfill inicial
    
    @property
    def database_url(self) -> str:
        """URL de conexión a PostgreSQL"""
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )
    
    @property
    def sec_stream_ws_url(self) -> str:
        """URL del WebSocket de SEC Stream API"""
        return f"{self.SEC_STREAM_URL}?apiKey={self.SEC_API_KEY}"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

