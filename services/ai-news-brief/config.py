"""
AI News Brief Service Configuration

Genera un "Brief Fundamental" de una noticia: explica el CONTEXTO en el que
aparece y QUE CAMBIA en el fundamento de la empresa (no metricas tecnicas).

Fuentes:
  - Claude Opus 4.8 (conocimiento + razonamiento)
  - Busqueda web en vivo (server tool) para lo mas reciente, con citas
  - Lente: la metodologia del trader ("Changing Fundamentals")
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    # ── Anthropic ───────────────────────────────────────────────────────
    anthropic_api_key: str = Field(default="", description="Anthropic API key")
    anthropic_model: str = Field(default="claude-opus-4-8", description="Modelo Claude")
    anthropic_version: str = Field(default="2023-06-01", description="anthropic-version header")
    # Opus 4.8: thinking adaptativo + nivel de esfuerzo (no 'enabled'/'budget').
    thinking_enabled: bool = Field(default=True, description="Usar thinking adaptativo")
    effort: str = Field(default="high", description="low|medium|high|xhigh|max")
    max_tokens: int = Field(default=16000, description="Tokens maximos (thinking + salida)")
    # Busqueda web en vivo (server tool de Anthropic) para frescura.
    web_search_enabled: bool = Field(default=True, description="Habilitar web search tool")
    web_search_max_uses: int = Field(default=5, description="Max busquedas web por brief")
    # Iteraciones max del loop agentico (tool use). 0 = sin tools internas.
    max_tool_iterations: int = Field(default=4, description="Vueltas max del loop de tools")

    # ── Endpoints internos (datos para las tools) ───────────────────────
    # network_mode: host => todo en 127.0.0.1.
    gateway_url: str = Field(default="http://127.0.0.1:8000", description="API Gateway")
    dilution_url: str = Field(default="http://127.0.0.1:8009", description="Dilution tracker")
    tool_timeout_s: float = Field(default=10.0, description="Timeout por llamada a tool interna")
    internal_tools_enabled: bool = Field(default=True, description="Exponer tools internas al LLM")
    max_price_targets: int = Field(default=8, description="Max price targets devueltos")
    max_instruments: int = Field(default=8, description="Max instrumentos de dilucion devueltos")

    # ── Metodologia (lente fundamental) ─────────────────────────────────
    # Prioridad: el tratado del usuario en docs/, si existe; si no, el base.
    methodology_path: str = Field(default="/app/docs/trading_methodology.md")
    methodology_fallback: str = Field(default="/app/methodology.md")

    # ── Servicio ────────────────────────────────────────────────────────
    service_port: int = Field(default=8072)
    log_level: str = Field(default="INFO")
    request_timeout_s: float = Field(default=120.0, description="Timeout de la llamada a Anthropic")

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
