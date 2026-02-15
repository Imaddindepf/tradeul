"""
MCP Gateway Configuration
Centralized config for all MCP servers - reads from environment variables.
"""
from pydantic_settings import BaseSettings
from typing import Optional


class MCPGatewayConfig(BaseSettings):
    """Configuration for the MCP Gateway service."""

    # Redis
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None

    # Service URLs (DNS-based, matching docker-compose service names)
    # NOTE: Docker Compose DNS uses the service name as-is (hyphens, underscores)
    api_gateway_url: str = "http://api_gateway:8000"
    scanner_url: str = "http://scanner:8005"
    analytics_url: str = "http://analytics:8007"
    screener_url: str = "http://screener:8000"
    sec_filings_url: str = "http://sec-filings:8012"
    financials_url: str = "http://financials:8020"
    dilution_tracker_url: str = "http://dilution_tracker:8000"
    benzinga_news_url: str = "http://benzinga-news:8015"
    benzinga_earnings_url: str = "http://benzinga-earnings:8022"
    prediction_markets_url: str = "http://prediction-markets:8021"
    ticker_metadata_url: str = "http://ticker_metadata:8010"
    pattern_matching_url: str = "http://pattern_matching:8025"
    event_detector_url: str = "http://event_detector:8040"

    # Historical data paths
    day_aggs_path: str = "/data/polygon/day_aggs"
    minute_aggs_path: str = "/data/polygon/minute_aggs"

    # TimescaleDB
    db_host: str = "timescaledb"
    db_port: int = 5432
    db_name: str = "tradeul"
    db_user: str = "tradeul_user"
    db_password: str = "changeme123"

    # MCP Server
    mcp_port: int = 8050
    mcp_host: str = "0.0.0.0"

    @property
    def redis_url(self) -> str:
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def database_url(self) -> str:
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    model_config = {"env_prefix": "MCP_"}


config = MCPGatewayConfig()
