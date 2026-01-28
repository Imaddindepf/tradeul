"""
Schema Definitions and Prompts for AI Agent Analysis
=====================================================
This module provides the data schema reference and prompt templates
for the execute_analysis tool. The schema must match the actual
Polygon flat file structure.
"""

from datetime import datetime, timedelta
from typing import Optional
import pytz

ET = pytz.timezone("America/New_York")


def get_current_date() -> str:
    """Get current date in YYYY-MM-DD format (Eastern Time).
    
    Returns:
        Current date string, e.g., '2026-01-22'
    """
    return datetime.now(ET).strftime("%Y-%m-%d")


def get_previous_trading_day(date_str: Optional[str] = None) -> str:
    """Get previous trading day (skipping weekends).
    
    Args:
        date_str: Optional date string. If None, uses today.
        
    Returns:
        Previous trading day in YYYY-MM-DD format
    """
    if date_str:
        current = datetime.strptime(date_str, "%Y-%m-%d")
    else:
        current = datetime.now(ET)
    
    # Go back one day
    prev = current - timedelta(days=1)
    
    # Skip weekends
    while prev.weekday() >= 5:  # Saturday = 5, Sunday = 6
        prev -= timedelta(days=1)
    
    return prev.strftime("%Y-%m-%d")


def get_analysis_system_prompt(granularity: str = "daily") -> str:
    """Build system prompt for execute_analysis tool.
    
    This prompt provides the LLM with:
    - Current date context
    - Complete data schema for Polygon flat files
    - Common analysis patterns
    - Available sandbox functions
    - Working SQL examples
    
    Args:
        granularity: 'daily' for day_aggs focus, 'minute' for intraday focus
        
    Returns:
        Complete system prompt string
    """
    current_date = get_current_date()
    prev_date = get_previous_trading_day(current_date)
    
    # Calculate date for "last week" queries
    week_start = (datetime.now(ET) - timedelta(days=7)).strftime("%Y-%m-%d")
    month_prefix = datetime.now(ET).strftime("%Y-%m")
    
    return f"""You are a financial data analyst with access to market data via DuckDB SQL.
Execute Python code to answer the user's question about market data.

═══════════════════════════════════════════════════════════════════════════════
                              CURRENT CONTEXT
═══════════════════════════════════════════════════════════════════════════════
Current Date: {current_date}
Previous Trading Day: {prev_date}
Month Prefix for GLOBs: {month_prefix}

═══════════════════════════════════════════════════════════════════════════════
                              DATA SCHEMA REFERENCE
═══════════════════════════════════════════════════════════════════════════════

DAY_AGGS (daily candles) - USE FOR: week/month analysis, gaps, multi-day trends
───────────────────────────────────────────────────────────────────────────────
Path: /data/polygon/day_aggs/YYYY-MM-DD.parquet  ← PREFERRED (10-15x faster)
      /data/polygon/day_aggs/YYYY-MM-DD.csv.gz   ← Fallback
Glob: /data/polygon/day_aggs/{month_prefix}-*.parquet (for current month)

Columns:
  ticker        VARCHAR   Stock symbol (e.g., 'AAPL', 'TSLA')
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
───────────────────────────────────────────────────────────────────────────────
Path: /data/polygon/minute_aggs/YYYY-MM-DD.parquet  ← PREFERRED
      /data/polygon/minute_aggs/YYYY-MM-DD.csv.gz   ← Fallback  
Today: /data/polygon/minute_aggs/today.parquet (always current day)

Columns:
  ticker        VARCHAR   Stock symbol
  window_start  BIGINT    Unix timestamp in NANOSECONDS (divide by 1e9)
  open          DOUBLE    Opening price of minute
  high          DOUBLE    High of minute
  low           DOUBLE    Low of minute
  close         DOUBLE    Closing price of minute
  volume        BIGINT    Volume in that minute

Size: ~500MB CSV.gz per file, ~4M rows (Parquet is ~200MB)

═══════════════════════════════════════════════════════════════════════════════
                           COMMON ANALYSIS PATTERNS
═══════════════════════════════════════════════════════════════════════════════

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
  - Use ROW_NUMBER() for ranking

VOLUME ANALYSIS:
  - Relative volume = today_volume / avg_volume_N_days
  - Volume spike = volume > 2x average
  - Use window functions for rolling averages

TIME-BASED (minute_aggs):
  - Premarket: hour < 9 (4:00-9:30 ET)
  - Morning: hour >= 9 AND hour < 12
  - Afternoon: hour >= 12 AND hour < 16
  - Afterhours: hour >= 16

═══════════════════════════════════════════════════════════════════════════════
                              AVAILABLE FUNCTIONS
═══════════════════════════════════════════════════════════════════════════════

REQUIRED:
  historical_query(sql: str) -> pd.DataFrame    Execute DuckDB SQL query
  save_output(dataframe, 'name')                REQUIRED to return results!

HELPERS (pre-built for convenience):
  get_period_top_movers(days, limit, min_volume, direction)  Top gainers/losers
  get_period_top_by_day(days, top_n, direction)              Top N per day
  get_daily_bars(days, symbol)                               Daily OHLCV
  get_top_movers(date_str, limit, min_volume, direction)     Single day movers
  get_minute_bars(date_str, symbol)                          Minute bars

TECHNICAL INDICATORS:
  calculate_rsi(df, period=14)         RSI indicator
  calculate_macd(df)                   MACD with signal line
  calculate_bollinger_bands(df)        Bollinger Bands
  calculate_atr(df, period=14)         Average True Range

VISUALIZATION:
  create_chart(matplotlib_figure)      Save chart to output

═══════════════════════════════════════════════════════════════════════════════
                                  EXAMPLES
═══════════════════════════════════════════════════════════════════════════════

⚠️ CRITICAL INSTRUCTIONS:
1. ALWAYS use current dates ({month_prefix}-XX), NOT old dates like 2023!
2. Use read_parquet() for .parquet files (10-15x faster than CSV)
3. For multi-day analysis, use GLOB: read_parquet('/data/polygon/day_aggs/{month_prefix}-*.parquet')
4. ALWAYS call save_output(result, 'name') to return results!
5. Handle empty DataFrames with .empty check

EXAMPLE 1 - GAP ANALYSIS: Gappers that closed below VWAP
───────────────────────────────────────────────────────────────────────────────
sql = '''
WITH yesterday AS (
    SELECT ticker, close as prev_close
    FROM read_parquet('/data/polygon/day_aggs/{prev_date}.parquet')
),
today AS (
    SELECT ticker, open, high, low, close, volume, vwap
    FROM read_parquet('/data/polygon/day_aggs/{current_date}.parquet')
)
SELECT 
    t.ticker, 
    ROUND(y.prev_close, 2) as prev_close,
    ROUND(t.open, 2) as open,
    ROUND(t.close, 2) as close,
    ROUND(t.vwap, 2) as vwap,
    t.volume,
    ROUND((t.open - y.prev_close) / y.prev_close * 100, 2) as gap_pct,
    CASE WHEN t.close < t.vwap THEN 'YES' ELSE 'NO' END as below_vwap
FROM today t
JOIN yesterday y ON t.ticker = y.ticker
WHERE y.prev_close > 0.5  -- Filter penny stocks
  AND (t.open - y.prev_close) / y.prev_close > 0.03  -- Gap > 3%
  AND t.volume > 500000
ORDER BY gap_pct DESC
LIMIT 20
'''
result = historical_query(sql)
save_output(result, 'gappers_below_vwap')

EXAMPLE 2 - WEEKLY TOP MOVERS (using GLOB for multiple days)
───────────────────────────────────────────────────────────────────────────────
sql = '''
WITH daily_changes AS (
    SELECT 
        ticker,
        DATE_TRUNC('day', to_timestamp(timestamp/1e9))::DATE as date,
        open, close, volume,
        ROUND((close - open) / open * 100, 2) as daily_change
    FROM read_parquet('/data/polygon/day_aggs/{month_prefix}-*.parquet')
    WHERE volume > 500000
),
aggregated AS (
    SELECT 
        ticker,
        COUNT(*) as trading_days,
        SUM(daily_change) as total_change,
        AVG(daily_change) as avg_daily_change,
        SUM(volume) as total_volume
    FROM daily_changes
    GROUP BY ticker
    HAVING COUNT(*) >= 3  -- At least 3 trading days
)
SELECT 
    ticker as symbol,
    trading_days,
    ROUND(total_change, 2) as week_change_pct,
    ROUND(avg_daily_change, 2) as avg_daily_pct,
    total_volume
FROM aggregated
ORDER BY total_change DESC
LIMIT 20
'''
result = historical_query(sql)
save_output(result, 'weekly_top_movers')

EXAMPLE 3 - MOMENTUM: Consecutive up days
───────────────────────────────────────────────────────────────────────────────
sql = '''
WITH daily_data AS (
    SELECT 
        ticker,
        DATE_TRUNC('day', to_timestamp(timestamp/1e9))::DATE as date,
        close, open,
        CASE WHEN close > open THEN 1 ELSE 0 END as up_day
    FROM read_parquet('/data/polygon/day_aggs/{month_prefix}-*.parquet')
    WHERE volume > 500000
),
streaks AS (
    SELECT 
        ticker,
        SUM(up_day) as up_days,
        COUNT(*) as total_days
    FROM daily_data
    GROUP BY ticker
    HAVING COUNT(*) >= 5
)
SELECT 
    ticker as symbol, 
    up_days, 
    total_days,
    ROUND(up_days * 100.0 / total_days, 1) as pct_up_days
FROM streaks
WHERE up_days >= 3
ORDER BY up_days DESC, pct_up_days DESC
LIMIT 20
'''
result = historical_query(sql)
save_output(result, 'momentum_streaks')

EXAMPLE 4 - VOLUME SPIKES: 3x average volume
───────────────────────────────────────────────────────────────────────────────
sql = '''
WITH vol_stats AS (
    SELECT 
        ticker,
        DATE_TRUNC('day', to_timestamp(timestamp/1e9))::DATE as date,
        volume,
        AVG(volume) OVER (
            PARTITION BY ticker 
            ORDER BY timestamp 
            ROWS BETWEEN 10 PRECEDING AND 1 PRECEDING
        ) as avg_vol_10d
    FROM read_parquet('/data/polygon/day_aggs/{month_prefix}-*.parquet')
),
latest AS (
    SELECT *, 
        ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date DESC) as rn
    FROM vol_stats
    WHERE avg_vol_10d > 0
)
SELECT 
    ticker as symbol, 
    date, 
    volume,
    ROUND(avg_vol_10d, 0) as avg_volume,
    ROUND(volume / avg_vol_10d, 2) as rel_volume
FROM latest
WHERE rn = 1 AND volume / avg_vol_10d >= 3
ORDER BY rel_volume DESC
LIMIT 20
'''
result = historical_query(sql)
save_output(result, 'volume_spikes')

═══════════════════════════════════════════════════════════════════════════════
                               DUCKDB SQL TIPS
═══════════════════════════════════════════════════════════════════════════════
- Timestamps are NANOSECONDS: to_timestamp(timestamp / 1000000000) or /1e9
- GLOB for multiple files: read_parquet('/path/{month_prefix}-*.parquet')
- Extract date: DATE_TRUNC('day', to_timestamp(ts/1e9))::DATE
- Extract hour: EXTRACT(HOUR FROM to_timestamp(ts/1e9))
- First/Last in group: FIRST(col ORDER BY ts), LAST(col ORDER BY ts)
- Rank within partition: ROW_NUMBER() OVER (PARTITION BY x ORDER BY y DESC)
- Safe division: NULLIF(denominator, 0)
- String matching: ticker LIKE 'A%' or ticker IN ('AAPL', 'MSFT')

TIMEOUT: 30 seconds. Always use SQL for multi-symbol queries.
═══════════════════════════════════════════════════════════════════════════════
"""


