"""
FMP Indices Connector — índices bursátiles en tiempo real vía FMP.

Fuente primaria: WebSocket wss://socket.financialmodelingprep.com, stream
`fmp-index-stream` (firehose global de ~425 índices; cada mensaje es un
quote completo). Fallback: polling REST `stable/batch-index-quotes` cuando
el WS lleva >STALE_WS_SECS sin datos.

IMPORTANTE: FMP permite UNA sola conexión WS por cuenta. Este servicio debe
ser el único consumidor (cerrar el Quote Feed Connector de la web de FMP).

Publica con el MISMO patrón que analytics/internals/market_internals.py
(índices sintéticos TRDL), reutilizando todo el pipeline aguas abajo:

  - stream:realtime:aggregates        → websocket_server → chart en vivo
  - stream:agg:p{N} (flag opcional)   → alert workers (detectores TA)
  - tabla minute_bars (TimescaleDB)   → histórico intradía + stitching
  - hash snapshot:indices:latest      → REST /api/v1/realtime/ticker/{sym}

Los símbolos se publican SIEMPRE en forma interna canónica (SPX, VIX,
^GDAXI...) — ver shared/config/index_symbols.py. Este servicio es el único
punto de traducción FMP→interno del data plane.

Al arrancar hace el seed de metadata en tickers_unified (market='indices')
con comprobación de colisión: si un alias choca con una equity activa, la
equity gana y el índice conserva su símbolo FMP.
"""

import asyncio
import json
import os
import ssl
import time
from contextlib import asynccontextmanager
from typing import Dict, List, Optional

import aiohttp
import orjson
import websockets
from fastapi import FastAPI

from shared.config.settings import settings
from shared.config.index_symbols import INDEX_ALIASES, from_fmp
from shared.contracts.realtime import build_realtime_aggregate_payload
from shared.utils.logger import configure_logging, get_logger
from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient

configure_logging(service_name="fmp_indices")
logger = get_logger(__name__)

# ── Config ──────────────────────────────────────────────────────────────────
FMP_WS_URL = os.getenv("FMP_WS_URL", "wss://socket.financialmodelingprep.com")
FMP_STREAM = os.getenv("FMP_INDEX_STREAM", "fmp-index-stream")
FMP_BATCH_URL = "https://financialmodelingprep.com/stable/batch-index-quotes"
FMP_INDEX_LIST_URL = "https://financialmodelingprep.com/stable/index-list"

AGGREGATES_STREAM = "stream:realtime:aggregates"
INDICES_HASH_KEY = "snapshot:indices:latest"
NUM_ALERT_PARTITIONS = int(os.getenv("NUM_ALERT_PARTITIONS", "4"))
# Fase 3: publicar también a stream:agg:p{N} para los detectores TA del
# alert engine. Off por defecto hasta validar que los detectores digieren
# símbolos sin entrada en el enriched cache.
INDICES_TO_ALERT_STREAMS = os.getenv("INDICES_TO_ALERT_STREAMS", "false").lower() == "true"

STALE_WS_SECS = int(os.getenv("STALE_WS_SECS", "60"))          # sin datos WS → fallback REST
REST_POLL_SECS = int(os.getenv("REST_POLL_SECS", "15"))        # cadencia del fallback
RECONNECT_BASE_SECS = 2
RECONNECT_MAX_SECS = 60
BARS_FLUSH_BATCH = 500

# ── Estado global ───────────────────────────────────────────────────────────
redis_client: Optional[RedisClient] = None
db: Optional[TimescaleClient] = None
ws_task: Optional[asyncio.Task] = None
poll_task: Optional[asyncio.Task] = None

stats = {
    "ws_connected": False,
    "ws_messages": 0,
    "rest_polls": 0,
    "published": 0,
    "skipped_dupes": 0,
    "last_data_ts": 0.0,
    "symbols_seen": 0,
    "seeded": 0,
    "alias_collisions": [],
}


class IndexState:
    """Estado por símbolo: dedupe, volumen delta y vela 1-min en formación."""

    __slots__ = ("last_price", "last_ts", "last_volume", "bar_minute", "bar")

    def __init__(self):
        self.last_price: Optional[float] = None
        self.last_ts: int = 0                      # timestamp FMP (s)
        self.last_volume: int = 0                  # volumen acumulado del día
        self.bar_minute: Optional[int] = None      # epoch-minute de la vela
        self.bar: Optional[List[float]] = None     # [o, h, l, c, vol_delta]


states: Dict[str, IndexState] = {}
pending_bar_rows: List[tuple] = []


