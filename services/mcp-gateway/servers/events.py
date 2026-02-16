"""
MCP Server: Market Events
85+ event types from the event_detector service.

Data sources:
  - Real-time: Redis stream `stream:events:market` (last ~500 events)
  - Historical: TimescaleDB `market_events` hypertable (60-day retention, ~900K events/day)
"""
from fastmcp import FastMCP
from clients.redis_client import redis_xrevrange
from clients.db_client import db_fetch, db_fetchval
from typing import Optional
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

mcp = FastMCP(
    "TradeUL Market Events",
    instructions="Market event detection system with 85+ event types. Supports real-time stream "
    "queries and historical TimescaleDB queries with full filtering (date range, event type, "
    "ticker, price, volume, sector, technical indicators).",
)

EVENT_TYPES = {
    "new_high": "Ticker hits a new intraday high",
    "new_low": "Ticker hits a new intraday low",
    "crossed_above_open": "Price crosses above today's open",
    "crossed_below_open": "Price crosses below today's open",
    "crossed_above_prev_close": "Price crosses above previous close",
    "crossed_below_prev_close": "Price crosses below previous close",
    "vwap_cross_up": "Price crosses above VWAP",
    "vwap_cross_down": "Price crosses below VWAP",
    "rvol_spike": "Relative volume spike detected",
    "volume_surge": "Sustained high volume period",
    "volume_spike_1min": "1-minute volume spike (>3x normal)",
    "unusual_prints": "Unusual print activity detected",
    "block_trade": "Block trade detected (large single transaction)",
    "running_up": "Stock running up rapidly",
    "running_down": "Stock running down rapidly",
    "percent_up_5": "Stock up 5%+ from a reference level",
    "percent_down_5": "Stock down 5%+ from a reference level",
    "percent_up_10": "Stock up 10%+ from a reference level",
    "percent_down_10": "Stock down 10%+ from a reference level",
    "pullback_75_from_high": "Price pulled back 75% from intraday high",
    "pullback_25_from_high": "Price pulled back 25% from intraday high",
    "pullback_75_from_low": "Price bounced 75% from intraday low",
    "pullback_25_from_low": "Price bounced 25% from intraday low",
    "gap_up_reversal": "Gap up fading/reversing below open",
    "gap_down_reversal": "Gap down recovering above open",
    "halt": "Trading halt initiated (LULD, regulatory, etc.)",
    "resume": "Trading resumed after halt",
    "crossed_above_sma20_daily": "Price crosses above daily SMA(20)",
    "crossed_below_sma20_daily": "Price crosses below daily SMA(20)",
    "crossed_above_sma50_daily": "Price crosses above daily SMA(50)",
    "crossed_below_sma50_daily": "Price crosses below daily SMA(50)",
    "sma8_above_sma20_5m": "5-min SMA(8) crosses above SMA(20) — bullish",
    "sma8_below_sma20_5m": "5-min SMA(8) crosses below SMA(20) — bearish",
    "macd_above_signal_5m": "5-min MACD crosses above signal line",
    "macd_below_signal_5m": "5-min MACD crosses below signal line",
    "stoch_cross_bullish_5m": "5-min Stochastic bullish crossover (K > D from oversold)",
    "stoch_cross_bearish_5m": "5-min Stochastic bearish crossover (K < D from overbought)",
    "orb_breakout_up": "Opening Range Breakout — price breaks above OR high",
    "orb_breakout_down": "Opening Range Breakout — price breaks below OR low",
    "consolidation_breakout_up": "Breakout from consolidation/tight range — bullish",
    "consolidation_breakout_down": "Breakdown from consolidation/tight range — bearish",
    "bb_upper_breakout": "Price breaks above upper Bollinger Band",
    "bb_lower_breakdown": "Price breaks below lower Bollinger Band",
    "crossed_daily_high_resistance": "Price crosses above previous daily high resistance",
    "crossed_daily_low_support": "Price crosses below previous daily low support",
}


@mcp.tool()
async def get_recent_events(
    count: int = 100,
    event_type: Optional[str] = None,
    symbol: Optional[str] = None,
    min_price: Optional[float] = None,
    min_rvol: Optional[float] = None,
) -> dict:
    """Get the most recent market events from the real-time Redis stream.

    This returns the latest events (last few minutes). For historical queries,
    use query_historical_events instead.

    Each event contains: event_type, symbol, price, change_pct, volume, rvol,
    vwap, details, and timestamp.
    """
    events = await redis_xrevrange("stream:events:market", count=min(count * 3, 500))

    filtered = []
    for e in events:
        if event_type and e.get("event_type") != event_type:
            continue
        if symbol and e.get("symbol", "").upper() != symbol.upper():
            continue
        if min_price and float(e.get("price", 0)) < min_price:
            continue
        if min_rvol and float(e.get("rvol", 0)) < min_rvol:
            continue
        filtered.append(e)
        if len(filtered) >= count:
            break

    return {"events": filtered, "count": len(filtered)}


