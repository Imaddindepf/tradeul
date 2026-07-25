"""
FMP Forex Connector — pares de divisas spot en tiempo real vía FMP.

Fuente primaria: WebSocket legacy DEDICADO wss://forex.financialmodelingprep.com
(suscripción por ticker). Su límite de conexión es INDEPENDIENTE del socket de
índices/futuros (verificado 2026-07-25: login+subscribe 200 con la conexión de
fmp_indices ocupada — por eso forex es un servicio aparte y no un módulo).
Fallback: polling REST `stable/batch-forex-quotes` cuando el WS lleva
>STALE_WS_SECS sin datos.

FMP lista ~1550 pares; ingerirlos todos inflaría minute_bars y el stream de
aggregates sin valor. Se ingiere un set CURADO (majors, crosses líquidos, EM
principales y oro/plata spot), ampliable vía env FOREX_SYMBOLS.

Publica con el MISMO patrón que fmp_indices (pipeline aguas abajo compartido):

  - stream:realtime:aggregates        → websocket_server → chart en vivo
  - stream:realtime:quotes            → canal QUOTE (bid/ask reales si el WS los da)
  - tabla minute_bars (TimescaleDB)   → histórico intradía + stitching
  - hash snapshot:forex:latest        → REST /api/v1/realtime/*

El símbolo FMP (EURUSD, XAUUSD...) es el canónico interno: sin colisiones con
equities y sin capa de traducción.

Al arrancar hace el seed de metadata en tickers_unified (market='forex').
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
from shared.contracts.realtime import build_realtime_aggregate_payload
from shared.utils.logger import configure_logging, get_logger
from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient

configure_logging(service_name="fmp_forex")
logger = get_logger(__name__)

# ── Config ──────────────────────────────────────────────────────────────────
FMP_FOREX_WS_URL = os.getenv("FMP_FOREX_WS_URL", "wss://forex.financialmodelingprep.com")
FMP_FOREX_BATCH_URL = "https://financialmodelingprep.com/stable/batch-forex-quotes"

AGGREGATES_STREAM = "stream:realtime:aggregates"
FOREX_HASH_KEY = "snapshot:forex:latest"

STALE_WS_SECS = int(os.getenv("STALE_WS_SECS", "60"))
REST_POLL_SECS = int(os.getenv("FOREX_REST_POLL_SECS", "10"))
RECONNECT_BASE_SECS = 2
RECONNECT_MAX_SECS = 60
BARS_FLUSH_BATCH = 500

_DEFAULT_FOREX = (
    # Majors
    "EURUSD,GBPUSD,USDJPY,USDCHF,USDCAD,AUDUSD,NZDUSD,"
    # Crosses EUR/GBP/JPY
    "EURGBP,EURJPY,EURCHF,EURAUD,EURCAD,GBPJPY,GBPCHF,GBPAUD,GBPCAD,"
    "AUDJPY,CADJPY,CHFJPY,NZDJPY,"
    # Crosses menores
    "AUDCAD,AUDCHF,AUDNZD,NZDCAD,CADCHF,"
    # EM / nórdicos / Asia líquidos
    "USDMXN,USDBRL,USDZAR,USDTRY,USDSEK,USDNOK,USDPLN,USDSGD,USDHKD,USDCNH,USDINR,"
    # Metales spot
    "XAUUSD,XAGUSD"
)
CURATED: List[str] = sorted({
    s.strip().upper() for s in os.getenv("FOREX_SYMBOLS", _DEFAULT_FOREX).split(",") if s.strip()
})
CURATED_SET = set(CURATED)

# ── Estado global ───────────────────────────────────────────────────────────
redis_client: Optional[RedisClient] = None
db: Optional[TimescaleClient] = None

stats = {
    "ws_connected": False,
    "ws_messages": 0,
    "rest_polls": 0,
    "published": 0,
    "skipped_dupes": 0,
    "last_data_ts": 0.0,
    "symbols": len(CURATED),
    "seeded": 0,
}


class PairState:
    """Estado por par: dedupe y vela 1-min en formación."""

    __slots__ = ("last_price", "last_ts", "bar_minute", "bar")

    def __init__(self):
        self.last_price: Optional[float] = None
        self.last_ts: int = 0
        self.bar_minute: Optional[int] = None
        self.bar: Optional[List[float]] = None  # [o, h, l, c]


states: Dict[str, PairState] = {}
pending_bar_rows: List[tuple] = []


# ── Publicación ─────────────────────────────────────────────────────────────
async def process_quote(q: dict, source: str) -> None:
    """
    Procesa un quote de forex (WS o REST) ya normalizado:
    {symbol, price, [change], [timestamp], [bid], [ask]}
    """
    symbol = q.get("symbol")
    price = q.get("price")
    if not symbol or price is None or price <= 0 or symbol not in CURATED_SET:
        return

    ts = int(q.get("timestamp") or 0)

    st = states.get(symbol)
    if st is None:
        st = states[symbol] = PairState()

    if price == st.last_price and ts == st.last_ts:
        stats["skipped_dupes"] += 1
        return

    st.last_price = price
    st.last_ts = ts
    stats["last_data_ts"] = time.time()
    if source == "ws":
        stats["ws_messages"] += 1

    now_ms = int(time.time() * 1000)
    epoch_min = now_ms // 60_000

    # ── Vela 1-min en formación ──
    if st.bar_minute is None or st.bar is None:
        st.bar_minute = epoch_min
        st.bar = [price, price, price, price]
    elif epoch_min != st.bar_minute:
        pending_bar_rows.append((
            symbol, st.bar_minute * 60_000,
            st.bar[0], st.bar[1], st.bar[2], st.bar[3], 0,
        ))
        st.bar_minute = epoch_min
        st.bar = [price, price, price, price]
    else:
        st.bar[1] = max(st.bar[1], price)
        st.bar[2] = min(st.bar[2], price)
        st.bar[3] = price

    # ── Aggregate canónico → chart en vivo ──
    payload = build_realtime_aggregate_payload(
        symbol=symbol,
        open_=st.bar[0],
        high=st.bar[1],
        low=st.bar[2],
        close=price,
        volume=0,
        volume_accumulated=0,
        vwap=price,
        avg_trade_size=0.0,
        trades=1,
        timestamp_start_ms=now_ms - 1000,
        timestamp_end_ms=now_ms,
        otc=False,
    )
    try:
        await redis_client.publish_to_stream(AGGREGATES_STREAM, payload)
        stats["published"] += 1
    except Exception as e:
        logger.debug("forex_stream_publish_error", symbol=symbol, error=str(e))

    # ── Quote → canal QUOTE (bid/ask reales si el WS los trae) ──
    bid = q.get("bid") or price
    ask = q.get("ask") or price
    try:
        await redis_client.publish_to_stream(
            "stream:realtime:quotes",
            {
                "symbol": symbol,
                "bid_price": str(bid),
                "bid_size": "0",
                "ask_price": str(ask),
                "ask_size": "0",
                "bid_exchange": "",
                "ask_exchange": "",
                "timestamp": str(now_ms),
                "tape": "",
            },
        )
    except Exception as e:
        logger.debug("forex_quote_publish_error", symbol=symbol, error=str(e))

    # ── Hash de snapshot ──
    change = q.get("change")
    change_pct = q.get("changePercentage")
    if change_pct is None and change is not None and price != change:
        change_pct = round(change / (price - change) * 100, 5)
    prev_close = round(price - change, 6) if change is not None else None
    try:
        entry = orjson.dumps({
            "symbol": symbol,
            "fmp_symbol": symbol,
            "asset_class": "forex",
            "name": _pair_name(symbol),
            "price": price,
            "bid": bid if bid != price else None,
            "ask": ask if ask != price else None,
            "change": change,
            "change_percent": change_pct,
            "previous_close": prev_close,
            "volume": 0,
            "timestamp": ts,
            "source": source,
            "updated_at": now_ms,
        }).decode()
        await redis_client.client.hset(FOREX_HASH_KEY, symbol, entry)
    except Exception as e:
        logger.debug("forex_hash_error", symbol=symbol, error=str(e))


def _pair_name(pair: str) -> str:
    base, quote = pair[:3], pair[3:]
    pretty = {"XAU": "Gold Spot", "XAG": "Silver Spot"}.get(base)
    return f"{pretty} ({quote})" if pretty else f"{base} / {quote}"


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
            logger.error("forex_bars_persist_error", error=str(e), rows=len(rows))


# ── WebSocket (fuente primaria) ─────────────────────────────────────────────
def _ssl_contexts():
    verified = ssl.create_default_context()
    insecure = ssl.create_default_context()
    insecure.check_hostname = False
    insecure.verify_mode = ssl.CERT_NONE
    return [verified, insecure]


def _parse_ws_message(d: dict) -> Optional[dict]:
    """
    Adaptador tolerante del mensaje WS legacy → shape de process_quote.
    Formato esperado (por-ticker legacy): {s|symbol, t (ms), lp|price|bp/ap...}.
    El shape exacto se valida con fx_ws_sample en los logs la primera sesión.
    """
    sym = (d.get("s") or d.get("symbol") or "").upper()
    if not sym:
        return None
    price = d.get("lp") or d.get("price")
    bid = d.get("bp") or d.get("bid")
    ask = d.get("ap") or d.get("ask")
    if price is None:
        if bid and ask:
            price = (float(bid) + float(ask)) / 2
        else:
            price = bid or ask
    if not price:
        return None
    ts_raw = d.get("t") or d.get("timestamp") or 0
    ts = int(ts_raw / 1000) if ts_raw and ts_raw > 1e12 else int(ts_raw)
    out = {"symbol": sym, "price": float(price), "timestamp": ts}
    if bid:
        out["bid"] = float(bid)
    if ask:
        out["ask"] = float(ask)
    return out


async def ws_consumer_loop() -> None:
    backoff = RECONNECT_BASE_SECS
    while True:
        try:
            connected = False
            for ctx in _ssl_contexts():
                try:
                    async with websockets.connect(
                        FMP_FOREX_WS_URL, ssl=ctx, open_timeout=15, ping_interval=None
                    ) as ws:
                        connected = True
                        backoff = RECONNECT_BASE_SECS
                        await _ws_session(ws)
                except ssl.SSLError as e:
                    logger.warning("fmp_forex_ws_ssl_error", error=str(e))
                    continue
                break
            if not connected:
                raise ConnectionError("no SSL context worked")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            stats["ws_connected"] = False
            logger.warning("fmp_forex_ws_disconnected", error=str(e), retry_in=backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, RECONNECT_MAX_SECS)


async def _ws_session(ws) -> None:
    await ws.send(json.dumps({"event": "login", "data": {"apiKey": settings.FMP_API_KEY}}))

    logged_in = False
    for _ in range(10):
        msg = await asyncio.wait_for(ws.recv(), timeout=20)
        d = json.loads(msg)
        if d.get("event") == "login":
            status = (d.get("data") or {}).get("status", d.get("status"))
            if status == 200:
                logged_in = True
                break
            raise ConnectionError(f"FMP forex login failed: {msg[:200]}")
    if not logged_in:
        raise ConnectionError("FMP forex login ack not received")

    # Suscripción por ticker (protocolo legacy: lowercase)
    await ws.send(json.dumps({
        "event": "subscribe",
        "data": {"ticker": [p.lower() for p in CURATED]},
    }))
    stats["ws_connected"] = True
    logger.info("fmp_forex_ws_subscribed", pairs=len(CURATED))

    samples_logged = 0
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
            logger.info("fmp_forex_ws_meta", message=str(d)[:200])
            continue
        if ev == "error" or (isinstance(d.get("status"), int) and d["status"] >= 400):
            logger.warning("fmp_forex_ws_error_event", message=str(d)[:200])
            continue
        # Validación del shape real del feed en la primera sesión
        if samples_logged < 3:
            samples_logged += 1
            logger.info("fx_ws_sample", message=str(d)[:300])
        parsed = _parse_ws_message(d)
        if parsed:
            await process_quote(parsed, source="ws")


# ── REST fallback ───────────────────────────────────────────────────────────
async def poll_batch_once() -> int:
    """Un poll del batch (~1550 pares en 1 llamada; se ingiere el set curado)."""
    async with aiohttp.ClientSession() as session:
        async with session.get(
            FMP_FOREX_BATCH_URL,
            params={"apikey": settings.FMP_API_KEY},
            timeout=aiohttp.ClientTimeout(total=20),
        ) as resp:
            if resp.status != 200:
                logger.warning("fmp_forex_batch_http", status=resp.status)
                return 0
            quotes = await resp.json()
    stats["rest_polls"] += 1
    count = 0
    for q in quotes or []:
        if q.get("symbol") in CURATED_SET:
            await process_quote(q, source="rest")
            count += 1
    return count


async def rest_fallback_loop() -> None:
    """Si el WS lleva STALE_WS_SECS sin datos, sondear el batch REST."""
    while True:
        await asyncio.sleep(REST_POLL_SECS)
        if time.time() - stats["last_data_ts"] < STALE_WS_SECS:
            continue
        try:
            await poll_batch_once()
        except Exception as e:
            logger.warning("fmp_forex_rest_error", error=str(e))


# ── Seed de metadata ────────────────────────────────────────────────────────
async def seed_forex_metadata() -> None:
    """Upsert del set curado en tickers_unified (market='forex')."""
    rows = []
    for pair in CURATED:
        if len(pair) > 10:
            continue
        rows.append((
            pair, _pair_name(pair)[:255], "FOREX", "forex", "FX", pair[3:][:20],
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
            WHERE tickers_unified.market = 'forex'
               OR tickers_unified.company_name IS NULL
            """,
            rows,
        )
        stats["seeded"] = len(rows)
        logger.info("forex_metadata_seeded", count=len(rows))
    except Exception as e:
        logger.error("forex_seed_upsert_error", error=str(e))


