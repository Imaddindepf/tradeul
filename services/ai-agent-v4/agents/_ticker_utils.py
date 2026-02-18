"""
Ticker Universe Validator — validates tickers against the real market.

The LLM (supervisor) handles ticker extraction from natural language.
This module's only job: confirm that LLM-suggested tickers actually
exist in our Redis market universe, catching hallucinations.

Architecture:
  LLM extracts tickers (understands context, language, company names)
    → validate_tickers() confirms they exist in Redis
    → Only real tickers reach the agents

Redis keys used:
  - snapshot:enriched:latest     (live market hours)
  - snapshot:enriched:last_close (fallback, off-hours)
"""
from __future__ import annotations

import logging
import os
import re
import time
from typing import Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# ── Redis connection ────────────────────────────────────────────────
# Enriched snapshots live in DB 0 (scanner's DB), NOT the agent's DB 5.
_AGENT_REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/5")
_SNAPSHOT_REDIS_URL = re.sub(r'/\d+$', '/0', _AGENT_REDIS_URL)
_redis: Optional[aioredis.Redis] = None

# ── In-memory universe cache ───────────────────────────────────────
_universe: set[str] = set()
_universe_ts: float = 0.0
_UNIVERSE_TTL = 300  # refresh every 5 min


async def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(_SNAPSHOT_REDIS_URL, decode_responses=True)
    return _redis


async def close_redis() -> None:
    """Close the shared Redis client (called during app shutdown)."""
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


async def _load_universe() -> set[str]:
    """Load all valid ticker symbols from Redis.

    Tries live data first, falls back to last close.
    Caches in memory for 5 minutes.
    """
    global _universe, _universe_ts
    now = time.time()
    if _universe and (now - _universe_ts) < _UNIVERSE_TTL:
        return _universe

    try:
        r = await _get_redis()

        keys = await r.hkeys("snapshot:enriched:latest")
        if not keys:
            keys = await r.hkeys("snapshot:enriched:last_close")

        if keys:
            _universe = set(keys)
            _universe_ts = now
            logger.info("Ticker universe loaded: %d symbols", len(_universe))
        else:
            logger.warning("No ticker universe found in Redis")
    except Exception as exc:
        logger.error("Failed to load ticker universe: %s", exc)

    return _universe


async def get_ticker_info(tickers: list[str]) -> dict[str, dict[str, str]]:
    """Fetch company metadata for validated tickers from Redis.

    Returns a dict mapping each ticker to its metadata:
      {"LFS": {"company_name": "LEIFRAS Co., Ltd.", "sector": "Consumer Defensive",
               "industry": "Education & Training Services", "description": "..."}}

    This metadata is stored in the state so downstream agents (especially research)
    know which company each ticker represents, preventing hallucination.
    """
    if not tickers:
        return {}

    try:
        r = await _get_redis()
        # metadata:ticker:* keys live in DB 0 (same as enriched snapshots)
        info: dict[str, dict[str, str]] = {}
        for t in tickers:
            sym = t.strip().upper()
            raw = await r.get(f"metadata:ticker:{sym}")
            if raw:
                import orjson
                data = orjson.loads(raw if isinstance(raw, bytes) else raw.encode())
                info[sym] = {
                    "company_name": data.get("company_name", ""),
                    "sector": data.get("sector", ""),
                    "industry": data.get("industry", ""),
                    "description": data.get("description", ""),
                }
        return info
    except Exception as exc:
        logger.warning("Failed to fetch ticker info: %s", exc)
        return {}


async def validate_tickers(tickers: list[str]) -> list[str]:
    """Validate a list of ticker symbols against the Redis universe.

    This is the primary function. Called by the supervisor after
    the LLM extracts tickers from the user query.

    Returns only tickers that exist in our market universe.
    If the universe is unavailable, returns all tickers unchanged
    (graceful degradation).
    """
    if not tickers:
        return []

    # Normalize: uppercase, strip whitespace
    normalized = list(dict.fromkeys(t.strip().upper() for t in tickers if t.strip()))
    if not normalized:
        return []

    universe = await _load_universe()

    if universe:
        validated = [t for t in normalized if t in universe]
        rejected = set(normalized) - set(validated)
        if rejected:
            logger.info("Rejected tickers not in universe: %s", rejected)
        return validated
    else:
        logger.warning("Universe unavailable — returning tickers unvalidated: %s", normalized)
        return normalized
