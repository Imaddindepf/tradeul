"""
Market Analysis Tools
=====================
Function declarations for Gemini Function Calling.

Each tool is a capability the LLM can invoke to get data or perform actions.
The LLM decides which tools to use based on the user's query.
"""

import pandas as pd
import httpx
import asyncio
import os
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from pathlib import Path
import pytz
import structlog

logger = structlog.get_logger(__name__)
ET = pytz.timezone('America/New_York')
POLYGON_API_KEY = os.environ.get('POLYGON_API_KEY', '')


# =============================================================================
# POLYGON API CLIENT WITH RETRY (for fallback when local files unavailable)
# =============================================================================

async def _polygon_request_with_retry(
    url: str, 
    params: dict = None, 
    max_retries: int = 3,
    timeout: float = 15.0
) -> dict:
    """Make Polygon API request with exponential backoff retry."""
    params = params or {}
    params['apiKey'] = POLYGON_API_KEY
    
    last_error = None
    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(max_retries):
            try:
                resp = await client.get(url, params=params)
                if resp.status_code == 200:
                    return resp.json()
                elif resp.status_code == 429:  # Rate limited
                    wait_time = 2 ** attempt
                    logger.warning("polygon_rate_limited", wait=wait_time)
                    await asyncio.sleep(wait_time)
                else:
                    last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
            except asyncio.TimeoutError:
                last_error = "Timeout"
                await asyncio.sleep(1)
            except Exception as e:
                last_error = str(e)
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
    
    raise Exception(f"Polygon API failed after {max_retries} retries: {last_error}")


async def _fetch_polygon_grouped_daily(date: str) -> pd.DataFrame:
    """
    Fetch all stocks' daily OHLCV from Polygon API.
    
    Args:
        date: YYYY-MM-DD format
        
    Returns:
        DataFrame with: symbol, open, high, low, close, volume
    """
    if not POLYGON_API_KEY:
        raise Exception("POLYGON_API_KEY not configured")
    
    url = f"https://api.polygon.io/v2/aggs/grouped/locale/us/market/stocks/{date}"
    
    logger.info("polygon_fetch_grouped_daily", date=date)
    data = await _polygon_request_with_retry(url, {"adjusted": "true"})
    
    if data.get("status") != "OK" or not data.get("results"):
        logger.warning("polygon_no_results", date=date, status=data.get("status"))
        return pd.DataFrame()
    
    df = pd.DataFrame(data["results"])
    df = df.rename(columns={
        "T": "symbol", "o": "open", "h": "high", "l": "low",
        "c": "close", "v": "volume", "vw": "vwap", "t": "timestamp"
    })
    
    # Convert timestamp to datetime
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True).dt.tz_convert(ET)
    
    logger.info("polygon_fetched", date=date, count=len(df))
    return df[["symbol", "datetime", "open", "high", "low", "close", "volume"]]


async def _fetch_polygon_top_movers(
    date: str,
    direction: str = "up",
    limit: int = 20,
    min_volume: int = 100000
) -> pd.DataFrame:
    """
    Get top movers from Polygon API as fallback.
    
    Args:
        date: YYYY-MM-DD format
        direction: 'up' for gainers, 'down' for losers
        limit: Number of results
        min_volume: Minimum volume filter
        
    Returns:
        DataFrame with: symbol, open, close, change_pct, volume
    """
    df = await _fetch_polygon_grouped_daily(date)
    
    if df.empty:
        return df
    
    # Calculate change percentage
    df["change_pct"] = ((df["close"] - df["open"]) / df["open"] * 100).round(2)
    
    # Filter
    df = df[df["volume"] >= min_volume]
    df = df[df["open"] > 0]  # Avoid division by zero cases
    
    # Sort
    ascending = direction == "down"
    df = df.sort_values("change_pct", ascending=ascending).head(limit)
    
    return df[["symbol", "open", "close", "change_pct", "volume"]]

# =============================================================================
# TOOL DEFINITIONS (Gemini Function Declarations)
# =============================================================================

