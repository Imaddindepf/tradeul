"""
MCP Server: Analytics
Real-time analytics pipeline data - RVOL, VWAP, volume/price windows, technical indicators.
"""
from fastmcp import FastMCP
from clients.redis_client import get_redis, redis_hgetall_parsed
from clients.http_client import service_get
from config import config
from typing import Optional
import orjson

mcp = FastMCP(
    "TradeUL Analytics",
    instructions="Real-time analytics engine providing RVOL, VWAP, volume/price windows, "
    "and intraday technical indicators. Data refreshed every second from Polygon aggregates.",
)


@mcp.tool()
async def get_rvol(symbol: str) -> dict:
    """Get the current Relative Volume (RVOL) for a ticker.
    RVOL compares current volume to historical average for the same time slot.
    RVOL > 2.0 = unusual activity. RVOL > 5.0 = very unusual."""
    r = await get_redis()
    raw = await r.hget("rvol:current_slot", symbol.upper())
    if raw is None:
        return {"symbol": symbol, "rvol": None, "message": "No RVOL data available"}
    try:
        return {"symbol": symbol, "rvol": float(raw)}
    except ValueError:
        return {"symbol": symbol, "rvol": None}


@mcp.tool()
async def get_rvol_batch(symbols: list[str]) -> dict:
    """Get RVOL for multiple tickers at once. More efficient than individual calls."""
    r = await get_redis()
    pipe = r.pipeline()
    for s in symbols:
        pipe.hget("rvol:current_slot", s.upper())
    results = await pipe.execute()

    rvol_data = {}
    for s, raw in zip(symbols, results):
        if raw is not None:
            try:
                rvol_data[s.upper()] = float(raw)
            except ValueError:
                pass
    return {"rvol": rvol_data, "found": len(rvol_data)}


@mcp.tool()
async def get_volume_windows(symbol: str) -> dict:
    """Get volume accumulation over multiple time windows for a ticker.
    Returns: vol_1min, vol_5min, vol_10min, vol_15min, vol_30min, vol_60min."""
    r = await get_redis()
    raw = await r.hget("snapshot:enriched:latest", symbol.upper())
    if not raw:
        return {"error": f"No data for {symbol}"}
    data = orjson.loads(raw)
    return {
        "symbol": symbol,
        "vol_1min": data.get("vol_1min"),
        "vol_5min": data.get("vol_5min"),
        "vol_10min": data.get("vol_10min"),
        "vol_15min": data.get("vol_15min"),
        "vol_30min": data.get("vol_30min"),
        "vol_60min": data.get("vol_60min"),
        "volume_today": data.get("volume") or data.get("volume_today"),
    }


@mcp.tool()
async def get_price_windows(symbol: str) -> dict:
    """Get price change over multiple time windows for a ticker.
    Returns: chg_1min, chg_5min, chg_10min, chg_15min, chg_30min, chg_60min."""
    r = await get_redis()
    raw = await r.hget("snapshot:enriched:latest", symbol.upper())
    if not raw:
        return {"error": f"No data for {symbol}"}
    data = orjson.loads(raw)
    return {
        "symbol": symbol,
        "chg_1min": data.get("chg_1min"),
        "chg_5min": data.get("chg_5min"),
        "chg_10min": data.get("chg_10min"),
        "chg_15min": data.get("chg_15min"),
        "chg_30min": data.get("chg_30min"),
        "chg_60min": data.get("chg_60min"),
        "change_percent": data.get("change_percent"),
    }


@mcp.tool()
async def get_technical_snapshot(symbol: str) -> dict:
    """Get all technical indicators for a ticker from the enriched snapshot.
    Returns: RSI, MACD, Bollinger Bands, SMA, EMA, ADX, Stochastic, VWAP,
    ATR, and derived metrics like distance from SMAs, position in range, etc."""
    r = await get_redis()
    raw = await r.hget("snapshot:enriched:latest", symbol.upper())
    if not raw:
        return {"error": f"No data for {symbol}"}
    data = orjson.loads(raw)

    technicals = {
        "symbol": symbol,
        # Price
        "price": data.get("price"),
        "vwap": data.get("vwap"),
        "price_vs_vwap": data.get("price_vs_vwap"),
        # Intraday indicators
        "rsi_14": data.get("rsi_14"),
        "macd_line": data.get("macd_line"),
        "macd_signal": data.get("macd_signal"),
        "macd_hist": data.get("macd_hist"),
        "bb_upper": data.get("bb_upper"),
        "bb_mid": data.get("bb_mid"),
        "bb_lower": data.get("bb_lower"),
        "adx_14": data.get("adx_14"),
        "stoch_k": data.get("stoch_k"),
        "stoch_d": data.get("stoch_d"),
        # Moving averages
        "sma_5": data.get("sma_5"),
        "sma_8": data.get("sma_8"),
        "sma_20": data.get("sma_20"),
        "sma_50": data.get("sma_50"),
        "sma_200": data.get("sma_200"),
        "ema_9": data.get("ema_9"),
        "ema_20": data.get("ema_20"),
        "ema_50": data.get("ema_50"),
        # ATR
        "atr": data.get("atr"),
        "atr_percent": data.get("atr_percent"),
        # RVOL
        "rvol": data.get("rvol"),
        # Daily indicators
        "daily_sma_20": data.get("daily_sma_20"),
        "daily_sma_50": data.get("daily_sma_50"),
        "daily_sma_200": data.get("daily_sma_200"),
        "daily_rsi": data.get("daily_rsi"),
        "daily_adx_14": data.get("daily_adx_14"),
        # 52-week
        "high_52w": data.get("high_52w"),
        "low_52w": data.get("low_52w"),
        "from_52w_high": data.get("from_52w_high"),
        "from_52w_low": data.get("from_52w_low"),
    }
    return technicals
