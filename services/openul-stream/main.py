"""
OpenUL Stream Service

Ultra-low-latency breaking news stream.
Ingests from source, publishes to Redis Stream + Pub/Sub,
and exposes SSE + REST endpoints for frontend consumption.
"""

import asyncio
import json
import logging
import socket
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import FastAPI, Query as QueryParam, HTTPException, Request, Header, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import structlog
import redis.asyncio as aioredis

from config import settings
from stream_consumer import XFilteredStreamConsumer
from trader_auth import verify_trader_key_ws, verify_trader_key_http, TraderSession

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
last_news_published_at: float = 0.0  # epoch timestamp de la última noticia publicada


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client, consumer

    logger.info("starting_openul_service")

    redis_url = f"redis://:{settings.redis_password}@{settings.redis_host}:{settings.redis_port}" if settings.redis_password else f"redis://{settings.redis_host}:{settings.redis_port}"

    redis_client = await aioredis.from_url(
        redis_url,
        encoding="utf-8",
        decode_responses=True,
        socket_keepalive=True,
        socket_keepalive_options={
            socket.TCP_KEEPIDLE:  60,   # iniciar keepalive tras 60s sin actividad
            socket.TCP_KEEPINTVL: 10,   # sondear cada 10s
            socket.TCP_KEEPCNT:    3,   # cerrar tras 3 sondeos fallidos (~30s)
        },
    )
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


