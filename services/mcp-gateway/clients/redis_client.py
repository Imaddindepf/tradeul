"""
Shared async Redis client for all MCP servers.
Singleton pattern - one connection pool shared across all tools.
"""
import redis.asyncio as aioredis
import orjson
from typing import Optional, Any

_redis: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        from config import config
        _redis = aioredis.from_url(
            config.redis_url,
            decode_responses=True,
            max_connections=20,
        )
    return _redis


async def close_redis():
    global _redis
    if _redis:
        await _redis.aclose()
        _redis = None


async def redis_get_json(key: str) -> Optional[Any]:
    r = await get_redis()
    raw = await r.get(key)
    if raw is None:
        return None
    return orjson.loads(raw)


async def redis_hgetall_parsed(key: str) -> dict:
    r = await get_redis()
    raw = await r.hgetall(key)
    if not raw:
        return {}
    result = {}
    for k, v in raw.items():
        if k == "__meta__":
            continue
        try:
            result[k] = orjson.loads(v)
        except Exception:
            result[k] = v
    return result


async def redis_zrevrange_parsed(key: str, start: int = 0, stop: int = -1) -> list:
    r = await get_redis()
    raw = await r.zrevrange(key, start, stop)
    results = []
    for item in raw:
        try:
            results.append(orjson.loads(item))
        except Exception:
            results.append(item)
    return results


async def redis_hget_enriched(symbol: str) -> Optional[dict]:
    """Get enriched snapshot for a symbol with fallback to last_close.
    During market hours uses 'snapshot:enriched:latest'.
    Outside market hours falls back to 'snapshot:enriched:last_close'.
    """
    r = await get_redis()
    raw = await r.hget("snapshot:enriched:latest", symbol.upper())
    if not raw:
        raw = await r.hget("snapshot:enriched:last_close", symbol.upper())
    if not raw:
        return None
    try:
        return orjson.loads(raw)
    except Exception:
        return None


async def redis_xrevrange(stream: str, count: int = 100) -> list:
    r = await get_redis()
    entries = await r.xrevrange(stream, count=count)
    results = []
    for entry_id, data in entries:
        parsed = {}
        for k, v in data.items():
            try:
                parsed[k] = orjson.loads(v)
            except Exception:
                parsed[k] = v
        parsed["_stream_id"] = entry_id
        results.append(parsed)
    return results
