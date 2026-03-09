"""
OpenUL Stream Service Configuration
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional, List


class Settings(BaseSettings):
    # X API (Consumer credentials for App-Only Bearer)
    x_consumer_key: str = Field(..., description="X API Consumer Key")
    x_consumer_secret: str = Field(..., description="X API Consumer Secret")

    # Accounts to monitor
    monitored_users: List[str] = Field(
        default=["GermanFinGuy", "tradfi", "TapTradTerminal"],
        description="X usernames to track via Filtered Stream",
    )

    # Redis
    redis_host: str = Field(default="redis", description="Redis host")
    redis_port: int = Field(default=6379, description="Redis port")
    redis_password: Optional[str] = Field(default=None, description="Redis password")

    # Redis Stream config
    redis_stream_key: str = Field(default="openul:news", description="Redis Stream key for breaking news")
    redis_stream_maxlen: int = Field(default=5000, description="Max entries in Redis Stream")
    redis_latest_key: str = Field(default="openul:latest", description="Sorted set for latest news")
    redis_latest_maxlen: int = Field(default=500, description="Max entries in latest sorted set")

    # Service
    service_port: int = Field(default=8070, description="Service port")
    log_level: str = Field(default="INFO", description="Log level")

    # Reconnect
    initial_backoff: float = Field(default=0.5, description="Initial reconnect backoff seconds")
    max_backoff: float = Field(default=30.0, description="Max reconnect backoff seconds")

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