@app.get("/feed-status")
async def feed_status():
    """
    Estado público del feed de noticias.
    Permite a traders verificar que el stream está vivo sin necesitar auth.
    """
    redis_ok = False
    try:
        if redis_client:
            await redis_client.ping()
            redis_ok = True
    except Exception:
        pass

    since: int | None = None
    if last_news_published_at:
        since = int(time.time() - last_news_published_at)

    return {
        "feed": "live" if redis_ok else "degraded",
        "last_news_ago_seconds": since,
        "ts": int(time.time()),
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
        global last_news_published_at
        last_news_published_at = time.time()
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


# ── Trader WebSocket Stream (autenticado) ───────────────────────────────────

def _sanitize_for_trader(item: dict) -> dict:
    """
    Filtra los campos internos antes de enviar al trader externo.
    Solo expone campos públicos — sin fuentes, metadatos internos ni IDs de infraestructura.
    """
    # Campos base siempre presentes
    out: dict = {
        "type": "news",
        "id":         item.get("id", ""),
        "text":       item.get("text", ""),
        "tickers":    item.get("tickers", []),
        "created_at": item.get("created_at", ""),
    }

    # Campos opcionales de noticias
    if item.get("media"):
        out["media"] = item["media"]
    if item.get("urls"):
        out["urls"] = item["urls"]

    # Campos extra de reacciones de precio
    item_type = item.get("type", "")
    if item_type == "reaction":
        out["type"] = "reaction"
        for field in ("direction", "change_pct", "price", "ref_price", "delay_seconds"):
            if field in item:
                out[field] = item[field]

    return out


@app.websocket("/stream")
async def trader_ws_stream(websocket: WebSocket):
    """
    WebSocket endpoint para traders programáticos.

    Autenticación:
      - Header:      Authorization: Bearer opn_xxx
      - Query param: ?api_key=opn_xxx  (para clientes que no soportan headers WS)

    Protocolo de mensajes (servidor → trader):
      { "type": "connected",  "key_id": "...", "ts": "..." }
      { "type": "news",       "id": "...", "text": "...", "tickers": [...], "created_at": "..." }
      { "type": "ping",       "ts": 1234567890 }

    Filtrado (trader → servidor, opcional):
      { "action": "subscribe", "tickers": ["TSLA", "NVDA"] }
      { "action": "subscribe", "tickers": [] }   ← recibe todo el feed
    """
    if not redis_client:
        await websocket.close(code=1011, reason="Service not ready")
        return

    trader: TraderSession = await verify_trader_key_ws(websocket, redis_client)

    await websocket.accept()
    logger.info("trader_ws_connected", key_id=trader.key_id, name=trader.name)

    subscribed_tickers: set = set()

    await websocket.send_json({
        "type": "connected",
        "key_id": trader.key_id,
        "rate_limit": trader.rate_limit,
        "ts": datetime.now(timezone.utc).isoformat(),
    })

    # ── Canal de heartbeat privado por conexión ──────────────────────────
    # Publicamos en este canal periódicamente y verificamos que lo
    # recibimos de vuelta, garantizando que el circuito Redis → WS funciona.
    hb_channel = f"openul:hb:{trader.key_id}:{int(time.time())}"

    async def _make_pubsub() -> aioredis.client.PubSub:
        ps = redis_client.pubsub()
        await ps.subscribe("openul:live", hb_channel)
        return ps

    pubsub = await _make_pubsub()

    PING_INTERVAL    = 30    # segundos entre pings al cliente
    HB_INTERVAL      = 120   # segundos entre heartbeats de Redis
    HB_TIMEOUT       = 15    # segundos máximos esperando el heartbeat de vuelta
    RESUB_INTERVAL   = 600   # refrescar suscripción cada 10 min por seguridad

    last_ping  = time.time()
    last_hb    = time.time()
    last_resub = time.time()
    hb_pending = False
    hb_sent_at = 0.0

    try:
        while True:
            now = time.time()

            # ── Leer mensaje del cliente (no bloqueante) ─────────────────
            try:
                msg_text = await asyncio.wait_for(websocket.receive_text(), timeout=0.05)
                try:
                    msg = json.loads(msg_text)
                    action = msg.get("action")
                    if action == "subscribe":
                        tickers = msg.get("tickers", [])
                        subscribed_tickers = {t.upper() for t in tickers if isinstance(t, str)}
                        await websocket.send_json({
                            "type": "subscribed",
                            "tickers": list(subscribed_tickers) or ["*"],
                        })

                    elif action == "status":
                        # El cliente pregunta si el feed está vivo
                        since = int(time.time() - last_news_published_at) if last_news_published_at else None
                        await websocket.send_json({
                            "type": "status",
                            "feed": "live",
                            "pubsub": "active",
                            "last_news_ago_seconds": since,
                            "ts": int(time.time()),
                        })

                except (json.JSONDecodeError, Exception):
                    pass
            except asyncio.TimeoutError:
                pass

            # ── Mensajes de Redis (noticias + heartbeat) ─────────────────
            try:
                redis_msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
            except Exception as redis_err:
                logger.error("trader_ws_redis_read_error", key_id=trader.key_id, error=str(redis_err))
                # El canal Redis murió — intentar reconectar
                try:
                    await pubsub.close()
                except Exception:
                    pass
                await asyncio.sleep(1)
                try:
                    pubsub = await _make_pubsub()
                    last_resub = now
                    hb_pending = False
                    logger.info("trader_ws_pubsub_reconnected", key_id=trader.key_id)
                except Exception as reconnect_err:
                    logger.error("trader_ws_pubsub_reconnect_failed", key_id=trader.key_id, error=str(reconnect_err))
                    break
                continue

            if redis_msg and redis_msg["type"] == "message":
                if redis_msg["channel"] == hb_channel:
                    # Heartbeat confirmado — el circuito Redis → WS está vivo
                    hb_pending = False
                    logger.info("trader_ws_heartbeat_ok", key_id=trader.key_id)
                else:
                    try:
                        item = json.loads(redis_msg["data"])
                        if subscribed_tickers:
                            item_tickers = {t.upper() for t in item.get("tickers", [])}
                            if not item_tickers.intersection(subscribed_tickers):
                                continue
                        await websocket.send_json(_sanitize_for_trader(item))
                    except Exception:
                        pass

            # ── Heartbeat Redis: verificar el circuito completo ───────────
            # Publicamos en nuestro canal privado y esperamos recibirlo.
            # Si no llega en HB_TIMEOUT segundos, el pubsub está roto.
            if not hb_pending and now - last_hb >= HB_INTERVAL:
                await redis_client.publish(hb_channel, "1")
                hb_pending = True
                hb_sent_at = now
                last_hb = now

            if hb_pending and now - hb_sent_at > HB_TIMEOUT:
                logger.warning("trader_ws_heartbeat_timeout", key_id=trader.key_id)
                try:
                    await pubsub.close()
                except Exception:
                    pass
                pubsub = await _make_pubsub()
                last_resub = now
                hb_pending = False
                logger.info("trader_ws_pubsub_reconnected_after_hb_timeout", key_id=trader.key_id)

            # ── Refresco periódico de la suscripción (cada 10 min) ────────
            # Previene suscripciones stale sin necesidad de heartbeat fallido.
            if now - last_resub >= RESUB_INTERVAL:
                try:
                    await pubsub.unsubscribe("openul:live", hb_channel)
                    await pubsub.subscribe("openul:live", hb_channel)
                    last_resub = now
                    logger.info("trader_ws_pubsub_refreshed", key_id=trader.key_id)
                except Exception as resub_err:
                    logger.warning("trader_ws_resub_error", key_id=trader.key_id, error=str(resub_err))

            # ── Ping periódico al cliente (keepalive WS) ─────────────────
            if now - last_ping >= PING_INTERVAL:
                await websocket.send_json({"type": "ping", "ts": int(now)})
                last_ping = now

    except WebSocketDisconnect:
        logger.info("trader_ws_disconnected", key_id=trader.key_id)
    except Exception as e:
        logger.error("trader_ws_error", key_id=trader.key_id, error=str(e))
    finally:
        try:
            await pubsub.unsubscribe("openul:live", hb_channel)
            await pubsub.close()
        except Exception:
            pass


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