# ── Lifecycle ───────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client, db

    logger.info("fmp_forex_starting", ws_url=FMP_FOREX_WS_URL, pairs=len(CURATED))

    redis_client = RedisClient()
    await redis_client.connect()

    db = TimescaleClient()
    await db.connect()

    await seed_forex_metadata()

    # Prime del snapshot: los pares disponibles desde el segundo cero
    try:
        primed = await poll_batch_once()
        logger.info("forex_snapshot_primed", quotes=primed)
    except Exception as e:
        logger.warning("forex_snapshot_prime_error", error=str(e))

    ws_task = asyncio.create_task(ws_consumer_loop())
    poll_task = asyncio.create_task(rest_fallback_loop())
    flush_task = asyncio.create_task(flush_bars_loop())

    yield

    for t in (ws_task, poll_task, flush_task):
        t.cancel()
    await db.disconnect()
    await redis_client.disconnect()
    logger.info("fmp_forex_stopped")


app = FastAPI(title="FMP Forex Connector", lifespan=lifespan)


@app.get("/health")
async def health():
    age = time.time() - stats["last_data_ts"] if stats["last_data_ts"] else None
    return {
        "status": "healthy" if stats["ws_connected"] or (age and age < 120) else "degraded",
        "ws_connected": stats["ws_connected"],
        "last_data_age_secs": round(age, 1) if age else None,
        **{k: v for k, v in stats.items() if k != "last_data_ts"},
    }


@app.get("/forex")
async def list_current():
    """Snapshot actual del set curado de pares."""
    raw = await redis_client.client.hgetall(FOREX_HASH_KEY)
    return {k: orjson.loads(v) for k, v in raw.items()}
