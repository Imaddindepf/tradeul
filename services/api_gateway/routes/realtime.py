"""
Real-time ticker data endpoint
Reads from Redis Hash snapshot:enriched:latest for live data.

Uses HGET for single ticker lookups (~500 bytes instead of ~7MB).
"""

from fastapi import APIRouter, HTTPException
from typing import Optional
import orjson

from shared.config.index_symbols import normalize_index_symbol

router = APIRouter(prefix="/api/v1/realtime", tags=["realtime"])


async def _get_index_realtime(symbol: str, hash_key: str = "snapshot:indices:latest"):
    """
    Índices/futuros (hash de fmp_indices) o forex (hash de fmp_forex).
    Devuelve el mismo shape que el endpoint de equities para que el frontend
    no distinga fuentes.
    """
    raw = await redis_client.client.hget(hash_key, symbol)
    if not raw:
        raise HTTPException(status_code=404, detail=f"Index {symbol} not found in snapshot")
    q = orjson.loads(raw)
    price = q.get("price") or 0
    return {
        "symbol": symbol,
        "timestamp": q.get("updated_at"),
        "minute": {
            "time": q.get("updated_at", 0),
            "open": price, "high": price, "low": price, "close": price,
            "volume": 0,
            "volume_accumulated": q.get("volume", 0),
        },
        "day": {
            "open": q.get("open", 0),
            "high": q.get("day_high", 0),
            "low": q.get("day_low", 0),
            "close": q.get("previous_close", 0),
            "volume": q.get("volume", 0),
        },
        "last_price": price,
        "intraday_high": q.get("day_high"),
        "intraday_low": q.get("day_low"),
        "change": q.get("change"),
        "change_percent": q.get("change_percent"),
        "asset_type": q.get("asset_class", "index"),
        "delayed": False,
    }

# Redis client will be injected from main.py
redis_client = None

def set_redis_client(client):
    global redis_client
    redis_client = client


@router.get("/class/{asset_class}")
async def get_realtime_class(asset_class: str):
    """
    Snapshot completo de una clase de activo del hash de fmp_indices:
    'future' (40 futuros continuos) o 'forex' (set curado de pares).
    Alimenta las ventanas de monitor (FUT/FX) con 1 request.
    """
    if not redis_client:
        raise HTTPException(status_code=503, detail="Redis not available")
    if asset_class not in ("future", "forex"):
        raise HTTPException(status_code=400, detail="asset_class must be 'future' or 'forex'")
    try:
        # forex tiene hash propio (servicio fmp_forex); los futuros viven en
        # el hash de fmp_indices (comparten el WS de índices)
        hash_key = "snapshot:forex:latest" if asset_class == "forex" else "snapshot:indices:latest"
        raw = await redis_client.client.hgetall(hash_key)
        out = []
        for _, v in raw.items():
            try:
                entry = orjson.loads(v)
            except Exception:
                continue
            if entry.get("asset_class") == asset_class:
                out.append(entry)
        out.sort(key=lambda e: e.get("symbol") or "")
        return {"count": len(out), "results": out}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quotes")
