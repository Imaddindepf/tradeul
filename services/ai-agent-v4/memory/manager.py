"""
Enhanced Memory Manager - Conversation persistence, market insight storage,
and keyword-based memory search via Redis.

Storage layout:
  - memory:conversations:{user_id}:{thread_id}  (list of messages)
  - memory:threads:{user_id}                     (sorted set by timestamp)
  - memory:insights:{symbol}                     (sorted set by timestamp)
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional

import orjson
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


class MemoryManager:
    """Async Redis-backed memory manager with conversation history,
    market insights, and keyword-based memory search."""

    def __init__(self, redis_url: Optional[str] = None) -> None:
        self._redis_url = redis_url or os.getenv("REDIS_URL", "redis://redis:6379/5")
        self._redis: Optional[aioredis.Redis] = None

    # ── lifecycle ────────────────────────────────────────────────

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(
                self._redis_url,
                decode_responses=False,  # we use orjson for (de)serialisation
            )
        return self._redis

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    # ══════════════════════════════════════════════════════════════
    # Conversation Memory
    # ══════════════════════════════════════════════════════════════

    async def store_conversation(
        self,
        user_id: str,
        thread_id: str,
        query: str,
        response: str,
        agent_results_summary: Optional[dict[str, Any]] = None,
    ) -> None:
        """Append a query/response pair to a conversation thread.

        Each entry is stored as a JSON blob in a Redis list, enabling
        ordered retrieval without score collisions.

        Args:
            user_id:               User identifier.
            thread_id:             Conversation thread identifier.
            query:                 The user's query text.
            response:              The agent's response text.
            agent_results_summary: Optional summary of agent results.
        """
        r = await self._get_redis()
        now = time.time()

        entry = orjson.dumps({
            "query": query,
            "response": response,
            "agent_results_summary": agent_results_summary or {},
            "timestamp": now,
        })

        conv_key = f"memory:conversations:{user_id}:{thread_id}"
        await r.rpush(conv_key, entry)

        # Cap the list at 200 messages to prevent unbounded growth
        await r.ltrim(conv_key, -200, -1)

        # Update the thread index (sorted set keyed by latest timestamp)
        thread_key = f"memory:threads:{user_id}"
        thread_meta = orjson.dumps({
            "thread_id": thread_id,
            "last_query": query[:200],  # truncate for summary
            "updated_at": now,
        })

        # Use thread_id as the member so upserts work naturally
        await r.zrem(thread_key, *[
            m for m in await r.zrange(thread_key, 0, -1)
            if _extract_thread_id(m) == thread_id
        ])
        await r.zadd(thread_key, {thread_meta: now})

        logger.debug(
            "Stored conversation entry for user=%s thread=%s", user_id, thread_id,
        )

    async def get_conversation_history(
        self,
        user_id: str,
        thread_id: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Retrieve the most recent messages in a conversation thread.

        Args:
            user_id:   User identifier.
            thread_id: Conversation thread identifier.
            limit:     Maximum number of message pairs to return.

        Returns:
            List of dicts ``{query, response, agent_results_summary, timestamp}``.
        """
        r = await self._get_redis()
        conv_key = f"memory:conversations:{user_id}:{thread_id}"

        # Fetch the last `limit` entries
        raw_entries = await r.lrange(conv_key, -limit, -1)

        results: list[dict[str, Any]] = []
        for raw in raw_entries:
            try:
                results.append(orjson.loads(raw))
            except Exception:
                logger.warning("Skipping malformed conversation entry")
        return results

    async def get_recent_threads(
        self,
        user_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Return the most recent conversation thread summaries.

        Args:
            user_id: User identifier.
            limit:   Maximum number of threads to return.

        Returns:
            List of dicts ``{thread_id, last_query, updated_at}``,
            ordered newest-first.
        """
        r = await self._get_redis()
        thread_key = f"memory:threads:{user_id}"

        raw_entries = await r.zrevrange(thread_key, 0, limit - 1)

        results: list[dict[str, Any]] = []
        for raw in raw_entries:
            try:
                results.append(orjson.loads(raw))
            except Exception:
                logger.warning("Skipping malformed thread index entry")
        return results

    # ══════════════════════════════════════════════════════════════
    # Market Insight Memory
    # ══════════════════════════════════════════════════════════════

    async def store_insight(
        self,
        symbol: str,
        insight_type: str,
        content: str,
        source_agent: str,
    ) -> None:
        """Store an analysis insight for a ticker.

        Args:
            symbol:       Ticker symbol (e.g. AAPL).
            insight_type: Category (e.g. technical, fundamental, news).
            content:      The insight text.
            source_agent: Agent that produced this insight.
        """
        r = await self._get_redis()
        now = time.time()
        key = f"memory:insights:{symbol.upper()}"

        payload = orjson.dumps({
            "insight_type": insight_type,
            "content": content,
            "source_agent": source_agent,
            "timestamp": now,
        })

        await r.zadd(key, {payload: now})

        # Keep only the most recent 200 insights per symbol
        await r.zremrangebyrank(key, 0, -201)

        logger.debug("Stored %s insight for %s from %s", insight_type, symbol, source_agent)

    async def get_insights(
        self,
        symbol: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Retrieve recent insights for a ticker.

        Args:
            symbol: Ticker symbol.
            limit:  Maximum number of insights.

        Returns:
            List of insight dicts, newest first.
        """
        r = await self._get_redis()
        key = f"memory:insights:{symbol.upper()}"

        raw_entries = await r.zrevrange(key, 0, limit - 1)

        results: list[dict[str, Any]] = []
        for raw in raw_entries:
            try:
                results.append(orjson.loads(raw))
            except Exception:
                logger.warning("Skipping malformed insight entry for %s", symbol)
        return results

    # ══════════════════════════════════════════════════════════════
    # Semantic / Keyword Memory Search
    # ══════════════════════════════════════════════════════════════

    async def search_memory(
        self,
        user_id: str,
        query: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Keyword-based memory search across conversations and insights.

        Scans recent conversation entries and insight entries for keyword
        overlap with *query*.  This is a simple TF fallback; when Redis
        Vector Similarity Search (VSS) is available, it should be
        replaced with proper embedding-based retrieval.

        Args:
            user_id: User identifier.
            query:   Search query string.
            limit:   Maximum number of results to return.

        Returns:
            List of dicts with ``source``, ``content``, ``score``, ``timestamp``.
        """
        query_tokens = set(query.lower().split())
        if not query_tokens:
            return []

        scored: list[tuple[float, dict[str, Any]]] = []

        # ── Search conversations ─────────────────────────────────
        threads = await self.get_recent_threads(user_id, limit=20)
        for thread in threads:
            thread_id = thread.get("thread_id", "")
            history = await self.get_conversation_history(user_id, thread_id, limit=30)
            for entry in history:
                text = f"{entry.get('query', '')} {entry.get('response', '')}".lower()
                text_tokens = set(text.split())
                overlap = len(query_tokens & text_tokens)
                if overlap > 0:
                    score = overlap / len(query_tokens)
                    scored.append((score, {
                        "source": "conversation",
                        "thread_id": thread_id,
                        "content": entry.get("query", "")[:300],
                        "response_snippet": entry.get("response", "")[:300],
                        "score": round(score, 3),
                        "timestamp": entry.get("timestamp", 0),
                    }))

        # ── Search insights ──────────────────────────────────────
        # We don't know which symbols to search, so scan recent keys
        r = await self._get_redis()
        cursor: int | bytes = 0
        insight_keys: list[bytes | str] = []
        while True:
            cursor, keys = await r.scan(cursor=cursor, match="memory:insights:*", count=100)
            insight_keys.extend(keys)
            if cursor == 0:
                break

        for ikey in insight_keys[:50]:  # limit scan breadth
            raw_entries = await r.zrevrange(ikey, 0, 19)
            key_str = ikey.decode() if isinstance(ikey, bytes) else ikey
            symbol = key_str.rsplit(":", 1)[-1]

            for raw in raw_entries:
                try:
                    data = orjson.loads(raw)
                except Exception:
                    continue
                text = f"{data.get('content', '')} {data.get('insight_type', '')} {symbol}".lower()
                text_tokens = set(text.split())
                overlap = len(query_tokens & text_tokens)
                if overlap > 0:
                    score = overlap / len(query_tokens)
                    scored.append((score, {
                        "source": "insight",
                        "symbol": symbol,
                        "insight_type": data.get("insight_type", ""),
                        "content": data.get("content", "")[:300],
                        "score": round(score, 3),
                        "timestamp": data.get("timestamp", 0),
                    }))

        # Sort by score descending, then by timestamp descending
        scored.sort(key=lambda x: (-x[0], -x[1].get("timestamp", 0)))
        return [item for _, item in scored[:limit]]

    # ══════════════════════════════════════════════════════════════
    # Housekeeping
    # ══════════════════════════════════════════════════════════════

    async def cleanup_old_memories(self, days: int = 30) -> int:
        """Remove conversation and insight entries older than *days*.

        Returns:
            Total number of entries removed.
        """
        r = await self._get_redis()
        cutoff = time.time() - (days * 86400)
        removed = 0

        # ── Clean thread indexes ─────────────────────────────────
        cursor: int | bytes = 0
        while True:
            cursor, keys = await r.scan(cursor=cursor, match="memory:threads:*", count=200)
            for key in keys:
                count = await r.zremrangebyscore(key, "-inf", cutoff)
                removed += count
            if cursor == 0:
                break

        # ── Clean insight sorted sets ────────────────────────────
        cursor = 0
        while True:
            cursor, keys = await r.scan(cursor=cursor, match="memory:insights:*", count=200)
            for key in keys:
                count = await r.zremrangebyscore(key, "-inf", cutoff)
                removed += count
            if cursor == 0:
                break

        # ── Clean conversation lists (remove entire key if stale) ─
        cursor = 0
        while True:
            cursor, keys = await r.scan(cursor=cursor, match="memory:conversations:*", count=200)
            for key in keys:
                # Check the newest entry in the list
                last_raw = await r.lindex(key, -1)
                if last_raw is not None:
                    try:
                        last = orjson.loads(last_raw)
                        if last.get("timestamp", 0) < cutoff:
                            length = await r.llen(key)
                            await r.delete(key)
                            removed += length
                    except Exception:
                        pass
            if cursor == 0:
                break

        logger.info("Cleaned up %d old memory entries (cutoff=%d days)", removed, days)
        return removed


# ── Helpers ──────────────────────────────────────────────────────


def _extract_thread_id(raw: bytes | str) -> str:
    """Extract thread_id from a serialised thread-index entry."""
    try:
        data = orjson.loads(raw)
        return data.get("thread_id", "")
    except Exception:
        return ""
