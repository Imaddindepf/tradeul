"""
Memory Manager - Conversation persistence and market insight storage via Redis.

Stores:
  - Conversation threads per user (hash: memory:user:{user_id}:threads)
  - Market insights per symbol   (sorted set: memory:insights:{symbol})
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


class MemoryManager:
    """Async Redis-backed memory manager for conversations and market insights."""

    def __init__(self, redis_url: Optional[str] = None):
        self._redis_url = redis_url or os.getenv("REDIS_URL", "redis://redis:6379/5")
        self._redis: Optional[aioredis.Redis] = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(
                self._redis_url,
                decode_responses=True,
            )
        return self._redis

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    # ── Conversation storage ─────────────────────────────────────

    async def store_conversation(
        self,
        user_id: str,
        thread_id: str,
        messages: list[dict[str, Any]],
        summary: str = "",
    ) -> None:
        """Store a conversation thread for a user.

        Args:
            user_id:   Unique user identifier.
            thread_id: Unique thread/conversation identifier.
            messages:  List of message dicts (role, content, timestamp).
            summary:   Short summary of the conversation for quick retrieval.
        """
        r = await self._get_redis()
        key = f"memory:user:{user_id}:threads"

        payload = json.dumps({
            "thread_id": thread_id,
            "messages": messages,
            "summary": summary,
            "timestamp": time.time(),
            "message_count": len(messages),
        })

        await r.hset(key, thread_id, payload)

        # Also maintain a sorted set for chronological retrieval
        ts_key = f"memory:user:{user_id}:thread_ts"
        await r.zadd(ts_key, {thread_id: time.time()})

        logger.debug(
            "Stored conversation %s for user %s (%d messages)",
            thread_id, user_id, len(messages),
        )

    async def get_recent_context(
        self,
        user_id: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Return the last N conversation summaries for a user.

        Args:
            user_id: Unique user identifier.
            limit:   Maximum number of conversations to return.

        Returns:
            List of dicts with thread_id, summary, timestamp.
        """
        r = await self._get_redis()

        # Get the most recent thread IDs by timestamp (descending)
        ts_key = f"memory:user:{user_id}:thread_ts"
        thread_ids = await r.zrevrange(ts_key, 0, limit - 1)

        if not thread_ids:
            return []

        key = f"memory:user:{user_id}:threads"
        results: list[dict[str, Any]] = []

        for tid in thread_ids:
            raw = await r.hget(key, tid)
            if raw:
                data = json.loads(raw)
                results.append({
                    "thread_id": data["thread_id"],
                    "summary": data.get("summary", ""),
                    "timestamp": data.get("timestamp", 0),
                    "message_count": data.get("message_count", 0),
                })

        return results

    # ── Market insight storage ───────────────────────────────────

    async def store_market_insight(
        self,
        symbol: str,
        insight: str,
        source: str = "unknown",
    ) -> None:
        """Store a market insight for a given symbol.

        Args:
            symbol:  Ticker symbol (e.g. AAPL).
            insight: The insight text.
            source:  Where this insight came from (agent name, user, etc.).
        """
        r = await self._get_redis()
        key = f"memory:insights:{symbol.upper()}"

        payload = json.dumps({
            "insight": insight,
            "source": source,
            "timestamp": time.time(),
        })

        await r.zadd(key, {payload: time.time()})

        # Trim to keep only the most recent 100 insights per symbol
        await r.zremrangebyrank(key, 0, -101)

        logger.debug("Stored insight for %s from %s", symbol, source)

    async def get_market_insights(
        self,
        symbol: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Retrieve recent market insights for a symbol.

        Args:
            symbol: Ticker symbol (e.g. AAPL).
            limit:  Maximum number of insights to return.

        Returns:
            List of dicts with insight, source, timestamp.
        """
        r = await self._get_redis()
        key = f"memory:insights:{symbol.upper()}"

        raw_entries = await r.zrevrange(key, 0, limit - 1)

        results: list[dict[str, Any]] = []
        for entry in raw_entries:
            try:
                data = json.loads(entry)
                results.append(data)
            except json.JSONDecodeError:
                logger.warning("Skipping malformed insight entry for %s", symbol)

        return results