async def get_realtime_quotes(symbols: str):
    """
    Batch de mini-quotes (precio + cambio del día) para la paleta de comandos.

    Un solo HMGET sobre snapshot:enriched:latest para todos los símbolos
    (equities; los índices se resuelven contra snapshot:indices:latest).
    Devuelve {} para símbolos sin datos — el frontend simplemente no pinta quote.
    """
    if not redis_client:
        raise HTTPException(status_code=503, detail="Redis not available")

    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()][:20]
    if not syms:
        return {"quotes": {}}

    quotes = {}
    try:
        raw = await redis_client.client.hmget("snapshot:enriched:latest", syms)
        for sym, ticker_json in zip(syms, raw):
            if not ticker_json:
                continue
            try:
                d = orjson.loads(ticker_json)
            except Exception:
                continue
            price = d.get("current_price") or (d.get("lastTrade") or {}).get("p") or 0
            if not price:
                continue
            quotes[sym] = {
                "price": price,
                "change_percent": d.get("todaysChangePerc"),
                "change": d.get("todaysChange"),
            }

        # Índices (SPX, VIX...) y futuros (ESUSD...) — hash de fmp_indices —
        # y forex (EURUSD...) — hash de fmp_forex. Futuros/forex viven con su
        # símbolo FMP tal cual, así que tras el alias se intenta el directo.
        missing = [s for s in syms if s not in quotes]
        for sym in missing:
            index_symbol = normalize_index_symbol(sym) or sym
            idx_raw = await redis_client.client.hget("snapshot:indices:latest", index_symbol)
            if not idx_raw:
                idx_raw = await redis_client.client.hget("snapshot:forex:latest", sym)
            if not idx_raw:
                continue
            try:
                q = orjson.loads(idx_raw)
            except Exception:
                continue
            if not q.get("price"):
                continue
            quotes[sym] = {
                "price": q.get("price"),
                "change_percent": q.get("change_percent"),
                "change": q.get("change"),
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"quotes": quotes}


@router.get("/ticker/{symbol}")
async def get_realtime_ticker(symbol: str):
    """
    Get real-time data for a specific ticker from the enriched snapshot hash.
    
    Uses HGET to read ONLY this ticker (~500 bytes) instead of
    reading the full snapshot (~7MB) and searching through it.
    """
    if not redis_client:
        raise HTTPException(status_code=503, detail="Redis not available")

    # Índices (SPX, VIX, ^GDAXI...): fuente propia, hash de fmp_indices
    index_symbol = normalize_index_symbol(symbol)
    if index_symbol:
        return await _get_index_realtime(index_symbol)

    try:
        # Read ONLY this ticker from the hash (HGET = ~500 bytes vs GET = ~7MB)
        ticker_json = await redis_client.client.hget("snapshot:enriched:latest", symbol.upper())

        if not ticker_json:
            # Futuros (ESUSD...): hash de fmp_indices con símbolo FMP directo.
            # Forex (EURUSD...): hash propio de fmp_forex.
            fut_raw = await redis_client.client.hget("snapshot:indices:latest", symbol.upper())
            if fut_raw:
                return await _get_index_realtime(symbol.upper())
            fx_raw = await redis_client.client.hget("snapshot:forex:latest", symbol.upper())
            if fx_raw:
                return await _get_index_realtime(symbol.upper(), "snapshot:forex:latest")
            raise HTTPException(
                status_code=404,
                detail=f"Ticker {symbol} not found in snapshot"
            )
        
        # Parse the single ticker JSON
        try:
            ticker_data = orjson.loads(ticker_json)
        except Exception:
            raise HTTPException(status_code=500, detail="Failed to parse ticker data")
        
        # Read metadata for timestamp
        meta_raw = await redis_client.client.hget("snapshot:enriched:latest", "__meta__")
        meta = orjson.loads(meta_raw) if meta_raw else {}
        
        # Extract relevant data for chart
        min_data = ticker_data.get("min", {})
        day_data = ticker_data.get("day", {})
        last_trade = ticker_data.get("lastTrade", {})
        
        return {
            "symbol": symbol.upper(),
            "timestamp": meta.get("timestamp"),
            "minute": {
                "time": min_data.get("t", 0),  # timestamp in ms
                "open": min_data.get("o", 0),
                "high": min_data.get("h", 0),
                "low": min_data.get("l", 0),
                "close": min_data.get("c", 0),
                "volume": min_data.get("v", 0),
                "volume_accumulated": min_data.get("av", 0),
            },
            "day": {
                "open": day_data.get("o", 0),
                "high": day_data.get("h", 0),
                "low": day_data.get("l", 0),
                "close": day_data.get("c", 0),
                "volume": day_data.get("v", 0),
            },
            "last_price": last_trade.get("p", ticker_data.get("current_price", 0)),
            "intraday_high": ticker_data.get("intraday_high"),
            "intraday_low": ticker_data.get("intraday_low"),
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

