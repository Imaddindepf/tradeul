"""
OpenUL Persister Service Configuration

Consume el Redis Stream `openul:news` y persiste cada item en una BD
Postgres separada (no la TimescaleDB principal).
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    # ── Redis (origen) ──────────────────────────────────────────────────
    redis_host: str = Field(default="redis", description="Redis host")
    redis_port: int = Field(default=6379, description="Redis port")
    redis_password: Optional[str] = Field(default=None, description="Redis password")
    redis_stream_key: str = Field(default="openul:news", description="Stream a consumir")

    # Consumer group: garantiza entrega y reanudacion tras reinicio
    consumer_group: str = Field(default="openul_persister", description="Redis consumer group")
    consumer_name: str = Field(default="persister_1", description="Nombre de este consumidor")

    # ── Postgres separado (destino) ─────────────────────────────────────
    db_host: str = Field(default="127.0.0.1", description="Host de la BD de news")
    db_port: int = Field(default=55433, description="Puerto de la BD de news")
    db_name: str = Field(default="openul", description="Nombre de la BD")
    db_user: str = Field(default="openul_admin", description="Usuario de la BD")
    db_password: str = Field(default="", description="Password de la BD")
    db_min_pool: int = Field(default=1, description="Pool minimo de conexiones")
    db_max_pool: int = Field(default=4, description="Pool maximo de conexiones")

    # ── Batching ────────────────────────────────────────────────────────
    batch_size: int = Field(default=100, description="Max items por lote de insert")
    batch_timeout_ms: int = Field(default=2000, description="Flush forzado tras N ms sin llenar el lote")
    block_ms: int = Field(default=2000, description="Bloqueo de XREADGROUP en ms")

    # ── Servicio ────────────────────────────────────────────────────────
    service_port: int = Field(default=8071, description="Puerto del health server")
    log_level: str = Field(default="INFO", description="Log level")

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