# ── Publicación ─────────────────────────────────────────────────────────────
async def process_quote(q: dict, source: str) -> None:
    """
    Procesa un quote de índice (WS o REST). Formato FMP:
    {symbol, name, price, change, changesPercentage, dayLow, dayHigh, open,
     previousClose, volume, timestamp, ...}
    """
    fmp_symbol = q.get("symbol")
    price = q.get("price")
    if not fmp_symbol or price is None or price <= 0:
        return

    symbol = from_fmp(fmp_symbol)
    ts = int(q.get("timestamp") or 0)

    st = states.get(symbol)
    if st is None:
        st = states[symbol] = IndexState()
        stats["symbols_seen"] = len(states)

    # Dedupe: mismo precio y mismo timestamp de fuente → no republicar
    # (el firehose re-broadcastea, y WS+REST pueden solaparse)
    if price == st.last_price and ts == st.last_ts:
        stats["skipped_dupes"] += 1
        return

    volume = int(q.get("volume") or 0)
    vol_delta = max(0, volume - st.last_volume) if st.last_volume else 0

    st.last_price = price
    st.last_ts = ts
    st.last_volume = volume
    stats["last_data_ts"] = time.time()

    now_ms = int(time.time() * 1000)
    epoch_min = now_ms // 60_000

    # ── Vela 1-min en formación (patrón market_internals) ──
    if st.bar_minute is None or st.bar is None:
        st.bar_minute = epoch_min
        st.bar = [price, price, price, price, vol_delta]
    elif epoch_min != st.bar_minute:
        pending_bar_rows.append((
            symbol, st.bar_minute * 60_000,
            st.bar[0], st.bar[1], st.bar[2], st.bar[3], int(st.bar[4]),
        ))
        st.bar_minute = epoch_min
        st.bar = [price, price, price, price, vol_delta]
    else:
        st.bar[1] = max(st.bar[1], price)
        st.bar[2] = min(st.bar[2], price)
        st.bar[3] = price
        st.bar[4] += vol_delta

    # ── Aggregate canónico → chart en vivo ──
    payload = build_realtime_aggregate_payload(
        symbol=symbol,
        open_=st.bar[0],
        high=st.bar[1],
        low=st.bar[2],
        close=price,
        volume=vol_delta,
        volume_accumulated=volume,
        vwap=price,
        avg_trade_size=0.0,
        trades=1,
        timestamp_start_ms=now_ms - 1000,
        timestamp_end_ms=now_ms,
        otc=False,
    )
    try:
        await redis_client.publish_to_stream(AGGREGATES_STREAM, payload)
        if INDICES_TO_ALERT_STREAMS:
            partition = hash(symbol) % NUM_ALERT_PARTITIONS
            await redis_client.publish_to_stream(
                f"stream:agg:p{partition}", payload, maxlen=50000
            )
        stats["published"] += 1
    except Exception as e:
        logger.debug("index_stream_publish_error", symbol=symbol, error=str(e))

    # ── Quote → canal QUOTE del websocket_server (QuoteMonitor/TickerSpan) ──
    # Un índice no tiene NBBO: bid = ask = valor (mid exacto, spread 0),
    # mismo shape que publica polygon_ws para que el fan-out no distinga.
    try:
        await redis_client.publish_to_stream(
            "stream:realtime:quotes",
            {
                "symbol": symbol,
                "bid_price": str(price),
                "bid_size": "0",
                "ask_price": str(price),
                "ask_size": "0",
                "bid_exchange": "",
                "ask_exchange": "",
                # ms, como los quotes de polygon_ws (el frontend formatea el reloj)
                "timestamp": str(now_ms),
                "tape": "",
            },
        )
    except Exception as e:
        logger.debug("index_quote_publish_error", symbol=symbol, error=str(e))

    # ── Hash de snapshot → REST /realtime/ticker ──
    # El batch REST viene en formato corto (sin changesPercentage ni day
    # high/low): derivar lo derivable para que los tooltips no queden vacíos.
    change = q.get("change")
    change_pct = q.get("changesPercentage") or q.get("changePercentage")
    if change_pct is None and change is not None and price != change:
        change_pct = round(change / (price - change) * 100, 5)
    prev_close = q.get("previousClose")
    if prev_close is None and change is not None:
        prev_close = round(price - change, 4)
    try:
        entry = orjson.dumps({
            "symbol": symbol,
            "fmp_symbol": fmp_symbol,
            "name": q.get("name"),
            "price": price,
            "change": change,
            "change_percent": change_pct,
            "day_low": q.get("dayLow"),
            "day_high": q.get("dayHigh"),
            "open": q.get("open"),
            "previous_close": prev_close,
            "volume": volume,
            "timestamp": ts,
            "source": source,
            "updated_at": now_ms,
        }).decode()
        await redis_client.client.hset(INDICES_HASH_KEY, symbol, entry)
    except Exception as e:
        logger.debug("index_hash_error", symbol=symbol, error=str(e))


