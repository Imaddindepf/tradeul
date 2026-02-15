"""Shared clients for MCP servers."""
from .redis_client import get_redis, close_redis
from .http_client import get_http_client, close_http_client

__all__ = ["get_redis", "close_redis", "get_http_client", "close_http_client"]
