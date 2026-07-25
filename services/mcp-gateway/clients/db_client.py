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


# ── Share-class dedupe map ───────────────────────────────────────
# Symbols that share a ticker_root (GOOG/GOOGL, BRK.A/BRK.B, SKHY/SKHYV)
# are the same company; rankings must not list them twice.
_root_map: dict[str, str] = {}
_root_map_loaded_at: float = 0.0
_ROOT_MAP_TTL = 3600.0


async def get_share_class_roots() -> dict[str, str]:
    """symbol -> ticker_root, only for symbols whose root is shared by
    more than one listing. Cached for 1h; empty dict on DB failure."""
    global _root_map, _root_map_loaded_at
    import time
    if _root_map and (time.time() - _root_map_loaded_at) < _ROOT_MAP_TTL:
        return _root_map
    try:
        rows = await db_fetch("""
            SELECT symbol, ticker_root FROM tickers_unified
            WHERE ticker_root IN (
                SELECT ticker_root FROM tickers_unified
                WHERE ticker_root IS NOT NULL
                GROUP BY ticker_root HAVING COUNT(*) > 1
            )
        """)
        _root_map = {r["symbol"]: r["ticker_root"] for r in rows}
        _root_map_loaded_at = time.time()
    except Exception as exc:
        logger.warning("share-class root map load failed: %s", exc)
    return _root_map


def dedupe_by_root(rows: list[dict], root_map: dict[str, str], key: str = "symbol") -> list[dict]:
    """Keep only the first row per company (rows must already be sorted
    by the ranking metric, so the best share class survives)."""
    seen: set[str] = set()
    out = []
    for row in rows:
        sym = row.get(key)
        root = root_map.get(sym, sym)
        if root in seen:
            continue
        seen.add(root)
        out.append(row)
    return out