MARKET_TOOLS = [
    {
        "name": "get_market_snapshot",
        "description": """Get real-time market data from scanner. Returns active tickers with current prices, 
        changes, volume, and technical indicators.
        
        USE FOR:
        - Check if specific ticker(s) are in scanner: symbols=["AAOI", "TSLA"]
        - Current gainers/losers: filter_type="gainers" or "losers"
        - Volume leaders: filter_type="volume"
        - Sector analysis: sector="Technology"
        
        Data includes: symbol, price, change_percent, volume_today, market_cap, sector, rvol, vwap.
        
        IMPORTANT: 
        - To check if ticker is in scanner, use symbols parameter
        - Set generate_chart=true when user asks for 'grafico', 'chart', 'visualizar'""",
        "parameters": {
            "type": "object",
            "properties": {
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter by specific ticker symbols. Use to check if ticker(s) are in scanner."
                },
                "filter_type": {
                    "type": "string",
                    "enum": ["all", "gainers", "losers", "volume", "premarket", "postmarket"],
                    "description": "Type of filter to apply"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max number of results (default 50)"
                },
                "min_volume": {
                    "type": "integer",
                    "description": "Minimum volume filter"
                },
                "min_price": {
                    "type": "number",
                    "description": "Minimum price filter"
                },
                "min_market_cap": {
                    "type": "number",
                    "description": "Minimum market cap filter in dollars (e.g., 1000000000 for 1B, 100000000 for 100M)"
                },
                "sector": {
                    "type": "string",
                    "description": "Filter by sector name"
                },
                "generate_chart": {
                    "type": "boolean",
                    "description": "Generate a bar chart. Use when user asks for 'grafico', 'chart', 'visualizar'"
                }
            },
            "required": []
        }
    },
    {
        "name": "get_historical_data",
        "description": """Get historical minute-level OHLCV data. Use for: yesterday's movers, specific time 
        ranges, after-hours analysis, pre-market analysis, multi-day comparisons. Returns bars with: 
        symbol, datetime, open, high, low, close, volume. Available: 1760+ days of historical data.""",
        "parameters": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Date: 'today', 'yesterday', or 'YYYY-MM-DD'"
                },
                "start_hour": {
                    "type": "integer",
                    "description": "Start hour (0-23) in ET timezone"
                },
                "end_hour": {
                    "type": "integer",
                    "description": "End hour (0-23) in ET timezone"
                },
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific symbols to filter (optional)"
                }
            },
            "required": ["date"]
        }
    },
    {
        "name": "get_top_movers",
        "description": """Get top gainers or losers for a specific DATE and HOUR RANGE.
        
        USE CASES:
        - "top gainers today" → date='today'
        - "top movers 9:30-10:30" → date='today', start_hour=9, end_hour=10
        - "after-hours movers" → start_hour=16, end_hour=20
        - "pre-market leaders" → start_hour=4, end_hour=9
        
        IMPORTANT: For "top per EACH hour" or "per range of hour", use get_top_movers_hourly instead.
        
        Returns: symbol, open_price, close_price, change_pct, volume.""",
        "parameters": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Date: 'today', 'yesterday', or 'YYYY-MM-DD'"
                },
                "start_hour": {
                    "type": "integer",
                    "description": "Start hour 0-23 in ET (e.g., 9 for 9:30 market open, 16 for after-hours)"
                },
                "end_hour": {
                    "type": "integer",
                    "description": "End hour 0-23 in ET (e.g., 10 for 10:30, 16 for market close)"
                },
                "direction": {
                    "type": "string",
                    "enum": ["up", "down"],
                    "description": "Gainers (up) or losers (down). Default: up"
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of results (default 20)"
                },
                "min_volume": {
                    "type": "integer",
                    "description": "Minimum volume (default 100000)"
                }
            },
            "required": ["date"]
        }
    },
    {
        "name": "get_top_movers_hourly",
        "description": """Get top stock for EACH HOUR range during a trading day.
        
        PERFECT FOR:
        - "top stock per hour range today"
        - "best performer each hour 9:30-16:00"
        - "top gainer cada hora"
        - "hourly leaders"
        
        Returns a table with: hour_range, symbol, change_pct, volume
        
        Runs concurrent API requests for efficiency.""",
        "parameters": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Date: 'today', 'yesterday', or 'YYYY-MM-DD'"
                },
                "start_hour": {
                    "type": "integer",
                    "description": "First hour to analyze (default 9 for market open)"
                },
                "end_hour": {
                    "type": "integer",
                    "description": "Last hour to analyze (default 16 for market close)"
                },
                "direction": {
                    "type": "string",
                    "enum": ["up", "down"],
                    "description": "Gainers (up) or losers (down). Default: up"
                },
                "min_volume": {
                    "type": "integer",
                    "description": "Minimum volume (default 100000)"
                },
                "min_market_cap": {
                    "type": "number",
                    "description": "Minimum market cap in dollars (e.g., 1000000000 for 1B)"
                }
            },
            "required": ["date"]
        }
    },
    {
        "name": "classify_synthetic_sectors",
        "description": """Classify tickers into THEMATIC sectors (synthetic ETFs). Creates dynamic groupings 
        like: Nuclear, AI & Semiconductors, Electric Vehicles, Biotech, Crypto, Cannabis, Space, etc.
        Use when user asks about: 'sectores sintéticos', 'synthetic ETFs', 'thematic sectors', 
        'sector nuclear', 'sector AI'. Returns sector performance rankings.
        
        IMPORTANT: Use filter parameters when user specifies constraints like 'market cap > 100M', 
        'volume > 500K', 'price > $5', etc.""",
        "parameters": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Date for classification: 'today' or 'yesterday'"
                },
                "max_sectors": {
                    "type": "integer",
                    "description": "Maximum sectors to return (default 15)"
                },
                "min_market_cap": {
                    "type": "number",
                    "description": "Minimum market cap filter in dollars (e.g., 100000000 for 100M)"
                },
                "min_volume": {
                    "type": "number",
                    "description": "Minimum volume filter"
                },
                "min_price": {
                    "type": "number",
                    "description": "Minimum price filter"
                },
                "max_price": {
                    "type": "number",
                    "description": "Maximum price filter"
                },
                "generate_chart": {
                    "type": "boolean",
                    "description": "Generate a bar chart of sector performance. Use when user asks for 'gráfico', 'chart', 'visualización'"
                },
                "min_tickers_per_sector": {
                    "type": "integer",
                    "description": "Minimum number of tickers required per sector. Use when user says 'al menos 5 acciones', 'at least 10 stocks', etc."
                }
            },
            "required": ["date"]
        }
    },
    {
        "name": "quick_news",
        "description": """FAST news lookup for a ticker from Benzinga (<1 second).
        Use FIRST when user asks: WHY is X moving?, news about X, what happened to X.
        Returns news articles instantly. Response includes deep_research_available flag for user to request more.""",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Ticker symbol (e.g., 'NVDA', 'AAPL')"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max news articles (default 5)"
                }
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "research_ticker",
        "description": """DEEP research on a ticker using X.com, web search, and news (takes 60-90 seconds).
        Use ONLY when user explicitly asks for "deep research", "full analysis", or wants more detail after quick_news.
        Returns: comprehensive analysis with citations from X.com, Bloomberg, Reuters, etc.""",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Ticker symbol (e.g., 'NVDA', 'AAPL')"
                },
                "include_technicals": {
                    "type": "boolean",
                    "description": "Include technical chart (default true)"
                }
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "execute_analysis",
        "description": """Execute Python/SQL code in sandbox for complex market analysis.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                              DATA SCHEMA REFERENCE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DAY_AGGS (daily candles) ⚡ USE FOR: week/month analysis, gaps, multi-day trends
─────────────────────────────────────────────────────────────────────────────────
Path: /data/polygon/day_aggs/YYYY-MM-DD.parquet  ← PREFERRED (10-15x faster)
      /data/polygon/day_aggs/YYYY-MM-DD.csv.gz   ← Fallback
Glob: /data/polygon/day_aggs/2026-01-*.parquet (for multiple days)

⚡ PARQUET IS 10-15x FASTER: Use read_parquet() when .parquet exists, else read_csv_auto()

Columns:
  ticker        VARCHAR   Stock symbol (e.g., 'AAPL')
  timestamp     BIGINT    Unix timestamp in NANOSECONDS (divide by 1e9)
  open          DOUBLE    Opening price
  high          DOUBLE    High of day
  low           DOUBLE    Low of day
  close         DOUBLE    Closing price
  volume        BIGINT    Total daily volume
  vwap          DOUBLE    Volume-weighted average price ← USEFUL FOR ANALYSIS!
  transactions  BIGINT    Number of transactions

Size: ~3MB per file, ~10,000 rows (one per ticker)

MINUTE_AGGS (minute candles) - USE FOR: intraday, hourly, premarket/afterhours
─────────────────────────────────────────────────────────────────────────────────
Path: /data/polygon/minute_aggs/YYYY-MM-DD.parquet  ← PREFERRED (10-15x faster)
      /data/polygon/minute_aggs/YYYY-MM-DD.csv.gz   ← Fallback
Today: /data/polygon/minute_aggs/today.parquet (always Parquet)

⚡ PARQUET IS 10-15x FASTER: Use read_parquet() when .parquet exists, else read_csv_auto()

Columns:
  ticker        VARCHAR   Stock symbol
  window_start  BIGINT    Unix timestamp in NANOSECONDS (divide by 1e9)
  open          DOUBLE    Opening price of minute
  high          DOUBLE    High of minute
  low           DOUBLE    Low of minute
  close         DOUBLE    Closing price of minute
  volume        BIGINT    Volume in that minute

Size: ~500MB CSV.gz per file, ~4M rows (Parquet is ~200MB and much faster)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                           COMMON ANALYSIS PATTERNS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

GAP ANALYSIS (compare today's open vs yesterday's close):
  - Join two consecutive day_aggs files
  - Gap % = (today.open - yesterday.close) / yesterday.close * 100
  - Gap UP > 3%, Gap DOWN < -3% are significant

VWAP ANALYSIS:
  - day_aggs has 'vwap' column (pre-calculated)
  - close > vwap = bullish, close < vwap = bearish
  - Distance from VWAP = (close - vwap) / vwap * 100

RELATIVE STRENGTH:
  - Compare stock change vs SPY/QQQ change
  - RS = stock_change - benchmark_change

MOMENTUM/TREND:
  - Multi-day: Use day_aggs with window functions (LAG, LEAD)
  - Consecutive up days: COUNT days where close > prev_close

VOLUME ANALYSIS:
  - Relative volume = today_volume / avg_volume_N_days
  - Volume spike = volume > 2x average

TIME-BASED (minute_aggs):
  - Premarket: hour < 9 (4:00-9:30 ET)
  - Morning: hour >= 9 AND hour < 12
  - Afternoon: hour >= 12 AND hour < 16
  - Afterhours: hour >= 16

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                              AVAILABLE FUNCTIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

historical_query(sql)                    Execute DuckDB SQL, return DataFrame
save_output(dataframe, 'name')           REQUIRED to return results

get_period_top_movers(days, limit, min_volume, direction)  Top gainers/losers over N days
get_period_top_by_day(days, top_n, direction)              Top N per each day
get_daily_bars(days, symbol)                                Daily OHLCV data
get_top_movers(date_str, limit, min_volume, direction)     Top movers for single day
get_minute_bars(date_str, symbol)                          Minute bars for single symbol

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                                  EXAMPLES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ CRITICAL INSTRUCTIONS:
1. ALWAYS use current dates (2026-01-XX), NOT old dates like 2023!
2. Use read_parquet() for .parquet files (10-15x faster)
3. For "week" analysis, use GLOB: read_parquet('/data/polygon/day_aggs/2026-01-*.parquet')
4. ALWAYS call save_output(result, 'name') to return results!

EXAMPLE 1 - GAP ANALYSIS: Gappers that closed below VWAP (SINGLE DAY)
─────────────────────────────────────────────────────────────────────────────────
sql = '''
WITH yesterday AS (
    SELECT ticker, close as prev_close
    FROM read_parquet('/data/polygon/day_aggs/2026-01-16.parquet')  -- Use .parquet if exists
),
today AS (
    SELECT ticker, open, high, low, close, volume, vwap
    FROM read_parquet('/data/polygon/day_aggs/2026-01-17.parquet')  -- Use .parquet if exists
),
gappers AS (
    SELECT t.ticker, y.prev_close, t.open, t.close, t.vwap, t.volume,
        ROUND((t.open - y.prev_close) / y.prev_close * 100, 2) as gap_pct,
        CASE WHEN t.close < t.vwap THEN 1 ELSE 0 END as closed_below_vwap
    FROM today t
    JOIN yesterday y ON t.ticker = y.ticker
    WHERE ABS((t.open - y.prev_close) / y.prev_close) > 0.03  -- Gap > 3%
      AND t.volume > 500000
)
SELECT 
    COUNT(*) as total_gappers,
    SUM(closed_below_vwap) as below_vwap,
    ROUND(SUM(closed_below_vwap) * 100.0 / NULLIF(COUNT(*), 0), 1) as pct_below_vwap
FROM gappers
'''
result = historical_query(sql)
save_output(result, 'gap_vwap_analysis')

EXAMPLE 1B - WEEKLY GAPPER ANALYSIS (multiple days with VWAP)
─────────────────────────────────────────────────────────────────────────────────
sql = '''
WITH daily_data AS (
    SELECT ticker, 
           DATE_TRUNC('day', to_timestamp(timestamp/1e9))::DATE as date,
           open, close, vwap, volume,
           LAG(close) OVER (PARTITION BY ticker ORDER BY timestamp) as prev_close
    FROM read_parquet('/data/polygon/day_aggs/2026-01-*.parquet')
    WHERE volume > 500000
),
gappers AS (
    SELECT *, 
           ROUND((open - prev_close) / prev_close * 100, 2) as gap_pct,
           CASE WHEN close < vwap THEN 1 ELSE 0 END as below_vwap
    FROM daily_data
    WHERE prev_close IS NOT NULL
      AND ABS((open - prev_close) / prev_close) > 0.03  -- Gap > 3%
)
SELECT 
    COUNT(*) as total_gappers,
    SUM(below_vwap) as closed_below_vwap,
    ROUND(SUM(below_vwap) * 100.0 / NULLIF(COUNT(*), 0), 1) as pct_below_vwap,
    ROUND(AVG(gap_pct), 2) as avg_gap_pct
FROM gappers
'''
result = historical_query(sql)
save_output(result, 'weekly_gapper_analysis')

EXAMPLE 2 - MOMENTUM: Stocks with 3+ consecutive up days
─────────────────────────────────────────────────────────────────────────────────
sql = '''
WITH daily_changes AS (
    SELECT ticker,
        DATE_TRUNC('day', to_timestamp(timestamp/1e9))::DATE as date,
        close, open,
        CASE WHEN close > open THEN 1 ELSE 0 END as up_day
    FROM read_parquet('/data/polygon/day_aggs/2026-01-*.parquet')  -- GLOB for multiple days
    WHERE volume > 500000
),
streaks AS (
    SELECT ticker,
        SUM(up_day) as up_days,
        COUNT(*) as total_days
    FROM daily_changes
    GROUP BY ticker
    HAVING COUNT(*) >= 5
)
SELECT ticker as symbol, up_days, total_days,
    ROUND(up_days * 100.0 / total_days, 1) as pct_up_days
FROM streaks
WHERE up_days >= 3
ORDER BY up_days DESC, pct_up_days DESC
LIMIT 20
'''
result = historical_query(sql)
save_output(result, 'momentum_streaks')

EXAMPLE 3 - TOP OF WEEK with breakdown by day
─────────────────────────────────────────────────────────────────────────────────
result = get_period_top_by_day(days=7, top_n=5, direction='up')
save_output(result, 'weekly_top_by_day')

EXAMPLE 4 - RELATIVE VOLUME: Stocks with 3x avg volume
─────────────────────────────────────────────────────────────────────────────────
sql = '''
WITH vol_stats AS (
    SELECT ticker,
        DATE_TRUNC('day', to_timestamp(timestamp/1e9))::DATE as date,
        volume,
        AVG(volume) OVER (PARTITION BY ticker ORDER BY timestamp 
                          ROWS BETWEEN 10 PRECEDING AND 1 PRECEDING) as avg_vol_10d
    FROM read_parquet('/data/polygon/day_aggs/2026-01-*.parquet')  -- GLOB for multiple days
),
latest AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date DESC) as rn
    FROM vol_stats
    WHERE avg_vol_10d > 0
)
SELECT ticker as symbol, date, volume, 
    ROUND(avg_vol_10d, 0) as avg_volume,
    ROUND(volume / avg_vol_10d, 2) as rel_volume
FROM latest
WHERE rn = 1 AND volume / avg_vol_10d >= 3
ORDER BY rel_volume DESC
LIMIT 20
'''
result = historical_query(sql)
save_output(result, 'volume_spikes')

EXAMPLE 5 - INTRADAY: Top by hour range with VWAP status
─────────────────────────────────────────────────────────────────────────────────
sql = '''
WITH bars AS (
    SELECT ticker,
        CASE 
            WHEN EXTRACT(HOUR FROM to_timestamp(window_start/1e9)) < 10 THEN 'open_hour'
            WHEN EXTRACT(HOUR FROM to_timestamp(window_start/1e9)) < 12 THEN 'mid_morning'
            WHEN EXTRACT(HOUR FROM to_timestamp(window_start/1e9)) < 14 THEN 'midday'
            ELSE 'afternoon'
        END as session,
        window_start, open, close, volume
    FROM read_csv_auto('/data/polygon/minute_aggs/2026-01-17.csv.gz')
    WHERE EXTRACT(HOUR FROM to_timestamp(window_start/1e9)) BETWEEN 9 AND 16
),
agg AS (
    SELECT ticker, session,
        FIRST(open ORDER BY window_start) as open_price,
        LAST(close ORDER BY window_start) as close_price,
        SUM(volume) as volume,
        ROUND((LAST(close ORDER BY window_start) - FIRST(open ORDER BY window_start)) 
              / FIRST(open ORDER BY window_start) * 100, 2) as change_pct
    FROM bars
    GROUP BY ticker, session
    HAVING SUM(volume) > 100000
),
ranked AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY session ORDER BY change_pct DESC) as rank
    FROM agg
)
SELECT session, rank, ticker as symbol, change_pct, volume
FROM ranked WHERE rank <= 5
ORDER BY session, rank
'''
result = historical_query(sql)
save_output(result, 'intraday_session_top')

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                               DUCKDB SQL TIPS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Timestamps are NANOSECONDS: to_timestamp(timestamp / 1000000000) or /1e9
- GLOB for multiple files: read_csv_auto('/path/2026-01-*.csv.gz')
- Extract date: DATE_TRUNC('day', to_timestamp(ts/1e9))::DATE
- Extract hour: EXTRACT(HOUR FROM to_timestamp(ts/1e9))
- First/Last in group: FIRST(col ORDER BY ts), LAST(col ORDER BY ts)
- Rank within partition: ROW_NUMBER() OVER (PARTITION BY x ORDER BY y DESC)
- Safe division: NULLIF(denominator, 0)

TIMEOUT: 30 seconds. Always use SQL for multi-symbol queries.""",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code using ONLY sandbox functions. Check DataFrames with .empty"
                },
                "description": {
                    "type": "string",
                    "description": "What this analysis does"
                }
            },
            "required": ["code", "description"]
        }
    },
    {
        "name": "get_ticker_info",
        "description": """Get detailed info about a specific ticker: price, change, volume, market cap,
        sector, industry, company name. Use for simple lookups like 'price of AAPL'.""",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Ticker symbol"
                }
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "get_earnings_calendar",
        "description": """Get earnings calendar with companies reporting on a specific date.
        
        Returns for each company:
        - Symbol, company name
        - Time slot (BMO=Before Market Open, AMC=After Market Close)
        - EPS estimate vs actual (if reported)
        - Revenue estimate vs actual (if reported)
        - Surprise percentage
        - Guidance direction (raised/lowered/maintained)
        
        USE WHEN USER ASKS:
        - "earnings de hoy" / "earnings today"
        - "quien reporta manana" / "who reports tomorrow"
        - "calendario de earnings" / "earnings calendar"
        - "resultados de earnings" / "earnings results"
        - "empresas que reportaron" / "companies that reported"
        """,
        "parameters": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Date in YYYY-MM-DD format. Use 'today' or 'tomorrow' for convenience."
                },
                "status": {
                    "type": "string",
                    "enum": ["scheduled", "reported"],
                    "description": "Filter by status: scheduled (pending) or reported (with results)"
                },
                "time_slot": {
                    "type": "string",
                    "enum": ["BMO", "AMC"],
                    "description": "Filter by time: BMO (before market) or AMC (after market)"
                }
            },
            "required": []
        }
    }
]