@mcp.tool()
async def query_historical_events(
    event_type: Optional[str] = None,
    symbol: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    min_change_pct: Optional[float] = None,
    min_rvol: Optional[float] = None,
    min_volume: Optional[int] = None,
    sector: Optional[str] = None,
    limit: int = 100,
) -> dict:
    """Query historical market events from TimescaleDB (up to 60 days).

    Args:
        event_type: Filter by event type (e.g. 'halt', 'vwap_cross_up', 'volume_surge')
        symbol: Filter by ticker symbol
        date_from: Start date (YYYY-MM-DD), defaults to today
        date_to: End date (YYYY-MM-DD), defaults to today
        min_price: Minimum price at event time
        max_price: Maximum price at event time
        min_change_pct: Minimum change percent (e.g. 5.0 for 5%+)
        min_rvol: Minimum relative volume
        min_volume: Minimum absolute volume
        sector: Filter by sector (partial match)
        limit: Max results (default 100, max 500)

    Returns events with: symbol, event_type, price, change_pct, volume, rvol,
    vwap, market_cap, sector, timestamp, and event-specific details.
    """
    limit = min(limit, 500)

    conditions = []
    params = []
    idx = 1

    if not date_from:
        date_from = datetime.now().strftime("%Y-%m-%d")
    if not date_to:
        date_to = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    conditions.append(f"ts >= ${idx}::timestamptz")
    params.append(date_from)
    idx += 1

    conditions.append(f"ts < ${idx}::timestamptz")
    params.append(date_to)
    idx += 1

    if event_type:
        conditions.append(f"event_type = ${idx}")
        params.append(event_type.lower())
        idx += 1

    if symbol:
        conditions.append(f"symbol = ${idx}")
        params.append(symbol.upper())
        idx += 1

    if min_price is not None:
        conditions.append(f"price >= ${idx}")
        params.append(min_price)
        idx += 1

    if max_price is not None:
        conditions.append(f"price <= ${idx}")
        params.append(max_price)
        idx += 1

    if min_change_pct is not None:
        conditions.append(f"ABS(change_pct) >= ${idx}")
        params.append(min_change_pct)
        idx += 1

    if min_rvol is not None:
        conditions.append(f"rvol >= ${idx}")
        params.append(min_rvol)
        idx += 1

    if min_volume is not None:
        conditions.append(f"volume >= ${idx}")
        params.append(min_volume)
        idx += 1

    if sector:
        conditions.append(f"sector ILIKE ${idx}")
        params.append(f"%{sector}%")
        idx += 1

    where_clause = " AND ".join(conditions) if conditions else "TRUE"

    query = f"""
        SELECT
            symbol, event_type, ts, price, change_pct, rvol, volume,
            market_cap, float_shares, gap_pct, sector, security_type,
            prev_value, new_value, delta, delta_pct,
            vwap, atr_pct, rsi,
            chg_1min, chg_5min, chg_10min,
            vol_1min, vol_5min,
            details
        FROM market_events
        WHERE {where_clause}
        ORDER BY ts DESC
        LIMIT ${idx}
    """
    params.append(limit)

    try:
        rows = await db_fetch(query, *params)
    except Exception as e:
        logger.error("TimescaleDB query error: %s", e)
        return {"error": f"Database query failed: {e}", "events": [], "count": 0}

    events = []
    for row in rows:
        event = {}
        for k, v in row.items():
            if v is None:
                continue
            if isinstance(v, datetime):
                event[k] = v.isoformat()
            else:
                event[k] = v
        events.append(event)

    return {
        "events": events,
        "count": len(events),
        "query": {
            "date_from": date_from,
            "date_to": date_to,
            "event_type": event_type,
            "symbol": symbol,
        },
    }


@mcp.tool()
async def get_event_stats(
    date: Optional[str] = None,
    symbol: Optional[str] = None,
) -> dict:
    """Get aggregated event statistics — count by event_type for a given date/symbol.

    Useful to understand what events are firing most frequently, or what
    events a specific ticker has triggered.
    """
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    conditions = ["ts >= $1::timestamptz", "ts < ($1::date + interval '1 day')::timestamptz"]
    params: list = [date]
    idx = 2

    if symbol:
        conditions.append(f"symbol = ${idx}")
        params.append(symbol.upper())
        idx += 1

    where = " AND ".join(conditions)
    query = f"""
        SELECT event_type, COUNT(*) as cnt
        FROM market_events
        WHERE {where}
        GROUP BY event_type
        ORDER BY cnt DESC
    """

    try:
        rows = await db_fetch(query, *params)
    except Exception as e:
        logger.error("Event stats query error: %s", e)
        return {"error": str(e), "stats": {}}

    total = sum(r["cnt"] for r in rows)
    return {
        "date": date,
        "symbol": symbol,
        "total_events": total,
        "by_type": {r["event_type"]: r["cnt"] for r in rows},
    }


@mcp.tool()
async def get_available_event_types() -> dict:
    """List all 85+ available event types with human-readable descriptions.
    Use this to understand what events the system can detect."""
    return {"event_types": EVENT_TYPES, "total": len(EVENT_TYPES)}


@mcp.tool()
async def get_events_by_ticker(symbol: str, count: int = 50) -> dict:
    """Get all recent events for a specific ticker from the real-time stream.
    For historical events, use query_historical_events with a date range."""
    return await get_recent_events(count=count, symbol=symbol)
