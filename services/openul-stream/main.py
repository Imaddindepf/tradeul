"""
OpenUL Stream Service

Ultra-low-latency breaking news stream.
Ingests from source, publishes to Redis Stream + Pub/Sub,
and exposes SSE + REST endpoints for frontend consumption.
"""

import asyncio
import json
import logging
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import FastAPI, Query as QueryParam, HTTPException, Request, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import structlog
import redis.asyncio as aioredis

from config import settings
from stream_consumer import XFilteredStreamConsumer

logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO, force=True)

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=False,
)

logger = structlog.get_logger(__name__)

redis_client: Optional[aioredis.Redis] = None
consumer: Optional[XFilteredStreamConsumer] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client, consumer

    logger.info("starting_openul_service")

    redis_url = f"redis://:{settings.redis_password}@{settings.redis_host}:{settings.redis_port}" if settings.redis_password else f"redis://{settings.redis_host}:{settings.redis_port}"

    redis_client = await aioredis.from_url(redis_url, encoding="utf-8", decode_responses=True)
    await redis_client.ping()
    logger.info("redis_connected")

    consumer = XFilteredStreamConsumer(redis_client)
    await consumer.start()
    logger.info("stream_consumer_started")

    yield

    logger.info("shutting_down")
    if consumer:
        await consumer.stop()
    if redis_client:
        await redis_client.close()
    logger.info("shutdown_complete")


app = FastAPI(
    title="OpenUL Stream Service",
    description="Ultra-low-latency breaking news stream",
    version="1.0.0",
    lifespan=lifespan,
)


# ── Health ──────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "openul-stream"}


@app.get("/status")
async def status():
    redis_ok = False
    try:
        if redis_client:
            await redis_client.ping()
            redis_ok = True
    except Exception:
        pass

    return {
        "status": "ok" if redis_ok and consumer else "degraded",
        "redis": "connected" if redis_ok else "disconnected",
        "consumer": consumer.get_stats() if consumer else {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── SSE Endpoint (real-time push to frontend) ──────────────────────────

@app.get("/api/v1/stream")
async def sse_stream(request: Request):
    """
    Server-Sent Events endpoint.
    Frontend connects here for real-time breaking news push.
    Uses Redis Pub/Sub for instant delivery.
    """
    async def event_generator():
        if not redis_client:
            yield f"data: {json.dumps({'error': 'redis not available'})}\n\n"
            return

        pubsub = redis_client.pubsub()
        await pubsub.subscribe("openul:live")

        try:
            yield f"data: {json.dumps({'type': 'connected', 'ts': datetime.now(timezone.utc).isoformat()})}\n\n"

            while True:
                if await request.is_disconnected():
                    break

                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg and msg["type"] == "message":
                    yield f"data: {msg['data']}\n\n"
                else:
                    yield f": keepalive {int(time.time())}\n\n"
                    await asyncio.sleep(15)

        finally:
            await pubsub.unsubscribe("openul:live")
            await pubsub.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── REST: Latest news ──────────────────────────────────────────────────

@app.get("/api/v1/news")
async def get_news(
    limit: int = QueryParam(50, ge=1, le=500, description="Number of items"),
    before_ts: Optional[float] = QueryParam(None, description="Get items before this timestamp (for pagination)"),
):
    """
    Get latest breaking news from sorted set.
    Ordered by received timestamp descending.
    """
    if not redis_client:
        raise HTTPException(status_code=503, detail="Service not ready")

    try:
        if before_ts:
            raw = await redis_client.zrevrangebyscore(
                settings.redis_latest_key,
                max=before_ts,
                min="-inf",
                start=0,
                num=limit,
            )
        else:
            raw = await redis_client.zrevrange(settings.redis_latest_key, 0, limit - 1)

        items = []
        for entry in raw:
            try:
                items.append(json.loads(entry))
            except json.JSONDecodeError:
                continue

        return {"status": "OK", "count": len(items), "results": items}

    except Exception as e:
        logger.error("get_news_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ── Ingest: External news sources (e.g. OOC bot) ──────────────────────

class IngestItem(BaseModel):
    text: str
    source: str = "external"
    source_id: Optional[str] = None


@app.post("/api/v1/ingest", status_code=202)
async def ingest_news(
    item: IngestItem,
    x_ingest_key: Optional[str] = Header(default=None, alias="x-ingest-key"),
):
    """
    Ingest a breaking news item from an external source (e.g. OOC Telegram bot).
    Publishes directly to Redis so it appears in the SSE stream and history.
    Requires header: x-ingest-key matching INGEST_SECRET env var.
    """
    if settings.ingest_secret and x_ingest_key != settings.ingest_secret:
        raise HTTPException(status_code=401, detail="Invalid ingest key")

    if not redis_client:
        raise HTTPException(status_code=503, detail="Service not ready")

    text = item.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")

    now_utc = datetime.now(timezone.utc)
    ticker_re = __import__("re").compile(r'\$([A-Z]{1,5})\b')
    tickers = list(dict.fromkeys(ticker_re.findall(text)))

    source_id = item.source_id or f"{item.source}_{int(now_utc.timestamp() * 1000)}"

    news_item = {
        "id": f"trd_{source_id}",
        "text": text,
        "tickers": tickers,
        "source": "tradeul",
        "created_at": now_utc.isoformat(),
        "received_at": now_utc.isoformat(),
        "received_ts": now_utc.timestamp(),
    }

    try:
        payload = json.dumps(news_item)
        pipe = redis_client.pipeline()
        pipe.xadd(settings.redis_stream_key, {"data": payload},
                  maxlen=settings.redis_stream_maxlen, approximate=True)
        pipe.zadd(settings.redis_latest_key, {payload: now_utc.timestamp()})
        pipe.zremrangebyrank(settings.redis_latest_key, 0, -(settings.redis_latest_maxlen + 1))
        pipe.publish("openul:live", payload)
        await pipe.execute()
    except Exception as e:
        logger.error("ingest_redis_error", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to publish news")

    logger.info("ingest_published", id=news_item["id"], source=item.source,
                text_preview=text[:80])
    return {"status": "ok", "id": news_item["id"]}


# ── REST: Stream history (Redis Stream XRANGE) ─────────────────────────

@app.get("/api/v1/history")
async def get_history(
    count: int = QueryParam(100, ge=1, le=1000, description="Number of items"),
    last_id: Optional[str] = QueryParam(None, description="Last stream ID for pagination"),
):
    """
    Read from Redis Stream directly (XREVRANGE).
    Useful for backfilling on reconnect.
    """
    if not redis_client:
        raise HTTPException(status_code=503, detail="Service not ready")

    try:
        end = last_id if last_id else "+"
        entries = await redis_client.xrevrange(settings.redis_stream_key, max=end, count=count)

        items = []
        for entry_id, fields in entries:
            try:
                item = json.loads(fields.get("data", "{}"))
                item["stream_id"] = entry_id
                items.append(item)
            except json.JSONDecodeError:
                continue

        return {"status": "OK", "count": len(items), "results": items}

    except Exception as e:
        logger.error("get_history_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ── Main ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.service_port,
        reload=False,
        log_level=settings.log_level.lower(),
    )