# =============================================================================
# TOOL EXECUTION
# =============================================================================

async def execute_tool(
    tool_name: str,
    args: Dict[str, Any],
    context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Execute a tool and return results.
    
    Args:
        tool_name: Name of tool to execute
        args: Arguments for the tool
        context: Execution context (clients, etc.)
    
    Returns:
        Dict with 'success', 'data', and optionally 'error'
    """
    try:
        if tool_name == "get_market_snapshot":
            return await _get_market_snapshot(args, context)
        elif tool_name == "get_historical_data":
            return await _get_historical_data(args, context)
        elif tool_name == "get_top_movers":
            return await _get_top_movers(args, context)
        elif tool_name == "get_top_movers_hourly":
            return await _get_top_movers_hourly(args, context)
        elif tool_name == "classify_synthetic_sectors":
            return await _classify_synthetic_sectors(args, context)
        elif tool_name == "quick_news":
            return await _quick_news(args, context)
        elif tool_name == "research_ticker":
            return await _research_ticker(args, context)
        elif tool_name == "execute_analysis":
            return await _execute_analysis(args, context)
        elif tool_name == "get_ticker_info":
            return await _get_ticker_info(args, context)
        elif tool_name == "get_earnings_calendar":
            return await _get_earnings_calendar(args, context)
        else:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}
    except Exception as e:
        logger.error("tool_execution_error", tool=tool_name, error=str(e))
        return {"success": False, "error": str(e)}


# =============================================================================
# TOOL IMPLEMENTATIONS
# =============================================================================

async def _get_market_snapshot(args: Dict, ctx: Dict) -> Dict:
    """Fetch real-time scanner data."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get("http://scanner:8005/api/scanner/filtered")
            if resp.status_code != 200:
                return {"success": False, "error": "Scanner unavailable"}
            
            data = resp.json()
            df = pd.DataFrame(data)
            
            if df.empty:
                return {"success": False, "error": "No scanner data"}
            
            # Apply filters
            filter_type = args.get("filter_type", "all")
            limit = args.get("limit", 50)
            min_volume = args.get("min_volume")
            min_price = args.get("min_price")
            min_market_cap = args.get("min_market_cap")
            sector = args.get("sector")
            symbols = args.get("symbols")  # Filter by specific symbols
            
            # If specific symbols requested, filter and report which are in scanner
            if symbols:
                symbols_upper = [s.upper() for s in symbols]
                found_df = df[df["symbol"].isin(symbols_upper)]
                found_symbols = set(found_df["symbol"].tolist())
                missing_symbols = [s for s in symbols_upper if s not in found_symbols]
                
                return {
                    "success": True,
                    "data": found_df,
                    "count": len(found_df),
                    "requested_symbols": symbols_upper,
                    "found_in_scanner": list(found_symbols),
                    "not_in_scanner": missing_symbols,
                    "message": f"Found {len(found_symbols)}/{len(symbols_upper)} symbols in scanner"
                }
            
            if min_volume and "volume_today" in df.columns:
                df = df[df["volume_today"] >= min_volume]
            if min_price and "price" in df.columns:
                df = df[df["price"] >= min_price]
            if min_market_cap and "market_cap" in df.columns:
                df = df[df["market_cap"] >= min_market_cap]
            if sector and "sector" in df.columns:
                df = df[df["sector"].str.contains(sector, case=False, na=False)]
            
            # Sort by filter type
            if filter_type == "gainers" and "change_percent" in df.columns:
                df = df.nlargest(limit, "change_percent")
            elif filter_type == "losers" and "change_percent" in df.columns:
                df = df.nsmallest(limit, "change_percent")
            elif filter_type == "volume" and "volume_today" in df.columns:
                df = df.nlargest(limit, "volume_today")
            elif filter_type == "premarket":
                # Use premarket_change_percent (congelado a las 9:30 o actual durante premarket)
                col = "premarket_change_percent"
                if col in df.columns:
                    df = df.dropna(subset=[col]).nlargest(limit, col)
                elif "change_percent" in df.columns:
                    # Fallback: usar change_percent si premarket_change_percent no existe
                    df = df.nlargest(limit, "change_percent")
                else:
                    df = df.head(limit)
            elif filter_type == "postmarket":
                col = "postmarket_change_percent"
                if col in df.columns:
                    df = df.dropna(subset=[col]).nlargest(limit, col)
                else:
                    df = df.head(limit)
            else:
                df = df.head(limit)
            
            result = {
                "success": True,
                "data": df,
                "count": len(df),
                "source": "scanner"
            }
            
            # Generate chart if requested
            generate_chart = args.get("generate_chart", False)
            if generate_chart and not df.empty:
                try:
                    import matplotlib
                    matplotlib.use('Agg')
                    import matplotlib.pyplot as plt
                    import io
                    
                    # Determine which column to use for chart
                    if filter_type == "premarket" and "premarket_change_percent" in df.columns:
                        chart_col = "premarket_change_percent"
                    elif filter_type == "postmarket" and "postmarket_change_percent" in df.columns:
                        chart_col = "postmarket_change_percent"
                    else:
                        chart_col = "change_percent"
                    
                    if chart_col not in df.columns:
                        chart_col = "change_percent"
                    
                    # Prepare data for chart
                    chart_df = df.head(20).copy()
                    chart_df = chart_df.dropna(subset=[chart_col])
                    chart_df = chart_df.sort_values(chart_col, ascending=True)
                    
                    fig, ax = plt.subplots(figsize=(12, max(6, len(chart_df) * 0.4)))
                    colors = ['#ef4444' if x < 0 else '#22c55e' for x in chart_df[chart_col]]
                    bars = ax.barh(chart_df['symbol'], chart_df[chart_col], color=colors)
                    
                    title = f"Top {filter_type.title()}" if filter_type in ['gainers', 'losers', 'premarket', 'postmarket'] else "Market Snapshot"
                    ax.set_xlabel('Change %', fontsize=12)
                    ax.set_title(title, fontsize=14, fontweight='bold')
                    ax.axvline(x=0, color='gray', linestyle='-', linewidth=0.5)
                    
                    for bar, val in zip(bars, chart_df[chart_col]):
                        width = bar.get_width()
                        ax.text(width + 0.3 if width >= 0 else width - 0.3, 
                               bar.get_y() + bar.get_height()/2,
                               f'{val:+.2f}%', va='center', ha='left' if width >= 0 else 'right',
                               fontsize=9)
                    
                    plt.tight_layout()
                    buf = io.BytesIO()
                    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
                    buf.seek(0)
                    result["chart"] = buf.getvalue()
                    plt.close(fig)
                    logger.info("market_snapshot_chart_generated", filter=filter_type, count=len(chart_df))
                except Exception as e:
                    logger.warning("chart_generation_failed", error=str(e))
            
            return result
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _get_historical_data(args: Dict, ctx: Dict) -> Dict:
    """Load historical minute bars from DuckDB files."""
    date_str = args.get("date", "yesterday")
    start_hour = args.get("start_hour")
    end_hour = args.get("end_hour")
    symbols = args.get("symbols", [])
    
    # Resolve date
    now = datetime.now(ET)
    if date_str == "today":
        target_date = now
        file_path = "/data/polygon/minute_aggs/today.parquet"
    elif date_str == "yesterday":
        target_date = now - timedelta(days=1)
        file_path = f"/data/polygon/minute_aggs/{target_date.strftime('%Y-%m-%d')}.csv.gz"
    else:
        target_date = datetime.strptime(date_str, "%Y-%m-%d")
        file_path = f"/data/polygon/minute_aggs/{date_str}.csv.gz"
    
    # Auto-retry with previous days if no data (handles weekends/holidays)
    original_date = date_str
    for retry in range(5):  # Try up to 5 previous days
        if Path(file_path).exists():
            break
        # Try previous day
        if isinstance(target_date, datetime):
            target_date = target_date - timedelta(days=1)
        else:
            target_date = datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=1)
        date_str = target_date.strftime("%Y-%m-%d")
        file_path = f"/data/polygon/minute_aggs/{date_str}.csv.gz"
    
    if not Path(file_path).exists():
        # FALLBACK: Try Polygon API
        logger.info("local_file_missing_trying_polygon", date=original_date, file=file_path)
        try:
            df = await _fetch_polygon_grouped_daily(date_str)
            if df.empty:
                return {"success": False, "error": f"No data for {original_date} (local files missing, Polygon API returned empty)"}
            
            df["hour"] = df["datetime"].dt.hour
            
            # Filter by hour
            if start_hour is not None:
                df = df[df["hour"] >= start_hour]
            if end_hour is not None:
                df = df[df["hour"] < end_hour]
            
            # Filter by symbols
            if symbols:
                df = df[df["symbol"].isin([s.upper() for s in symbols])]
            
            return {
                "success": True,
                "data": df[["symbol", "datetime", "open", "high", "low", "close", "volume"]],
                "count": len(df),
                "date": date_str,
                "source": "polygon_api"
            }
        except Exception as e:
            logger.error("polygon_fallback_failed", error=str(e))
            return {"success": False, "error": f"No local data for {original_date} and Polygon API failed: {e}"}
    
    try:
        if file_path.endswith(".parquet"):
            df = pd.read_parquet(file_path)
            df["datetime"] = pd.to_datetime(df["window_start"], unit="ms", utc=True).dt.tz_convert(ET)
        else:
            df = pd.read_csv(file_path, compression="gzip")
            df["datetime"] = pd.to_datetime(df["window_start"], unit="ns", utc=True).dt.tz_convert(ET)
            if "ticker" in df.columns:
                df = df.rename(columns={"ticker": "symbol"})
        
        df["hour"] = df["datetime"].dt.hour
        
        # Filter by hour
        if start_hour is not None:
            df = df[df["hour"] >= start_hour]
        if end_hour is not None:
            df = df[df["hour"] < end_hour]
        
        # Filter by symbols
        if symbols:
            df = df[df["symbol"].isin([s.upper() for s in symbols])]
        
        return {
            "success": True,
            "data": df[["symbol", "datetime", "open", "high", "low", "close", "volume"]],
            "count": len(df),
            "date": date_str
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _get_top_movers(args: Dict, ctx: Dict) -> Dict:
    """Get pre-aggregated top movers using DuckDB layer with Polygon API fallback."""
    date_str = args.get("date", "yesterday")
    start_hour = args.get("start_hour")
    end_hour = args.get("end_hour")
    direction = args.get("direction", "up")
    limit = args.get("limit", 20)
    min_volume = args.get("min_volume", 100000)
    
    # Get historical data and aggregate
    hist_result = await _get_historical_data({
        "date": date_str,
        "start_hour": start_hour,
        "end_hour": end_hour
    }, ctx)
    
    if not hist_result["success"]:
        # Try direct Polygon API fallback for top movers
        logger.info("top_movers_trying_polygon_fallback", date=date_str)
        try:
            now = datetime.now(ET)
            if date_str == "today":
                api_date = now.strftime('%Y-%m-%d')
            elif date_str == "yesterday":
                api_date = (now - timedelta(days=1)).strftime('%Y-%m-%d')
            else:
                api_date = date_str
            
            df = await _fetch_polygon_top_movers(api_date, direction, limit, min_volume)
            if not df.empty:
                logger.info("top_movers_polygon_success", count=len(df))
                return {
                    "success": True,
                    "data": df,
                    "count": len(df),
                    "direction": direction,
                    "source": "polygon_api"
                }
        except Exception as e:
            logger.error("top_movers_polygon_failed", error=str(e))
        
        return hist_result  # Return original error
    
    df = hist_result["data"]
    
    # Aggregate by symbol
    agg = df.groupby("symbol").agg({
        "open": "first",
        "close": "last",
        "high": "max",
        "low": "min",
        "volume": "sum"
    }).reset_index()
    
    agg["change_pct"] = ((agg["close"] - agg["open"]) / agg["open"] * 100).round(2)
    agg = agg[agg["volume"] >= min_volume]
    
    # Sort
    ascending = direction == "down"
    agg = agg.sort_values("change_pct", ascending=ascending).head(limit)
    
    return {
        "success": True,
        "data": agg[["symbol", "open", "close", "change_pct", "volume"]],
        "count": len(agg),
        "direction": direction
    }


async def _get_top_movers_hourly(args: Dict, ctx: Dict) -> Dict:
    """
    Get top mover for EACH hour range during a trading day.
    
    Uses concurrent requests for efficiency with retry on failure.
    Falls back to Polygon API if local data unavailable.
    Supports market cap filtering via scanner data.
    """
    date_str = args.get("date", "today")
    start_hour = args.get("start_hour", 9)  # Market open
    end_hour = args.get("end_hour", 16)      # Market close
    direction = args.get("direction", "up")
    min_volume = args.get("min_volume", 100000)
    min_market_cap = args.get("min_market_cap")
    
    # Resolve date for API
    now = datetime.now(ET)
    if date_str == "today":
        api_date = now.strftime('%Y-%m-%d')
    elif date_str == "yesterday":
        api_date = (now - timedelta(days=1)).strftime('%Y-%m-%d')
    else:
        api_date = date_str
    
    logger.info("top_movers_hourly_start", date=api_date, start=start_hour, end=end_hour, 
                min_market_cap=min_market_cap)
    
    # Get eligible symbols by market cap if filter specified
    # Query tickers_unified via API Gateway (has all symbols, not just scanner's ~250)
    eligible_symbols = None
    if min_market_cap:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "http://api_gateway:8000/api/symbols/by-market-cap",
                    params={"min_market_cap": min_market_cap}
                )
                if resp.status_code == 200:
                    data = resp.json()
                    eligible_symbols = set(data.get("symbols", []))
                    logger.info("market_cap_filter_applied", 
                               min_cap=min_market_cap, 
                               eligible_count=len(eligible_symbols))
        except Exception as e:
            logger.warning("market_cap_filter_failed", error=str(e))
    
    async def fetch_hour_range(hour: int) -> Dict:
        """Fetch top mover for a single hour range."""
        try:
            # If market cap filter, get ALL movers (no limit) then filter
            # Otherwise just get top 1
            limit = 5000 if eligible_symbols else 1  # 5000 = effectively no limit
            
            result = await _get_top_movers({
                "date": date_str,
                "start_hour": hour,
                "end_hour": hour + 1,
                "direction": direction,
                "limit": limit,
                "min_volume": min_volume
            }, ctx)
            
            if result["success"] and result["count"] > 0:
                df = result["data"]
                
                # Filter by market cap if applicable
                if eligible_symbols:
                    original_count = len(df)
                    df = df[df["symbol"].isin(eligible_symbols)]
                    if df.empty:
                        logger.warning("no_eligible_symbols_in_hour", 
                                      hour=hour, 
                                      checked=original_count,
                                      eligible_total=len(eligible_symbols))
                        return None
                
                row = df.iloc[0]
                return {
                    "hour_range": f"{hour:02d}:00-{hour+1:02d}:00",
                    "symbol": row["symbol"],
                    "change_pct": row["change_pct"],
                    "volume": row.get("volume", 0),
                    "source": result.get("source", "local")
                }
            return None
        except Exception as e:
            logger.warning("hourly_fetch_failed", hour=hour, error=str(e))
            return None
    
    # Run concurrent requests for all hour ranges
    tasks = [fetch_hour_range(h) for h in range(start_hour, end_hour)]
    results = await asyncio.gather(*tasks)
    
    # Filter out None results and build DataFrame
    valid_results = [r for r in results if r is not None]
    
    if not valid_results:
        error_msg = f"No data available for {api_date}"
        if min_market_cap:
            error_msg += f" with market cap >= ${min_market_cap:,.0f}"
        return {"success": False, "error": error_msg}
    
    df = pd.DataFrame(valid_results)
    
    logger.info("top_movers_hourly_complete", count=len(df), date=api_date)
    
    return {
        "success": True,
        "data": df,
        "count": len(df),
        "direction": direction,
        "date": api_date,
        "hour_range": f"{start_hour:02d}:00-{end_hour:02d}:00",
        "filters": {"min_volume": min_volume, "min_market_cap": min_market_cap}
    }


