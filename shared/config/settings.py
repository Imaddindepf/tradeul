"""
Centralized configuration using Pydantic Settings
Loads from environment variables and .env file
"""

from typing import Optional, List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    """
    Application settings
    All settings can be overridden by environment variables
    """
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow"
    )
    
    # =============================================
    # API KEYS
    # =============================================
    polygon_api_key: str = Field(..., description="Polygon.io API key")
    fmp_api_key: str = Field(..., description="FMP API key")
    
    # Aliases para compatibilidad (mayúsculas)
    @property
    def POLYGON_API_KEY(self) -> str:
        return self.polygon_api_key
    
    @property
    def FMP_API_KEY(self) -> str:
        return self.fmp_api_key
    
    # =============================================
    # REDIS
    # =============================================
    redis_host: str = Field(default="redis", description="Redis host")
    redis_port: int = Field(default=6379, description="Redis port")
    redis_db: int = Field(default=0, description="Redis database number")
    redis_password: Optional[str] = Field(default=None, description="Redis password")
    
    # Aliases para compatibilidad (mayúsculas)
    @property
    def REDIS_HOST(self) -> str:
        return self.redis_host
    
    @property
    def REDIS_PORT(self) -> int:
        return self.redis_port
    
    @property
    def REDIS_DB(self) -> int:
        return self.redis_db
    
    # =============================================
    # TIMESCALEDB / POSTGRESQL
    # =============================================
    db_host: str = Field(default="timescaledb", description="Database host")
    db_port: int = Field(default=5432, description="Database port")
    db_name: str = Field(default="tradeul", description="Database name")
    db_user: str = Field(default="tradeul_user", description="Database user")
    db_password: str = Field(default="changeme123", description="Database password")
    
    # Aliases para compatibilidad (mayúsculas)
    @property
    def POSTGRES_HOST(self) -> str:
        return self.db_host
    
    @property
    def POSTGRES_PORT(self) -> int:
        return self.db_port
    
    @property
    def POSTGRES_DB(self) -> str:
        return self.db_name
    
    @property
    def POSTGRES_USER(self) -> str:
        return self.db_user
    
    @property
    def POSTGRES_PASSWORD(self) -> str:
        return self.db_password
    
    @property
    def database_url(self) -> str:
        """Get PostgreSQL connection URL for psycopg2"""
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"
    
    @property
    def async_database_url(self) -> str:
        """Get async PostgreSQL connection URL for asyncpg (NOT sqlalchemy)"""
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"
    
    # =============================================
    # TIMESCALEDB (Aliases)
    # =============================================
    @property
    def TIMESCALE_HOST(self) -> str:
        return self.db_host
    
    @property
    def TIMESCALE_PORT(self) -> int:
        return self.db_port
    
    @property
    def TIMESCALE_DB(self) -> str:
        return self.db_name
    
    @property
    def TIMESCALE_USER(self) -> str:
        return self.db_user
    
    @property
    def TIMESCALE_PASSWORD(self) -> str:
        return self.db_password
    
    # =============================================
    # SERVICES
    # =============================================
    orchestrator_host: str = Field(default="orchestrator", description="Orchestrator host")
    orchestrator_port: int = Field(default=8001, description="Orchestrator port")
    
    market_session_host: str = Field(default="market_session", description="Market Session host")
    market_session_port: int = Field(default=8002, description="Market Session port")
    
    data_ingest_host: str = Field(default="data_ingest", description="Data Ingest host")
    data_ingest_port: int = Field(default=8003, description="Data Ingest port")
    
    historical_host: str = Field(default="historical", description="Historical host")
    historical_port: int = Field(default=8004, description="Historical port")
    
    scanner_host: str = Field(default="scanner", description="Scanner host")
    scanner_port: int = Field(default=8005, description="Scanner port")
    
    polygon_ws_host: str = Field(default="polygon_ws", description="Polygon WS host")
    polygon_ws_port: int = Field(default=8006, description="Polygon WS port")
    
    analytics_host: str = Field(default="analytics", description="Analytics host")
    analytics_port: int = Field(default=8007, description="Analytics port")
    
    api_gateway_host: str = Field(default="api_gateway", description="API Gateway host")
    api_gateway_port: int = Field(default=8000, description="API Gateway port")
    
    admin_panel_host: str = Field(default="admin_panel", description="Admin Panel host")
    admin_panel_port: int = Field(default=8008, description="Admin Panel port")
    
    # =============================================
    # SCANNER CONFIGURATION
    # =============================================
    initial_universe_size: int = Field(default=11000, description="Initial universe size")
    max_filtered_tickers: int = Field(default=1000, description="Max filtered tickers")
    snapshot_interval: int = Field(default=5, description="Snapshot interval in seconds")
    default_gappers_limit: int = Field(default=100, description="Default number of gappers to return")
    default_category_limit: int = Field(default=100, description="Default number of tickers per category")
    default_query_limit: int = Field(default=1000, description="Default query limit for scanner endpoints")
    max_category_limit: int = Field(default=500, description="Maximum number of tickers per category")
    max_query_limit: int = Field(default=5000, description="Maximum query limit for scanner endpoints")
    
    # =============================================
    # MARKET HOURS (ET)
    # =============================================
    pre_market_start: str = Field(default="04:00", description="Pre-market start time")
    market_open: str = Field(default="09:30", description="Market open time")
    market_close: str = Field(default="16:00", description="Market close time")
    post_market_end: str = Field(default="20:00", description="Post-market end time")
    
    # =============================================
    # RVOL CONFIGURATION
    # =============================================
    rvol_slot_minutes: int = Field(default=5, description="RVOL slot size in minutes")
    rvol_lookback_days: int = Field(default=30, description="RVOL lookback period")
    
    # =============================================
    # LOGGING
    # =============================================
    log_level: str = Field(default="INFO", description="Log level")
    log_format: str = Field(default="json", description="Log format (json or text)")
    
    # =============================================
    # SECURITY
    # =============================================
    api_key_admin: str = Field(default="changeme_admin_key", description="Admin API key")
    jwt_secret: str = Field(default="changeme_jwt_secret", description="JWT secret key")
    jwt_algorithm: str = Field(default="HS256", description="JWT algorithm")
    jwt_expiration_hours: int = Field(default=24, description="JWT expiration in hours")
    
    # =============================================
    # PERFORMANCE
    # =============================================
    worker_threads: int = Field(default=4, description="Worker threads")
    max_concurrent_requests: int = Field(default=100, description="Max concurrent requests")
    
    # =============================================
    # WEBSOCKET
    # =============================================
    ws_max_connections: int = Field(default=1000, description="Max WebSocket connections")
    ws_ping_interval: int = Field(default=30, description="WebSocket ping interval")
    ws_ping_timeout: int = Field(default=10, description="WebSocket ping timeout")
    
    # =============================================
    # POLYGON WEBSOCKET
    # =============================================
    polygon_ws_url: str = Field(
        default="wss://socket.polygon.io/stocks",
        description="Polygon WebSocket URL"
    )
    
    # =============================================
    # DEVELOPMENT
    # =============================================
    debug: bool = Field(default=False, description="Debug mode")
    environment: str = Field(default="production", description="Environment")
    
    # =============================================
    # REDIS STREAM KEYS
    # =============================================
    # Core data streams
    stream_raw_snapshots: str = Field(default="snapshots:raw", description="Raw snapshots stream (data_ingest → scanner)")
    stream_filtered_tickers: str = Field(default="tickers:filtered", description="Filtered tickers stream (scanner → analytics)")
    stream_session_events: str = Field(default="events:session", description="Session events stream (market_session → scanner)")
    
    # Real-time data streams
    stream_realtime_aggregates: str = Field(default="stream:realtime:aggregates", description="Real-time aggregates from Polygon WS")
    stream_analytics_rvol: str = Field(default="stream:analytics:rvol", description="RVOL calculations from analytics service")
    
    # NEW: Ranking deltas stream (para arquitectura snapshot + deltas)
    stream_ranking_deltas: str = Field(default="stream:ranking:deltas", description="Incremental ranking changes (snapshot + deltas)")
    
    # Polygon WS subscription control
    key_polygon_subscriptions: str = Field(default="polygon_ws:subscriptions", description="Polygon WS subscription commands stream")
    
    # =============================================
    # REDIS KEY PREFIXES
    # =============================================
    key_prefix_metadata: str = Field(default="metadata", description="Metadata key prefix")
    key_prefix_rvol: str = Field(default="rvol", description="RVOL key prefix")
    key_prefix_market: str = Field(default="market", description="Market key prefix")
    key_prefix_scanner: str = Field(default="scanner", description="Scanner key prefix")
    
    # =============================================
    # CACHE TTL (seconds)
    # =============================================
    cache_ttl_metadata: int = Field(default=86400, description="Metadata cache TTL (24h)")
    cache_ttl_market_status: int = Field(default=60, description="Market status cache TTL (1min)")
    cache_ttl_filters: int = Field(default=300, description="Filters cache TTL (5min)")
    
    # =============================================
    # HELPER METHODS
    # =============================================
    
    def get_service_url(self, service_name: str) -> str:
        """Get full URL for a service"""
        service_map = {
            "orchestrator": f"http://{self.orchestrator_host}:{self.orchestrator_port}",
            "market_session": f"http://{self.market_session_host}:{self.market_session_port}",
            "data_ingest": f"http://{self.data_ingest_host}:{self.data_ingest_port}",
            "historical": f"http://{self.historical_host}:{self.historical_port}",
            "scanner": f"http://{self.scanner_host}:{self.scanner_port}",
            "polygon_ws": f"http://{self.polygon_ws_host}:{self.polygon_ws_port}",
            "analytics": f"http://{self.analytics_host}:{self.analytics_port}",
            "api_gateway": f"http://{self.api_gateway_host}:{self.api_gateway_port}",
            "admin_panel": f"http://{self.admin_panel_host}:{self.admin_panel_port}",
        }
        return service_map.get(service_name, "")
    
    def get_redis_url(self) -> str:
        """Get Redis connection URL"""
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"


# Global settings instance
settings = Settings()
