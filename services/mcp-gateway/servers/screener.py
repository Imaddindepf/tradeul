"""
MCP Server: Screener (DuckDB)
High-performance stock screener with 60+ indicators powered by DuckDB on Parquet files.
"""
from fastmcp import FastMCP
from clients.http_client import service_get
from config import config
from typing import Optional

mcp = FastMCP(
    "TradeUL Screener",
    instructions="DuckDB-powered stock screener with 60+ technical and fundamental indicators. "
    "Supports complex multi-criteria screening with SQL-like filter expressions. "
    "Data source: Polygon day_aggs Parquet files.",
)

AVAILABLE_INDICATORS = [
    "open", "high", "low", "close", "volume", "vwap", "transactions",
    "change_pct", "gap_pct", "range_pct", "dollar_volume",
    "relative_volume", "avg_volume_5d", "avg_volume_10d", "avg_volume_20d",
    "rsi_14", "rsi_7",
    "sma_5", "sma_10", "sma_20", "sma_50", "sma_200",
    "ema_9", "ema_12", "ema_20", "ema_26", "ema_50",
    "macd_line", "macd_signal", "macd_histogram",
    "bb_upper", "bb_middle", "bb_lower", "bb_width", "bb_position",
    "atr_14", "atr_percent",
    "adx_14", "plus_di", "minus_di",
    "stoch_k", "stoch_d",
    "obv", "obv_change",
    "change_1d", "change_3d", "change_5d", "change_10d", "change_20d",
    "high_52w", "low_52w", "from_52w_high", "from_52w_low",
    "above_sma_20", "above_sma_50", "above_sma_200",
    "dist_from_sma_20", "dist_from_sma_50", "dist_from_sma_200",
    "market_cap", "float_shares", "sector", "industry",
]


@mcp.tool()
async def run_screen(
    filters: list[dict],
    sort_by: str = "relative_volume",
    sort_order: str = "desc",
    limit: int = 50,
    symbols: Optional[list[str]] = None,
) -> dict:
    """Run a stock screen with multiple filter criteria.

    Each filter is a dict with: field, operator, value.
    Operators: '>', '<', '>=', '<=', '=', '!=', 'between', 'in'

    Example filters:
    [
      {"field": "rsi_14", "operator": "<", "value": 30},
      {"field": "relative_volume", "operator": ">", "value": 2.0},
      {"field": "market_cap", "operator": ">", "value": 100000000},
      {"field": "close", "operator": "between", "value": [5, 50]}
    ]

    Available indicators: close, volume, rsi_14, macd_line, bb_position,
    atr_percent, adx_14, stoch_k, relative_volume, change_pct, gap_pct,
    sma_20, ema_50, market_cap, float_shares, and 50+ more.

    Returns: list of matching tickers with all requested indicator values.
    """
    try:
        return await service_get(
            config.screener_url,
            "/api/v1/screen",
            params={
                "filters": filters,
                "sort_by": sort_by,
                "sort_order": sort_order,
                "limit": limit,
                "symbols": symbols,
            },
        )
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def get_available_filters() -> dict:
    """Get all available screener filters/indicators with their descriptions.
    Use this to understand what criteria you can screen for."""
    return {
        "indicators": AVAILABLE_INDICATORS,
        "operators": [">", "<", ">=", "<=", "=", "!=", "between", "in"],
        "sort_options": AVAILABLE_INDICATORS,
        "total_indicators": len(AVAILABLE_INDICATORS),
    }


@mcp.tool()
async def get_daily_indicators(symbols: Optional[list[str]] = None) -> dict:
    """Get pre-computed daily indicators for all tickers or specific symbols.
    Includes: RSI, MACD, Bollinger Bands, SMA, EMA, ATR, ADX, and more.
    Updated every 5 minutes from DuckDB."""
    try:
        params = {}
        if symbols:
            params["symbols"] = ",".join(s.upper() for s in symbols)
        return await service_get(
            config.screener_url, "/api/v1/indicators", params=params
        )
    except Exception as e:
        return {"error": str(e)}
