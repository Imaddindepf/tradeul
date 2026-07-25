"""
Futuros (categoría "commodities" de FMP) — módulo del FMP Indices Connector.

Los futuros COMPARTEN la única conexión WebSocket de la cuenta con los índices
(socket.financialmodelingprep.com admite doble suscripción: verificado ACK 200
en fmp-commodity-stream + ticks reales 2026-07-25), por eso viven como módulo
de fmp_indices y no como servicio aparte. Todo lo demás (config, estado, seed,
fallback REST) está encapsulado aquí; main.py solo llama a los hooks:

    await futures.subscribe(ws)          # 2ª suscripción en el mismo WS
    futures.touch(fmp_symbol, source)    # clasifica y actualiza contadores
    await futures.seed_metadata(db)      # upsert en tickers_unified
    await futures.poll_once(process_fn)  # prime / fallback REST
    futures.rest_loop(process_fn)        # loop de fallback (staleness check)
    futures.stats                        # merge en /health

Cobertura: 40 contratos continuos front-month (ES/NQ/YM/RTY, tipos ZT-ZB+ZQ,
energía, metales, agro, DXY). Símbolo FMP como canónico interno (ESUSD...):
sin colisiones con equities y sin capa de traducción.
"""

import asyncio
import json
import os
import time
from typing import Any, Callable, Coroutine, Dict

import aiohttp

from shared.config.settings import settings
from shared.utils.logger import get_logger

logger = get_logger(__name__)

# ── Config ──────────────────────────────────────────────────────────────────
ENABLED = os.getenv("ENABLE_FUTURES", "true").lower() == "true"
STREAM = os.getenv("FMP_COMMODITY_STREAM", "fmp-commodity-stream")
BATCH_URL = "https://financialmodelingprep.com/stable/batch-commodity-quotes"
LIST_URL = "https://financialmodelingprep.com/stable/commodities-list"
REST_POLL_SECS = int(os.getenv("FUTURES_REST_POLL_SECS", "10"))
STALE_WS_SECS = int(os.getenv("STALE_WS_SECS", "60"))

# ── Estado ──────────────────────────────────────────────────────────────────
symbols: set = set()

stats: Dict[str, Any] = {
    "ws_futures_messages": 0,
    "futures_rest_polls": 0,
    "last_futures_data_ts": 0.0,
    "futures_symbols": 0,
    "futures_seeded": 0,
}

ProcessFn = Callable[[dict, str], Coroutine[Any, Any, None]]


# ── Hooks ───────────────────────────────────────────────────────────────────
async def subscribe(ws) -> None:
    """2ª suscripción sobre la conexión WS compartida (única por cuenta)."""
    if not ENABLED:
        return
    await ws.send(json.dumps({"event": "subscribe", "data": {"stream": STREAM}}))
    logger.info("fmp_ws_subscribed", stream=STREAM)


def touch(fmp_symbol: str, source: str) -> bool:
    """True si el símbolo es un futuro; actualiza contadores de frescura."""
    if fmp_symbol not in symbols:
        return False
    stats["last_futures_data_ts"] = time.time()
    if source == "ws":
        stats["ws_futures_messages"] += 1
    return True


async def poll_once(process_quote: ProcessFn) -> int:
    """Un poll del batch REST (40 futuros en 1 llamada)."""
    async with aiohttp.ClientSession() as session:
        async with session.get(
            BATCH_URL,
            params={"apikey": settings.FMP_API_KEY},
            timeout=aiohttp.ClientTimeout(total=20),
        ) as resp:
            if resp.status != 200:
                logger.warning("fmp_futures_batch_http", status=resp.status)
                return 0
            quotes = await resp.json()
    stats["futures_rest_polls"] += 1
    for q in quotes or []:
        # El batch es autoritativo para el universo: un símbolo nuevo entra
        # al set y al pipeline sin necesidad de deploy.
        sym = q.get("symbol")
        if sym:
            symbols.add(sym)
        await process_quote(q, "rest")
    stats["futures_symbols"] = len(symbols)
    return len(quotes or [])


async def rest_loop(process_quote: ProcessFn) -> None:
    """
    Fallback REST: sondea el batch mientras el stream WS de commodities no
    esté sirviendo datos frescos. Con el WS emitiendo, se queda en silencio.
    """
    while True:
        await asyncio.sleep(REST_POLL_SECS)
        if time.time() - stats["last_futures_data_ts"] < STALE_WS_SECS:
            continue
        try:
            await poll_once(process_quote)
        except Exception as e:
            logger.warning("fmp_futures_rest_error", error=str(e))


async def seed_metadata(db) -> None:
    """
    Upsert de los ~40 futuros FMP en tickers_unified (market='commodities').
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                LIST_URL,
                params={"apikey": settings.FMP_API_KEY},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    logger.error("futures_seed_list_http", status=resp.status)
                    return
                commodity_list = await resp.json()
    except Exception as e:
        logger.error("futures_seed_list_error", error=str(e))
        return

    rows = []
    for item in commodity_list or []:
        fmp_symbol = item.get("symbol")
        if not fmp_symbol or len(fmp_symbol) > 10:
            continue
        symbols.add(fmp_symbol)
        rows.append((
            fmp_symbol,
            (item.get("name") or "")[:255],
            "FUTURES",                    # exchange
            "commodities",                # market
            "FUTURE",                     # type
            (item.get("currency") or "USD")[:20],
        ))
    stats["futures_symbols"] = len(symbols)

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
            WHERE tickers_unified.market = 'commodities'
               OR tickers_unified.company_name IS NULL
            """,
            rows,
        )
        stats["futures_seeded"] = len(rows)
        logger.info("futures_metadata_seeded", count=len(rows))
    except Exception as e:
        logger.error("futures_seed_upsert_error", error=str(e))