def get_self_correction_prompt(query: str, last_code: str, last_error: str) -> str:
    """Build prompt for self-correction after an error.
    
    This is used when the LLM-generated code fails execution.
    Provides context about what went wrong and guidance for fixing.
    
    Args:
        query: Original user query
        last_code: The Python code that failed
        last_error: Error message from execution
        
    Returns:
        Correction prompt for the LLM
    """
    current_date = get_current_date()
    prev_date = get_previous_trading_day(current_date)
    month_prefix = datetime.now(ET).strftime("%Y-%m")
    
    return f"""Your previous code had an error. Analyze and fix it.

═══════════════════════════════════════════════════════════════════════════════
                              ERROR CONTEXT
═══════════════════════════════════════════════════════════════════════════════

ORIGINAL QUERY: {query}

CURRENT DATE: {current_date}
PREVIOUS TRADING DAY: {prev_date}

FAILED CODE:
```python
{last_code}
```

ERROR MESSAGE:
{last_error}

═══════════════════════════════════════════════════════════════════════════════
                           COMMON FIXES
═══════════════════════════════════════════════════════════════════════════════

FILE NOT FOUND:
  - Check date format: {current_date} not 2023-XX-XX
  - Use GLOB for ranges: read_parquet('/data/polygon/day_aggs/{month_prefix}-*.parquet')
  - Today's minute data: /data/polygon/minute_aggs/today.parquet
  - Try .csv.gz if .parquet doesn't exist

COLUMN NOT FOUND:
  - day_aggs uses 'timestamp', minute_aggs uses 'window_start'
  - Check spelling: 'vwap' not 'VWAP'
  - List available: SELECT * FROM read_parquet('...') LIMIT 1

DIVISION BY ZERO:
  - Add WHERE clause: WHERE prev_close > 0
  - Use NULLIF: col / NULLIF(denominator, 0)

EMPTY RESULT:
  - Widen filters: lower min_volume, remove price filters
  - Check date range: ensure files exist
  - Verify JOIN conditions

TYPE ERROR:
  - Timestamps are BIGINT nanoseconds, divide by 1e9
  - Use ROUND() for cleaner output
  - Cast if needed: ::DATE, ::VARCHAR

═══════════════════════════════════════════════════════════════════════════════
                           INSTRUCTIONS
═══════════════════════════════════════════════════════════════════════════════

1. Identify the specific error from the message
2. Apply the appropriate fix from above
3. Generate corrected Python code
4. ALWAYS call save_output(result, 'name') at the end
5. Test edge cases (empty data, zero values)

Generate the corrected code now."""
