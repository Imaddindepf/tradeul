"""
Shared publisher for OpenUL news items.

Single source of truth for how a news item lands in Redis. Guarantees that
the `stream_id` (assigned by XADD) is included in the JSON payload that
goes into the sorted set AND the Pub/Sub channel, so that SSE consumers
can use it as the SSE `id:` line and resume from `Last-Event-ID` after a
disconnect without losing or duplicating messages.

Flow:
    1.  XADD openul:news  →  Redis returns the new stream id (e.g. 1780489213884-0)
    2.  Stamp the id back into the item as `stream_id`
    3.  Pipeline: ZADD openul:latest, ZREMRANGEBYRANK trim, PUBLISH openul:live
"""
from __future__ import annotations

import json
from typing import Any, Dict

import redis.asyncio as aioredis

from config import settings


async def publish_news_item(
    redis_client: aioredis.Redis,
    item: Dict[str, Any],
) -> str:
    """
    Publish a news item to the Redis Stream + Sorted Set + Pub/Sub channel.

    Mutates `item` to include the assigned `stream_id`. Returns the stream id.

    Raises any underlying redis error so the caller can surface the failure.
    """
    # Step 1: XADD first so we know the stream id before we publish.
    # We serialise twice because `item["stream_id"]` only exists after XADD.
    initial_payload = json.dumps(item)
    stream_id: str = await redis_client.xadd(
        settings.redis_stream_key,
        {"data": initial_payload},
        maxlen=settings.redis_stream_maxlen,
        approximate=True,
    )

    # Step 2: stamp the stream id into the item so it travels with every
    # downstream consumer (sorted set, Pub/Sub, SSE).
    item["stream_id"] = stream_id
    payload = json.dumps(item)

    # Step 3: ZADD + trim + PUBLISH in a single round-trip. Score is the
    # received timestamp so the sorted set stays ordered chronologically.
    score = item.get("received_ts") or 0.0
    pipe = redis_client.pipeline()
    pipe.zadd(settings.redis_latest_key, {payload: score})
    pipe.zremrangebyrank(
        settings.redis_latest_key, 0, -(settings.redis_latest_maxlen + 1)
    )
    pipe.publish("openul:live", payload)
    await pipe.execute()

    return stream_id
