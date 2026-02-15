"""
MCP Server: Market Events
Real-time market event detection - 27+ event types from the event_detector service.
Reads from Redis stream and TimescaleDB for historical data.
"""
from fastmcp import FastMCP
from clients.redis_client import redis_xrevrange
from clients.http_client import service_get
from config import config
from typing import Optional

mcp = FastMCP(
    "TradeUL Market Events",
    instructions="Market event detection system with 27+ event types including price breakouts, "
    "VWAP crosses, volume spikes, momentum shifts, pullbacks, gaps, halts, "
    "stochastic/MACD signals, Bollinger band events, and more.",
)

EVENT_TYPES = [
    "new_high", "new_low", "breakout_high", "breakdown_low",
    "vwap_cross_up", "vwap_cross_down", "vwap_reclaim", "vwap_rejection",
    "volume_spike", "volume_surge", "unusual_volume",
    "momentum_acceleration", "momentum_reversal", "momentum_exhaustion",
    "pullback_to_vwap", "pullback_to_ema", "pullback_bounce",
    "gap_up_hold", "gap_up_fade", "gap_down_hold", "gap_down_recovery",
    "halt_pending", "halt_resume",
    "stoch_oversold_cross", "stoch_overbought_cross",
    "macd_bullish_cross", "macd_bearish_cross",
    "bb_squeeze", "bb_breakout_upper", "bb_breakout_lower",
    "orb_breakout_high", "orb_breakout_low",
    "consolidation_breakout", "consolidation_breakdown",
    "session_high", "session_low",
    "confirmed_sma_cross_up", "confirmed_sma_cross_down",
    "confirmed_ema_cross_up", "confirmed_ema_cross_down",
]


@mcp.tool()
async def get_recent_events(
    count: int = 100,
    event_type: Optional[str] = None,
    symbol: Optional[str] = None,
    min_price: Optional[float] = None,
    min_rvol: Optional[float] = None,
) -> dict:
    """Get the most recent market events from the real-time stream.

    Events include: new_high, volume_spike, vwap_cross_up, momentum_acceleration,
    halt_pending, macd_bullish_cross, bb_breakout_upper, orb_breakout_high, etc.

    Each event contains: event_type, symbol, price, change_percent, volume, rvol,
    vwap, details (human-readable description), and timestamp.
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
async def get_available_event_types() -> dict:
    """List all available event types with descriptions.
    Use this to understand what events the system can detect."""
    descriptions = {
        "new_high": "Ticker hits a new intraday high",
        "new_low": "Ticker hits a new intraday low",
        "breakout_high": "Price breaks above recent resistance",
        "breakdown_low": "Price breaks below recent support",
        "vwap_cross_up": "Price crosses above VWAP",
        "vwap_cross_down": "Price crosses below VWAP",
        "vwap_reclaim": "Price reclaims VWAP after being below",
        "vwap_rejection": "Price rejected at VWAP level",
        "volume_spike": "Sudden volume increase (>3x normal)",
        "volume_surge": "Sustained high volume period",
        "unusual_volume": "Anomalous volume detected (z-score based)",
        "momentum_acceleration": "Price momentum increasing rapidly",
        "momentum_reversal": "Momentum direction changing",
        "momentum_exhaustion": "Momentum slowing after strong move",
        "pullback_to_vwap": "Price pulling back to VWAP level",
        "pullback_to_ema": "Price pulling back to EMA support",
        "pullback_bounce": "Price bouncing from pullback level",
        "gap_up_hold": "Gap up holding above open price",
        "gap_up_fade": "Gap up fading below open price",
        "gap_down_hold": "Gap down holding below open price",
        "gap_down_recovery": "Gap down recovering above open",
        "halt_pending": "Trading halt initiated",
        "halt_resume": "Trading halt resumed",
        "stoch_oversold_cross": "Stochastic cross up from oversold",
        "stoch_overbought_cross": "Stochastic cross down from overbought",
        "macd_bullish_cross": "MACD bullish crossover",
        "macd_bearish_cross": "MACD bearish crossover",
        "bb_squeeze": "Bollinger Band squeeze (low volatility)",
        "bb_breakout_upper": "Price breaks above upper Bollinger Band",
        "bb_breakout_lower": "Price breaks below lower Bollinger Band",
        "orb_breakout_high": "Opening range breakout (high)",
        "orb_breakout_low": "Opening range breakout (low)",
        "consolidation_breakout": "Breakout from consolidation pattern",
        "consolidation_breakdown": "Breakdown from consolidation pattern",
        "session_high": "New session high",
        "session_low": "New session low",
        "confirmed_sma_cross_up": "Confirmed SMA bullish crossover",
        "confirmed_sma_cross_down": "Confirmed SMA bearish crossover",
        "confirmed_ema_cross_up": "Confirmed EMA bullish crossover",
        "confirmed_ema_cross_down": "Confirmed EMA bearish crossover",
    }
    return {"event_types": descriptions, "total": len(descriptions)}


@mcp.tool()
async def get_events_by_ticker(symbol: str, count: int = 50) -> dict:
    """Get all recent events for a specific ticker.
    Useful to understand what is happening with a particular stock."""
    return await get_recent_events(count=count, symbol=symbol)


@mcp.tool()
async def get_alert_catalog() -> dict:
    """Get the full alert/event catalog with categories and phases.
    Shows which events are available and how they are organized."""
    try:
        return await service_get(config.api_gateway_url, "/api/alerts/catalog")
    except Exception as e:
        return {"error": str(e)}
