"""
Shared async PostgreSQL/TimescaleDB client for MCP servers.
Lazy-initialized asyncpg connection pool.
"""
import asyncpg
import logging
from typing import Optional, Any

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None


async def get_db_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        from config import config
        _pool = await asyncpg.create_pool(
            config.database_url,
            min_size=2,
            max_size=10,
            command_timeout=30,
        )
        logger.info("TimescaleDB pool created: %s:%s/%s", config.db_host, config.db_port, config.db_name)
    return _pool


async def close_db_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("TimescaleDB pool closed")


async def db_fetch(query: str, *args, timeout: float = 15.0) -> list[dict]:
    """Execute a SELECT query and return results as list of dicts."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *args, timeout=timeout)
        return [dict(r) for r in rows]


async def db_fetchval(query: str, *args, timeout: float = 10.0) -> Any:
    """Execute a query and return a single value."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(query, *args, timeout=timeout)