async def _classify_synthetic_sectors(args: Dict, ctx: Dict) -> Dict:
    """Classify tickers into thematic sectors."""
    from research.synthetic_sectors import (
        classify_tickers_into_synthetic_sectors,
        calculate_synthetic_sector_performance,
        clean_tickers_dataframe
    )
    
    date_str = args.get("date", "today")
    max_sectors = args.get("max_sectors", 15)
    input_data = args.get("input_data")  # DataFrame, dict, or serialized dataframe from previous node
    
    # Filter parameters
    min_market_cap = args.get("min_market_cap")
    min_volume = args.get("min_volume")
    min_price = args.get("min_price")
    max_price = args.get("max_price")
    generate_chart = args.get("generate_chart", False)
    min_tickers_per_sector = args.get("min_tickers_per_sector")
    
    llm_client = ctx.get("llm_client")
    if not llm_client:
        return {"success": False, "error": "LLM client required"}
    
    df = None
    
    # Priority 1: Use input data from connected node (e.g., Scanner)
    if input_data is not None:
        logger.info("synthetic_sectors_received_input", 
                   input_type=type(input_data).__name__,
                   input_keys=list(input_data.keys()) if isinstance(input_data, dict) else None)
        
        # Case A: Direct DataFrame (unlikely after serialization)
        if isinstance(input_data, pd.DataFrame) and not input_data.empty:
            df = input_data
            logger.info("synthetic_sectors_using_direct_dataframe", rows=len(df))
        
        # Case B: Serialized format from workflow: { type: 'dataframe', columns: [...], data: [...] }
        elif isinstance(input_data, dict) and input_data.get('type') == 'dataframe':
            records = input_data.get('data', [])
            if records:
                df = pd.DataFrame(records)
                logger.info("synthetic_sectors_using_serialized_dataframe", rows=len(df))
        
        # Case C: Nested in result dict: { success: True, data: { type: 'dataframe', ... } }
        elif isinstance(input_data, dict):
            inner = input_data.get('data')
            if isinstance(inner, pd.DataFrame) and not inner.empty:
                df = inner
                logger.info("synthetic_sectors_using_nested_dataframe", rows=len(df))
            elif isinstance(inner, dict) and inner.get('type') == 'dataframe':
                records = inner.get('data', [])
                if records:
                    df = pd.DataFrame(records)
                    logger.info("synthetic_sectors_using_nested_serialized_dataframe", rows=len(df))
    
    # Priority 2: Fetch data ourselves if no input
    if df is None or df.empty:
        logger.info("synthetic_sectors_fetching_own_data", date=date_str)
        
        # Try scanner first if "today"
        if date_str == "today":
            snapshot = await _get_market_snapshot({"limit": 1000}, ctx)
            if snapshot["success"] and isinstance(snapshot.get("data"), pd.DataFrame) and not snapshot["data"].empty:
                df = snapshot["data"]
            else:
                # Fallback to yesterday's historical data
                logger.info("synthetic_sectors_scanner_empty_using_historical")
                date_str = "yesterday"
        
        # Use historical data
        if df is None or (isinstance(df, pd.DataFrame) and df.empty):
            # For historical: get top 500 movers (250 gainers + 250 losers)
            gainers = await _get_top_movers({
                "date": date_str,
                "limit": 250,
                "min_volume": 50000,
                "direction": "up"
            }, ctx)
            losers = await _get_top_movers({
                "date": date_str,
                "limit": 250,
                "min_volume": 50000,
                "direction": "down"
            }, ctx)
            
            # Combine gainers and losers
            dfs = []
            if gainers["success"] and not gainers["data"].empty:
                dfs.append(gainers["data"])
            if losers["success"] and not losers["data"].empty:
                dfs.append(losers["data"])
            
            if not dfs:
                return {"success": False, "error": "No historical data found"}
            
            df = pd.concat(dfs, ignore_index=True).drop_duplicates(subset="symbol")
            df["change_percent"] = df["change_pct"]
            df["price"] = df["close"]
            df["volume_today"] = df["volume"]
            df["market_cap"] = 0
    
    # Apply filters BEFORE classification
    original_count = len(df)
    
    if min_market_cap and "market_cap" in df.columns:
        df = df[df["market_cap"] >= min_market_cap]
        logger.info("filter_applied_market_cap", min=min_market_cap, before=original_count, after=len(df))
    
    if min_volume and "volume_today" in df.columns:
        df = df[df["volume_today"] >= min_volume]
        logger.info("filter_applied_volume", min=min_volume, after=len(df))
    
    if min_price and "price" in df.columns:
        df = df[df["price"] >= min_price]
        logger.info("filter_applied_min_price", min=min_price, after=len(df))
    
    if max_price and "price" in df.columns:
        df = df[df["price"] <= max_price]
        logger.info("filter_applied_max_price", max=max_price, after=len(df))
    
    if df.empty:
        return {"success": False, "error": f"No tickers match the filters (started with {original_count})"}
    
    logger.info("synthetic_sectors_after_filters", 
               original=original_count, 
               filtered=len(df),
               filters_applied={
                   "min_market_cap": min_market_cap,
                   "min_volume": min_volume,
                   "min_price": min_price,
                   "max_price": max_price
               })
    
    # Classify
    classified = await classify_tickers_into_synthetic_sectors(
        df, llm_client, max_sectors=max_sectors
    )
    
    if classified.empty:
        return {"success": False, "error": "Classification failed"}
    
    # Clean up the tickers dataframe (remove premarket if all zeros, etc.)
    classified = clean_tickers_dataframe(classified)
    
    performance = calculate_synthetic_sector_performance(classified)
    
    # Filter by minimum tickers per sector if specified
    if min_tickers_per_sector and not performance.empty:
        original_sectors = len(performance)
        # Performance has 'ticker_count' column
        performance = performance[performance['ticker_count'] >= min_tickers_per_sector]
        
        if performance.empty:
            return {"success": False, "error": f"No sectors have >= {min_tickers_per_sector} tickers (had {original_sectors} sectors)"}
        
        # Also filter the classified tickers to only include tickers from qualifying sectors
        valid_sectors = performance['sector'].tolist()
        classified = classified[classified['synthetic_sector'].isin(valid_sectors)]
        
        logger.info("filter_min_tickers_per_sector", 
                   min_required=min_tickers_per_sector,
                   original_sectors=original_sectors,
                   filtered_sectors=len(performance))
    
    # Generate chart if requested
    chart_data = None
    if generate_chart and not performance.empty:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            import io
            
            # Sort by avg_change for the chart
            perf_sorted = performance.sort_values('avg_change', ascending=True)
            
            # Create horizontal bar chart
            fig, ax = plt.subplots(figsize=(12, max(6, len(perf_sorted) * 0.4)))
            
            colors = ['#ef4444' if x < 0 else '#22c55e' for x in perf_sorted['avg_change']]
            bars = ax.barh(perf_sorted['sector'], perf_sorted['avg_change'], color=colors)
            
            ax.set_xlabel('Average Change %', fontsize=12)
            ax.set_title('Synthetic ETF Sectors - Performance', fontsize=14, fontweight='bold')
            ax.axvline(x=0, color='gray', linestyle='-', linewidth=0.5)
            
            # Add value labels
            for bar, val in zip(bars, perf_sorted['avg_change']):
                width = bar.get_width()
                ax.text(width + 0.3 if width >= 0 else width - 0.3, 
                       bar.get_y() + bar.get_height()/2,
                       f'{val:+.2f}%', va='center', ha='left' if width >= 0 else 'right',
                       fontsize=9)
            
            plt.tight_layout()
            
            # Save to bytes
            buf = io.BytesIO()
            plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
            buf.seek(0)
            chart_data = buf.getvalue()
            plt.close(fig)
            
            logger.info("synthetic_sectors_chart_generated", size=len(chart_data))
        except Exception as e:
            logger.warning("chart_generation_failed", error=str(e))
    
    # Convert DataFrames to JSON-serializable dicts
    def convert_to_native(obj):
        """Convert numpy types to Python native types."""
        if hasattr(obj, 'item'):  # numpy scalar
            return obj.item()
        elif isinstance(obj, dict):
            return {k: convert_to_native(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_to_native(i) for i in obj]
        return obj
    
    sectors_data = convert_to_native(performance.to_dict('records')) if not performance.empty else []
    tickers_data = convert_to_native(classified.to_dict('records')) if not classified.empty else []
    
    result = {
        "success": True,
        "sectors": sectors_data,
        "tickers": tickers_data,
        "sector_count": int(classified["synthetic_sector"].nunique()) if not classified.empty else 0
    }
    
    if chart_data:
        import base64
        result["chart"] = base64.b64encode(chart_data).decode('utf-8')
    
    return result


async def _quick_news(args: Dict, ctx: Dict) -> Dict:
    """Fast news lookup from Benzinga (<1 second)."""
    from research.grok_research import fetch_benzinga_news
    
    # Accept both 'symbol' and 'ticker' parameter names for compatibility
    symbol = (args.get("symbol") or args.get("ticker") or "").upper()
    limit = args.get("limit", 5)
    
    if not symbol:
        return {"success": False, "error": "Symbol required"}
    
    news = await fetch_benzinga_news(symbol, limit=limit)
    
    # Format news for display
    formatted_news = []
    for n in (news or []):
        formatted_news.append({
            "title": n.get("title", ""),
            "summary": n.get("summary", "")[:200] + "..." if len(n.get("summary", "")) > 200 else n.get("summary", ""),
            "published": n.get("published", ""),
            "source": n.get("source", "Benzinga")
        })
    
    # Return under "data" key for proper collection by core
    return {
        "success": True,
        "data": {
            "symbol": symbol,
            "news": formatted_news,
            "count": len(formatted_news),
            "deep_research_available": True
        }
    }


async def _research_ticker(args: Dict, ctx: Dict) -> Dict:
    """Deep research using Grok + Benzinga News combined."""
    from research.grok_research import research_ticker_combined
    
    # Accept both 'symbol' and 'ticker' parameter names
    symbol = args.get("symbol") or args.get("ticker", "")
    symbol = symbol.upper() if symbol else ""
    include_technicals = args.get("include_technicals", True)
    
    if not symbol:
        return {"success": False, "error": "Symbol required"}
    
    # Usa research_ticker_combined que consulta Grok + Benzinga en paralelo
    result = await research_ticker_combined(
        ticker=symbol,
        include_technicals=include_technicals
    )
    
    if result.get("error"):
        return {"success": False, "error": result["error"]}
    
    return {
        "success": True,
        "data": result
    }


async def _execute_analysis(args: Dict, ctx: Dict) -> Dict:
    """Execute custom analysis in sandbox with auto-correction on errors."""
    from sandbox.manager import SandboxManager
    
    code = args.get("code", "")
    description = args.get("description", "Custom analysis")
    max_retries = 2  # Max correction attempts
    
    if not code:
        return {"success": False, "error": "Code required"}
    
    sandbox = ctx.get("sandbox") or SandboxManager()
    
    # Inject available data
    data = {}
    if "scanner_data" in ctx:
        data["scanner_data"] = ctx["scanner_data"]
    if "historical_bars" in ctx:
        data["historical_bars"] = ctx["historical_bars"]
    
    # Execute with auto-correction loop
    current_code = code
    for attempt in range(max_retries + 1):
        result = await sandbox.execute(current_code, data=data)
        
        if result.success:
            return {
                "success": True,
                "stdout": result.stdout,
                "outputs": result.output_files,
                "corrected": attempt > 0,  # Flag if code was auto-corrected
                "attempts": attempt + 1
            }
        
        # If failed and we have retries left, try to auto-correct
        if attempt < max_retries and result.error_message:
            logger.info("sandbox_error_attempting_correction", 
                       attempt=attempt + 1, 
                       error=result.error_message[:200])
            
            corrected_code = await _auto_correct_code(
                current_code, 
                result.error_message, 
                ctx
            )
            
            if corrected_code and corrected_code != current_code:
                logger.info("code_auto_corrected", attempt=attempt + 1)
                current_code = corrected_code
                continue
            else:
                # Couldn't correct, break out
                break
    
    # All attempts failed
    return {
        "success": False,
        "stdout": result.stdout,
        "outputs": result.output_files,
        "error": result.error_message,
        "attempts": max_retries + 1
    }


async def _auto_correct_code(code: str, error: str, ctx: Dict) -> Optional[str]:
    """Use LLM to auto-correct code based on error message."""
    from google import genai
    from google.genai import types
    import os
    
    try:
        client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
        
        correction_prompt = f"""You are a Python/DuckDB code fixer. Fix the following code based on the error.

ORIGINAL CODE:
```python
{code}
```

ERROR:
{error}

AVAILABLE FUNCTIONS in sandbox:
- get_minute_bars(date_str, symbol=None, start_hour=None, end_hour=None) -> DataFrame
- get_top_movers(date_str, start_hour=None, end_hour=None, min_volume=100000, limit=20, ascending=False, direction=None)
- available_dates() -> list of date strings
- historical_query(sql) -> DataFrame (uses DuckDB)
- save_output(data, 'name') -> saves for display

DUCKDB-SPECIFIC FIXES:
- window_start is BIGINT (nanoseconds since epoch), NOT a timestamp
- To extract hour: EXTRACT(HOUR FROM to_timestamp(window_start / 1000000000))
- To format time: strftime(to_timestamp(window_start / 1000000000), '%H:%M')
- Don't use strftime directly on BIGINT - convert to timestamp first!
- For timezone: Use AT TIME ZONE 'America/New_York' after to_timestamp()

EXAMPLE FIX for hour extraction:
  WRONG: strftime('%H', window_start/1000000000, 'unixepoch')
  RIGHT: EXTRACT(HOUR FROM to_timestamp(window_start / 1000000000) AT TIME ZONE 'America/New_York')

RULES:
1. Fix ONLY the error, don't change the logic
2. Return ONLY the corrected Python code, no explanations
3. Keep all the original query structure

CORRECTED CODE:"""

        # Use async API for non-blocking execution
        response = await client.aio.models.generate_content(
            model="gemini-2.0-flash",
            contents=[types.Content(
                role="user",
                parts=[types.Part(text=correction_prompt)]
            )],
            config=types.GenerateContentConfig(
                temperature=0.1,  # Low temperature for precise corrections
                max_output_tokens=4096
            )
        )
        
        if response.text:
            # Extract code from response (might be wrapped in ```python```)
            corrected = response.text.strip()
            if "```python" in corrected:
                corrected = corrected.split("```python")[1].split("```")[0].strip()
            elif "```" in corrected:
                corrected = corrected.split("```")[1].split("```")[0].strip()
            
            return corrected
    
    except Exception as e:
        logger.warning("auto_correct_failed", error=str(e))
    
    return None


async def _get_ticker_info(args: Dict, ctx: Dict) -> Dict:
    """Get basic info about a ticker."""
    # Accept both 'symbol' and 'ticker' parameter names for compatibility
    symbol = (args.get("symbol") or args.get("ticker") or "").upper()
    
    if not symbol:
        return {"success": False, "error": "Symbol required"}
    
    # Try scanner first (real-time data)
    snapshot = await _get_market_snapshot({"limit": 2000}, ctx)
    if snapshot["success"]:
        df = snapshot["data"]
        ticker_data = df[df["symbol"] == symbol]
        if not ticker_data.empty:
            row = ticker_data.iloc[0]
            return {
                "success": True,
                "data": {
                    "symbol": symbol,
                    "price": row.get("price"),
                    "change_percent": row.get("change_percent"),
                    "volume": row.get("volume_today"),
                    "market_cap": row.get("market_cap"),
                    "sector": row.get("sector"),
                    "source": "scanner"
                }
            }
    
    # Fallback: try historical data (today)
    try:
        hist = await _get_historical_data({"date": "today", "symbols": [symbol]}, ctx)
        if hist["success"] and hist["count"] > 0:
            df = hist["data"]
            last_bar = df.iloc[-1]
            first_bar = df.iloc[0]
            change = ((last_bar["close"] - first_bar["open"]) / first_bar["open"] * 100)
            return {
                "success": True,
                "data": {
                    "symbol": symbol,
                    "price": float(last_bar["close"]),
                    "change_percent": round(change, 2),
                    "volume": int(df["volume"].sum()),
                    "source": "historical"
                }
            }
    except Exception:
        pass
    
    # Ticker not found in any source
    return {
        "success": True,  # Return success but with message
        "data": {
            "symbol": symbol,
            "message": f"Ticker {symbol} not found in current market data. It may not be actively trading.",
            "source": "none"
        }
    }


# =============================================================================
# EARNINGS CALENDAR
# =============================================================================

async def _get_earnings_calendar(args: Dict, ctx: Dict) -> Dict:
    """
    Get earnings calendar for a specific date via API Gateway.
    Returns structured data with pre-formatted analysis for LLM.
    """
    import aiohttp
    from datetime import datetime, date, timedelta
    import os
    
    date_input = args.get("date", "today")
    status = args.get("status")
    time_slot = args.get("time_slot")
    
    # Parse date
    today = datetime.now().date()
    if date_input == "today":
        target_date = today
    elif date_input == "tomorrow":
        target_date = today + timedelta(days=1)
    elif date_input == "yesterday":
        target_date = today - timedelta(days=1)
    else:
        try:
            target_date = date.fromisoformat(date_input)
        except ValueError:
            target_date = today
    
    # Build API URL
    api_url = os.getenv("API_GATEWAY_URL", "http://api_gateway:8000")
    url = f"{api_url}/api/v1/earnings/calendar?date={target_date}"
    if status:
        url += f"&status={status}"
    if time_slot:
        url += f"&time_slot={time_slot.upper()}"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return {"success": False, "error": f"API error {resp.status}"}
                
                data = await resp.json()
        
        reports = data.get("reports", [])
        if not reports:
            return {
                "success": True,
                "date": str(target_date),
                "count": 0,
                "analysis": f"No hay earnings programados para {target_date}."
            }
        
        # Build structured analysis
        beats = []
        misses = []
        scheduled = []
        
        for r in reports:
            symbol = r.get("symbol", "")
            company = r.get("company_name", symbol)
            slot = r.get("time_slot", "TBD")
            quarter = r.get("fiscal_quarter", "")
            eps_est = r.get("eps_estimate")
            eps_act = r.get("eps_actual")
            eps_surp = r.get("eps_surprise_pct")
            rev_est = r.get("revenue_estimate")
            rev_act = r.get("revenue_actual")
            rev_surp = r.get("revenue_surprise_pct")
            beat_eps = r.get("beat_eps")
            beat_rev = r.get("beat_revenue")
            guidance = r.get("guidance_direction")
            highlights = r.get("key_highlights", [])
            guid_comment = r.get("guidance_commentary", "")
            status_r = r.get("status", "scheduled")
            
            # Format revenue
            def fmt_rev(v):
                if not v: return "N/A"
                if v >= 1e9: return f"${v/1e9:.1f}B"
                if v >= 1e6: return f"${v/1e6:.0f}M"
                return f"${v:,.0f}"
            
            entry = {
                "ticker": symbol,
                "company": company,
                "quarter": quarter,
                "time": slot,
                "eps": {
                    "estimate": f"${eps_est:.2f}" if eps_est else "N/A",
                    "actual": f"${eps_act:.2f}" if eps_act else "Pending",
                    "surprise": f"{eps_surp:+.1f}%" if eps_surp else None,
                    "beat": beat_eps
                },
                "revenue": {
                    "estimate": fmt_rev(rev_est),
                    "actual": fmt_rev(rev_act) if rev_act else "Pending",
                    "surprise": f"{rev_surp:+.1f}%" if rev_surp else None,
                    "beat": beat_rev
                },
                "guidance": guidance or "none",
                "guidance_detail": guid_comment if guid_comment else None,
                "highlights": highlights[:3] if highlights else None,
                "status": status_r
            }
            
            if status_r == "reported":
                if beat_eps:
                    beats.append(entry)
                else:
                    misses.append(entry)
            else:
                scheduled.append(entry)
        
        # Build summary text
        total = len(reports)
        total_reported = len(beats) + len(misses)
        total_scheduled = len(scheduled)
        beat_rate = (len(beats) / total_reported * 100) if total_reported > 0 else 0
        
        summary_parts = [f"Earnings {target_date}: {total} companies"]
        if total_reported > 0:
            summary_parts.append(f"{total_reported} reported ({len(beats)} beat, {len(misses)} miss, {beat_rate:.0f}% beat rate)")
        if total_scheduled > 0:
            summary_parts.append(f"{total_scheduled} pending")
        
        return {
            "success": True,
            "date": str(target_date),
            "summary": " | ".join(summary_parts),
            "stats": {
                "total": total,
                "reported": total_reported,
                "scheduled": total_scheduled,
                "beats": len(beats),
                "misses": len(misses),
                "beat_rate_pct": round(beat_rate, 1)
            },
            "beats": beats,
            "misses": misses,
            "scheduled": scheduled
        }
        
    except Exception as e:
        logger.error("earnings_calendar_tool_error", error=str(e))
        return {"success": False, "error": str(e)}