async def flush_bars_loop() -> None:
    """Persistir velas 1-min cerradas a minute_bars en lotes."""
    global pending_bar_rows
    while True:
        await asyncio.sleep(5)
        if not pending_bar_rows or db is None:
            continue
        rows, pending_bar_rows = pending_bar_rows[:BARS_FLUSH_BATCH], pending_bar_rows[BARS_FLUSH_BATCH:]
        try:
            await db.executemany(
                """
                INSERT INTO minute_bars (symbol, ts, open, high, low, close, volume)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT DO NOTHING
                """,
                rows,
            )
        except Exception as e:
            logger.error("index_bars_persist_error", error=str(e), rows=len(rows))


# ── WebSocket (fuente primaria) ─────────────────────────────────────────────
def _ssl_contexts():
    """FMP a veces sirve una cadena TLS incompleta; probamos verificado y,
    como último recurso, sin verificar (solo datos públicos de mercado)."""
    verified = ssl.create_default_context()
    insecure = ssl.create_default_context()
    insecure.check_hostname = False
    insecure.verify_mode = ssl.CERT_NONE
    return [verified, insecure]


async def ws_consumer_loop() -> None:
    backoff = RECONNECT_BASE_SECS
    while True:
        try:
            connected = False
            for ctx in _ssl_contexts():
                try:
                    async with websockets.connect(
                        FMP_WS_URL, ssl=ctx, open_timeout=15, ping_interval=None
                    ) as ws:
                        connected = True
                        backoff = RECONNECT_BASE_SECS
                        await _ws_session(ws)
                except ssl.SSLError as e:
                    logger.warning("fmp_ws_ssl_error", error=str(e))
                    continue
                break
            if not connected:
                raise ConnectionError("no SSL context worked")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            stats["ws_connected"] = False
            logger.warning("fmp_ws_disconnected", error=str(e), retry_in=backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, RECONNECT_MAX_SECS)


async def _ws_session(ws) -> None:
    await ws.send(json.dumps({"event": "login", "data": {"apiKey": settings.FMP_API_KEY}}))

    # Esperar el ack del login ANTES de suscribir (si otra conexión ocupa el
    # slot de la cuenta, FMP responde "Maximum number of connections reached")
    logged_in = False
    for _ in range(10):
        msg = await asyncio.wait_for(ws.recv(), timeout=20)
        d = json.loads(msg)
        if d.get("event") == "login":
            status = (d.get("data") or {}).get("status", d.get("status"))
            if status == 200:
                logged_in = True
                break
            raise ConnectionError(f"FMP login failed: {msg[:200]}")
    if not logged_in:
        raise ConnectionError("FMP login ack not received")

    await ws.send(json.dumps({"event": "subscribe", "data": {"stream": FMP_STREAM}}))
    stats["ws_connected"] = True
    logger.info("fmp_ws_subscribed", stream=FMP_STREAM)

    while True:
        msg = await asyncio.wait_for(ws.recv(), timeout=STALE_WS_SECS + 30)
        try:
            d = json.loads(msg)
        except Exception:
            continue
        ev = d.get("event")
        if ev == "heartbeat":
            continue
        if ev in ("login", "subscribe", "unsubscribe"):
            logger.info("fmp_ws_meta", message=str(d)[:200])
            continue
        if ev == "error" or (isinstance(d.get("status"), int) and d["status"] >= 400):
            logger.warning("fmp_ws_error_event", message=str(d)[:200])
            continue
        if "symbol" in d and "price" in d:
            stats["ws_messages"] += 1
            await process_quote(d, source="ws")


# ── REST fallback ───────────────────────────────────────────────────────────
async def poll_batch_once() -> int:
    """Un poll del batch REST (425 índices en 1 llamada). Devuelve #quotes."""
    async with aiohttp.ClientSession() as session:
        async with session.get(
            FMP_BATCH_URL,
            params={"apikey": settings.FMP_API_KEY},
            timeout=aiohttp.ClientTimeout(total=20),
        ) as resp:
            if resp.status != 200:
                logger.warning("fmp_rest_batch_http", status=resp.status)
                return 0
            quotes = await resp.json()
    stats["rest_polls"] += 1
    for q in quotes or []:
        await process_quote(q, source="rest")
    return len(quotes or [])


async def rest_fallback_loop() -> None:
    """Si el WS lleva STALE_WS_SECS sin datos, sondear el batch REST."""
    while True:
        await asyncio.sleep(REST_POLL_SECS)
        if time.time() - stats["last_data_ts"] < STALE_WS_SECS:
            continue
        try:
            await poll_batch_once()
        except Exception as e:
            logger.warning("fmp_rest_fallback_error", error=str(e))


