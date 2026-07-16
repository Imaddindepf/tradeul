"""
MCP Server: Scanner
Real-time stock scanner with RETE engine - 12 categories, ~1000 active tickers.

Architecture:
  - Category rankings: fetched via Scanner HTTP API (in-memory engine)
  - Enriched snapshots: read from Redis hash (145 fields per ticker)
  - Market session: read from Redis key
  - Dynamic filtering: queries enriched snapshot with structured filters
"""
from fastmcp import FastMCP
from clients.redis_client import redis_get_json, get_redis
from clients.http_client import service_get
from config import config
from typing import Optional
import logging
import orjson

logger = logging.getLogger(__name__)

mcp = FastMCP(
    "Tradeul Scanner",
    instructions="Real-time stock scanner processing 11K+ tickers. Use for current market data, "
    "category rankings (gappers, momentum, volume leaders), enriched snapshots with 145+ indicators, "
    "and dynamic filtering on the full ticker universe.",
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

    try:
        data = await service_get(
            config.scanner_url,
            f"/api/categories/{category}",
            params={"limit": limit * 3},
        )
    except Exception as e:
        logger.error("Scanner API error for %s: %s", category, e)
        return {"category": category, "tickers": [], "count": 0, "error": str(e)}

    tickers = data.get("tickers", []) if isinstance(data, dict) else []

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
    try:
        data = await service_get(config.scanner_url, "/api/categories")
        if isinstance(data, dict) and "categories" in data:
            return data
        if isinstance(data, list):
            return {"categories": {c.get("name", c): c.get("count", 0) for c in data}}
    except Exception as e:
        logger.error("Scanner categories API error: %s", e)

    try:
        stats = await service_get(config.scanner_url, "/api/categories/stats")
        return {"categories": stats}
    except Exception:
        pass

    return {"categories": {}, "error": "Scanner service unavailable"}


@mcp.tool()
async def get_enriched_ticker(symbol: str) -> dict:
    """Get fully enriched data for a specific ticker from the enriched snapshot.
    Returns 145+ fields: price, volume, technical indicators (RSI, MACD, BB,
    SMA, EMA, ADX, Stochastic), volume windows, change windows, daily indicators,
    52-week data, derived metrics, and more.
    """
    r = await get_redis()
    sym = symbol.upper()
    raw = await r.hget("snapshot:enriched:latest", sym)
    if not raw:
        raw = await r.hget("snapshot:enriched:last_close", sym)
    if not raw:
        return {"error": f"Ticker {sym} not found in enriched snapshot"}
    try:
        return {"symbol": sym, "data": orjson.loads(raw)}
    except Exception:
        return {"error": f"Failed to parse data for {sym}"}


@mcp.tool()
async def get_enriched_batch(symbols: list[str]) -> dict:
    """Get enriched data for multiple tickers at once.
    More efficient than calling get_enriched_ticker multiple times.
    Falls back to last_close data when market is closed."""
    r = await get_redis()

    tickers = {}
    for s in symbols:
        sym = s.upper()
        raw = await r.hget("snapshot:enriched:latest", sym)
        if not raw:
            raw = await r.hget("snapshot:enriched:last_close", sym)
        if raw:
            try:
                tickers[sym] = orjson.loads(raw)
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


# The enriched snapshot uses internal field names; accept the friendly
# aliases the LLM naturally produces so filters don't silently match nothing.
_FIELD_ALIASES = {
    "price": "current_price",
    "volume": "current_volume",
    "change_pct": "todaysChangePerc",
    "change_percent": "todaysChangePerc",
    "gap_pct": "gap_percent",
    "premarket_change_pct": "premarket_change_percent",
    "postmarket_change_pct": "postmarket_change_percent",
    "afterhours_change_percent": "postmarket_change_percent",
}


def _resolve_field(field: str) -> str:
    return _FIELD_ALIASES.get(field, field)


# Resolved field names already present in every output row under a friendly
# name (price/change_pct/volume/...). Skipped when echoing filter/sort fields
# to avoid duplicated values under two names.
_OUTPUT_BASE_FIELDS = {
    "current_price", "todaysChangePerc", "current_volume",
    "rvol", "market_cap", "sector",
}


@mcp.tool()
async def apply_dynamic_filter(
    filters: list[dict],
    sort_by: str = "volume",
    sort_order: str = "desc",
    limit: int = 50,
    snapshot: str = "live",
) -> dict:
    """Filter the entire enriched snapshot universe (~11K tickers) using structured filters.

    Each filter is a dict with: {"field": str, "op": str, "value": number|string}
    Operators: gt, gte, lt, lte, eq, neq, contains (for string fields like sector)

    snapshot: "live" (real-time data, default) or "close" (universe frozen at
    the last regular-session close — use for "at/before the close" questions
    asked during post-market or overnight).

    Available numeric fields: price, volume, rvol, market_cap, change_pct, gap_pct,
    float_shares, rsi_14, atr_percent, adx_14, vwap, daily_rsi, daily_adx_14,
    from_52w_high, from_52w_low, change_1d, change_5d, change_20d,
    premarket_change_percent, premarket_volume, postmarket_change_percent,
    avg_volume_5d, avg_volume_20d, bb_upper, bb_lower, stoch_k, stoch_d,
    macd_line, macd_signal, macd_hist, ema_9, ema_20, ema_50,
    sma_20, sma_50, sma_200, daily_sma_20, daily_sma_50, daily_sma_200,
    dist_daily_sma_20, dist_daily_sma_50, trades_today, trades_z_score,
    vol_1min, vol_5min, chg_1min, chg_5min, chg_10min, chg_15min, chg_30min, chg_60min.

    String fields: sector, security_type.

    Example: [{"field":"rsi_14","op":"lt","value":30},{"field":"volume","op":"gt","value":1000000}]
    """
    sort_by = _resolve_field(sort_by)
    filters = [
        {**f, "field": _resolve_field(f.get("field", ""))}
        for f in filters
        if isinstance(f, dict)
    ]
    r = await get_redis()
    keys = ["snapshot:enriched:latest", "snapshot:enriched:last_close"]
    if snapshot == "close":
        keys.reverse()
    raw_all = await r.hgetall(keys[0])
    if not raw_all:
        raw_all = await r.hgetall(keys[1])
    if not raw_all:
        return {"error": "No enriched snapshot available", "tickers": [], "count": 0}

    OPS = {
        "gt": lambda a, b: a > b,
        "gte": lambda a, b: a >= b,
        "lt": lambda a, b: a < b,
        "lte": lambda a, b: a <= b,
        "eq": lambda a, b: a == b,
        "neq": lambda a, b: a != b,
        "contains": lambda a, b: str(b).lower() in str(a).lower(),
    }

    matched = []
    for sym, raw_val in raw_all.items():
        if sym == "__meta__":
            continue
        try:
            ticker = orjson.loads(raw_val)
        except Exception:
            continue

        passes = True
        for f in filters:
            field = f.get("field", "")
            op = f.get("op", "gt")
            value = f.get("value")
            if not field or value is None or op not in OPS:
                continue

            actual = ticker.get(field)
            if actual is None:
                passes = False
                break

            try:
                if op != "contains":
                    actual = float(actual)
                    value = float(value)
                if not OPS[op](actual, value):
                    passes = False
                    break
            except (ValueError, TypeError):
                passes = False
                break

        if passes:
            row = {
                "symbol": sym,
                "price": ticker.get("current_price"),
                "change_pct": ticker.get("todaysChangePerc"),
                "volume": ticker.get("current_volume"),
                "rvol": ticker.get("rvol"),
                "market_cap": ticker.get("market_cap"),
                "sector": ticker.get("sector"),
            }
            # Add filter/sort fields not already covered by the base row,
            # so rows never carry the same value under two names.
            for extra in [f.get("field") for f in filters] + [sort_by]:
                if extra and extra not in _OUTPUT_BASE_FIELDS and extra not in row:
                    row[extra] = ticker.get(extra)
            matched.append((ticker.get(sort_by), row))

    def _sort_key(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    reverse = sort_order == "desc"
    matched.sort(key=lambda pair: _sort_key(pair[0]), reverse=reverse)
    rows = [row for _, row in matched]

    return {
        "tickers": rows[:limit],
        "count": len(rows),
        "total_scanned": len(raw_all),
        "filters_applied": filters,
        "sort": {"by": sort_by, "order": sort_order},
    }


@mcp.tool()
async def search_scanner(symbols: list[str]) -> dict:
    """Check if specific tickers are currently in the scanner (active/filtered).
    Returns which symbols are found and their enriched data."""
    r = await get_redis()
    found = []
    not_found = []

    for s in symbols:
        sym = s.upper()
        raw = await r.hget("snapshot:enriched:latest", sym)
        if not raw:
            raw = await r.hget("snapshot:enriched:last_close", sym)
        if raw:
            try:
                data = orjson.loads(raw)
                found.append({"symbol": sym, **data})
            except Exception:
                not_found.append(sym)
        else:
            not_found.append(sym)

    return {"found": found, "not_found": not_found}
