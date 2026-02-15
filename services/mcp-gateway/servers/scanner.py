"""
MCP Server: Scanner
Real-time stock scanner with RETE engine - 12 categories, ~1000 active tickers.
Reads directly from Redis for lowest latency.
"""
from fastmcp import FastMCP
from clients.redis_client import redis_get_json, redis_hgetall_parsed
from typing import Optional
import orjson

mcp = FastMCP(
    "TradeUL Scanner",
    instructions="Real-time stock scanner processing 11K+ tickers. Use for current market data, "
    "category rankings (gappers, momentum, volume leaders), and enriched snapshots with 100+ indicators.",
)

CATEGORIES = [
    "gappers_up", "gappers_down", "momentum_up", "momentum_down",
    "high_volume", "winners", "losers", "reversals", "anomalies",
    "new_highs", "new_lows", "post_market", "halts",
]


@mcp.tool()
async def get_scanner_snapshot(
    category: str = "gappers_up",
    limit: int = 50,
    min_price: Optional[float] = None,
    min_rvol: Optional[float] = None,
    min_volume: Optional[int] = None,
    min_market_cap: Optional[float] = None,
    sector: Optional[str] = None,
) -> dict:
    """Get real-time scanner snapshot for a specific category.

    Categories: gappers_up, gappers_down, momentum_up, momentum_down,
    high_volume, winners, losers, reversals, anomalies, new_highs, new_lows,
    post_market, halts.

    Returns ranked tickers with: symbol, price, change_percent, volume,
    market_cap, sector, rvol, vwap, gap_percent, atr_percent, and more.
    """
    if category not in CATEGORIES:
        return {"error": f"Invalid category. Valid: {CATEGORIES}"}

    data = await redis_get_json(f"scanner:category:{category}")
    if not data:
        return {"category": category, "tickers": [], "count": 0}

    tickers = data if isinstance(data, list) else []

    # Apply filters
    filtered = []
    for t in tickers:
        if min_price and (t.get("price") or 0) < min_price:
            continue
        if min_rvol and (t.get("rvol") or 0) < min_rvol:
            continue
        if min_volume and (t.get("volume") or t.get("volume_today") or 0) < min_volume:
            continue
        if min_market_cap and (t.get("market_cap") or 0) < min_market_cap:
            continue
        if sector and sector.lower() not in (t.get("sector") or "").lower():
            continue
        filtered.append(t)

    return {
        "category": category,
        "tickers": filtered[:limit],
        "count": len(filtered),
        "total_unfiltered": len(tickers),
    }


@mcp.tool()
async def get_all_categories() -> dict:
    """Get a summary of all scanner categories with their current ticker count.
    Useful to understand what is active in the market right now."""
    result = {}
    for cat in CATEGORIES:
        data = await redis_get_json(f"scanner:category:{cat}")
        count = len(data) if isinstance(data, list) else 0
        result[cat] = count
    return {"categories": result}


@mcp.tool()
async def get_enriched_ticker(symbol: str) -> dict:
    """Get fully enriched data for a specific ticker from the enriched snapshot.
    Returns 100+ fields: price, volume, technical indicators (RSI, MACD, BB,
    SMA, EMA, ADX, Stochastic), volume windows, change windows, daily indicators,
    52-week data, derived metrics, and more.
    """
    from clients.redis_client import get_redis
    r = await get_redis()
    raw = await r.hget("snapshot:enriched:latest", symbol.upper())
    if not raw:
        return {"error": f"Ticker {symbol} not found in enriched snapshot"}
    return {"symbol": symbol, "data": orjson.loads(raw)}


@mcp.tool()
async def get_enriched_batch(symbols: list[str]) -> dict:
    """Get enriched data for multiple tickers at once.
    More efficient than calling get_enriched_ticker multiple times."""
    from clients.redis_client import get_redis
    r = await get_redis()
    pipe = r.pipeline()
    for s in symbols:
        pipe.hget("snapshot:enriched:latest", s.upper())
    results = await pipe.execute()

    tickers = {}
    for s, raw in zip(symbols, results):
        if raw:
            try:
                tickers[s.upper()] = orjson.loads(raw)
            except Exception:
                pass
    return {"tickers": tickers, "found": len(tickers), "requested": len(symbols)}


@mcp.tool()
async def get_market_session() -> dict:
    """Get current market session status.
    Returns: session (PRE_MARKET, MARKET_OPEN, POST_MARKET, CLOSED), timestamp."""
    data = await redis_get_json("market:session:status")
    if not data:
        return {"session": "UNKNOWN"}
    return data


@mcp.tool()
async def search_scanner(
    symbols: list[str],
) -> dict:
    """Check if specific tickers are currently in the scanner (active/filtered).
    Returns which symbols are found and their current data."""
    data = await redis_get_json("scanner:filtered_complete:LAST")
    if not data:
        return {"found": [], "not_found": symbols}

    lookup = {}
    for t in (data if isinstance(data, list) else []):
        sym = t.get("symbol", "")
        if sym:
            lookup[sym.upper()] = t

    found = []
    not_found = []
    for s in symbols:
        s_upper = s.upper()
        if s_upper in lookup:
            found.append(lookup[s_upper])
        else:
            not_found.append(s_upper)

    return {"found": found, "not_found": not_found}