# ── Seed de metadata ────────────────────────────────────────────────────────
async def seed_index_metadata() -> None:
    """
    Upsert de los ~425 índices FMP en tickers_unified (market='indices').
    Colisiones: si el símbolo interno ya existe como NO-índice, la equity
    gana y el índice se registra con su símbolo FMP.
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                FMP_INDEX_LIST_URL,
                params={"apikey": settings.FMP_API_KEY},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    logger.error("index_seed_list_http", status=resp.status)
                    return
                index_list = await resp.json()
    except Exception as e:
        logger.error("index_seed_list_error", error=str(e))
        return

    rows = []
    for idx in index_list or []:
        fmp_symbol = idx.get("symbol")
        if not fmp_symbol:
            continue
        internal = from_fmp(fmp_symbol)
        # tickers_unified.symbol es varchar(10 o 20 según despliegue); la cola
        # larga con símbolos largos (DE000SLA30S3.SG) se salta sin drama.
        if len(internal) > 10:
            continue
        # Colisión: ¿existe ya como no-índice?
        if internal != fmp_symbol:
            existing = await db.fetchrow(
                "SELECT market FROM tickers_unified WHERE symbol = $1", internal
            )
            if existing and existing["market"] != "indices":
                stats["alias_collisions"].append(internal)
                logger.warning("index_alias_collision", alias=internal, fmp=fmp_symbol)
                internal = fmp_symbol
                if len(internal) > 10:
                    continue
        rows.append((
            internal,
            (idx.get("name") or "")[:255],
            "INDEX",                      # exchange
            "indices",                    # market
            "INDEX",                      # type
            (idx.get("currency") or "USD")[:20],
        ))

    if not rows:
        return
    try:
        await db.executemany(
            """
            INSERT INTO tickers_unified
                (symbol, company_name, exchange, market, type, currency_name,
                 is_active, is_actively_trading, is_etf, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, true, true, false, NOW())
            ON CONFLICT (symbol) DO UPDATE SET
                company_name = EXCLUDED.company_name,
                exchange = EXCLUDED.exchange,
                market = EXCLUDED.market,
                type = EXCLUDED.type,
                currency_name = EXCLUDED.currency_name,
                is_active = true,
                is_actively_trading = true,
                updated_at = NOW()
            WHERE tickers_unified.market = 'indices'
               OR tickers_unified.company_name IS NULL
            """,
            rows,
        )
        stats["seeded"] = len(rows)
        logger.info("index_metadata_seeded", count=len(rows),
                    collisions=stats["alias_collisions"])
    except Exception as e:
        logger.error("index_seed_upsert_error", error=str(e))


# ── Lifecycle ───────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client, db, ws_task, poll_task

    logger.info("fmp_indices_starting", ws_url=FMP_WS_URL, stream=FMP_STREAM,
                alert_streams=INDICES_TO_ALERT_STREAMS)

    redis_client = RedisClient()
    await redis_client.connect()

    db = TimescaleClient()
    await db.connect()

    await seed_index_metadata()

    # Prime del snapshot: un batch REST inicial deja los 425 índices
    # disponibles en el hash desde el segundo cero (el firehose WS solo
    # re-emite los que van actualizándose — con un mercado cerrado, su
    # índice no aparecería hasta la próxima sesión).
    try:
        primed = await poll_batch_once()
        logger.info("index_snapshot_primed", quotes=primed)
    except Exception as e:
        logger.warning("index_snapshot_prime_error", error=str(e))

    ws_task = asyncio.create_task(ws_consumer_loop())
    poll_task = asyncio.create_task(rest_fallback_loop())
    flush_task = asyncio.create_task(flush_bars_loop())

    yield

    for t in (ws_task, poll_task, flush_task):
        t.cancel()
    await db.disconnect()
    await redis_client.disconnect()
    logger.info("fmp_indices_stopped")


app = FastAPI(title="FMP Indices Connector", lifespan=lifespan)


@app.get("/health")
async def health():
    age = time.time() - stats["last_data_ts"] if stats["last_data_ts"] else None
    return {
        "status": "healthy" if stats["ws_connected"] or (age and age < 120) else "degraded",
        "ws_connected": stats["ws_connected"],
        "last_data_age_secs": round(age, 1) if age else None,
        **{k: v for k, v in stats.items() if k != "last_data_ts"},
    }


@app.get("/indices")
async def list_current():
    """Snapshot actual de todos los índices trackeados."""
    raw = await redis_client.client.hgetall(INDICES_HASH_KEY)
    return {k: orjson.loads(v) for k, v in raw.items()}
