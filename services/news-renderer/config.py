"""News Renderer configuration."""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    service_port: int = Field(default=8074)
    log_level: str = Field(default="INFO")
    max_concurrency: int = Field(default=2, description="Renderizados simultáneos (acota RAM)")
    nav_timeout_ms: int = Field(default=20000, description="Timeout de navegación")
    idle_timeout_ms: int = Field(default=6000, description="Espera de networkidle tras carga")
    proxy_url: str = Field(default="", description="Proxy de egress opcional (p. ej. US) para evitar muros GDPR")

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
