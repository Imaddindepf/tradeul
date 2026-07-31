"""
News Persister Service Configuration

Consume el Redis Stream `stream:benzinga:news` (feed unificado: benzinga/OOC +
fmp + polygon) y lo persiste en la TimescaleDB principal (hypertable
news_articles). Expone además la búsqueda full-text del histórico.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    # ── Redis (origen) ──────────────────────────────────────────────────
    redis_host: str = Field(default="redis", description="Redis host")
    redis_port: int = Field(default=6379, description="Redis port")
    redis_password: Optional[str] = Field(default=None, description="Redis password")
    redis_stream_key: str = Field(default="stream:benzinga:news", description="Stream unificado de noticias")

    # Consumer group: entrega garantizada y reanudación tras reinicio
    consumer_group: str = Field(default="news_persister", description="Redis consumer group")
    consumer_name: str = Field(default="persister_1", description="Nombre de este consumidor")

    # ── TimescaleDB principal (destino) ─────────────────────────────────
    postgres_host: str = Field(default="timescaledb", description="Host de TimescaleDB")
    postgres_port: int = Field(default=5432, description="Puerto")
    postgres_db: str = Field(default="tradeul", description="Base de datos")
    postgres_user: str = Field(default="tradeul_user", description="Usuario")
    postgres_password: str = Field(default="", description="Password")
    db_min_pool: int = Field(default=1, description="Pool mínimo de conexiones")
    db_max_pool: int = Field(default=6, description="Pool máximo de conexiones")

    # ── Batching ────────────────────────────────────────────────────────
    batch_size: int = Field(default=100, description="Máx items por lote de insert")
    block_ms: int = Field(default=2000, description="Bloqueo de XREADGROUP en ms")

    # ── Servicio ────────────────────────────────────────────────────────
    service_port: int = Field(default=8073, description="Puerto del servicio")
    log_level: str = Field(default="INFO", description="Log level")

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
