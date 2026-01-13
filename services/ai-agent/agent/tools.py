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
        "description": """Get real-time market data snapshot. Returns ~1000 most active tickers with current prices, 
        changes, volume, and technical indicators. Use for: current gainers/losers, real-time rankings, 
        sector analysis, volume leaders. Data includes: symbol, price, change_percent, volume_today, 
        market_cap, sector, rvol, vwap, pre/post market data.
        
        IMPORTANT: Set generate_chart=true when user asks for 'grafico', 'chart', 'visualizar', 'plot'.""",
        "parameters": {
            "type": "object",
            "properties": {
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
        "description": """Execute Python code in sandbox for complex analysis.

GLOBAL FUNCTIONS (call directly, no object prefix):
1. historical_query(sql) - FASTEST! Direct SQL on DuckDB. Use for complex queries.
2. get_top_movers(date_str, limit=20, min_volume=100000, direction='up'/'down')
3. get_minute_bars(date_str, symbol=None) - Only for single symbol analysis  
4. save_output(dataframe, 'name') - Required to return results

WRONG: default_api.historical_query(sql)
CORRECT: historical_query(sql)

DATA FILES (use in SQL):
- read_csv_auto('/data/polygon/minute_aggs/YYYY-MM-DD.csv.gz')
- Columns: ticker, window_start, open, high, low, close, volume
- window_start is nanoseconds, divide by 1000000000 for timestamp

EXAMPLE 1 - Relative Strength vs SPY (FAST - single SQL query):
sql = '''
WITH spy AS (
    SELECT (LAST(close ORDER BY window_start) / FIRST(open ORDER BY window_start) - 1) * 100 as spy_change
    FROM read_csv_auto('/data/polygon/minute_aggs/2026-01-09.csv.gz')
    WHERE ticker = 'SPY'
),
stocks AS (
    SELECT ticker as symbol,
           ROUND((LAST(close ORDER BY window_start) / FIRST(open ORDER BY window_start) - 1) * 100, 2) as change_pct,
           SUM(volume) as volume
    FROM read_csv_auto('/data/polygon/minute_aggs/2026-01-09.csv.gz')
    GROUP BY ticker
    HAVING SUM(volume) > 1000000
)
SELECT s.*, spy.spy_change, s.change_pct - spy.spy_change as relative_strength
FROM stocks s, spy
WHERE s.change_pct > spy.spy_change
ORDER BY relative_strength DESC LIMIT 20
'''
result = historical_query(sql)
save_output(result, 'relative_strength')

EXAMPLE 2 - Stocks with volume > 1M, price > $10 that went UP when SPY went DOWN:
sql = '''
WITH spy_down AS (
    SELECT window_start FROM read_csv_auto('/data/polygon/minute_aggs/2026-01-09.csv.gz')
    WHERE ticker = 'SPY' AND close < open
),
stock_strength AS (
    SELECT ticker, COUNT(*) as up_minutes, ROUND(AVG((close-open)/open*100),3) as avg_gain
    FROM read_csv_auto('/data/polygon/minute_aggs/2026-01-09.csv.gz')
    WHERE window_start IN (SELECT window_start FROM spy_down) AND close > open
    GROUP BY ticker HAVING COUNT(*) > 20
),
stock_stats AS (
    SELECT ticker, SUM(volume) as volume, FIRST(open ORDER BY window_start) as open_price
    FROM read_csv_auto('/data/polygon/minute_aggs/2026-01-09.csv.gz')
    GROUP BY ticker
)
SELECT ss.ticker as symbol, ss.up_minutes, ss.avg_gain, st.volume, st.open_price
FROM stock_strength ss
JOIN stock_stats st ON ss.ticker = st.ticker
WHERE st.volume > 1000000 AND st.open_price > 10
ORDER BY ss.up_minutes DESC LIMIT 15
'''
result = historical_query(sql)
save_output(result, 'pullback_strength')

EXAMPLE 3 - Extract time ranges/hours (IMPORTANT: window_start is nanoseconds!):
sql = '''
SELECT ticker,
    EXTRACT(HOUR FROM to_timestamp(window_start / 1000000000) AT TIME ZONE 'America/New_York') as hour_et,
    COUNT(*) as candles,
    ROUND(AVG((close-open)/open*100), 3) as avg_gain_pct
FROM read_csv_auto('/data/polygon/minute_aggs/2026-01-09.csv.gz')
WHERE close > open
GROUP BY ticker, hour_et
ORDER BY avg_gain_pct DESC LIMIT 20
'''
result = historical_query(sql)
save_output(result, 'hourly_strength')

IMPORTANT FOR TIME EXTRACTION:
- WRONG: strftime('%H', window_start/1000000000, 'unixepoch') -- SQLite syntax, NOT DuckDB!
- RIGHT: EXTRACT(HOUR FROM to_timestamp(window_start / 1000000000) AT TIME ZONE 'America/New_York')

WRONG (SLOW - don't do this):
for symbol in symbols:  # Multiple queries = TIMEOUT
    df = get_minute_bars(date, symbol=symbol)

CORRECT (FAST - single query):
sql = "SELECT ... FROM read_csv_auto(...) WHERE ticker IN ('A','B','C')"
result = historical_query(sql)

TIMEOUT: 30 seconds. Use SQL for anything involving multiple symbols.""",
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
        if date_str == "today":
            snapshot = await _get_market_snapshot({"limit": 1000}, ctx)
            if not snapshot["success"]:
                return snapshot
            df = snapshot["data"]
        else:
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
    
    result = {
        "success": True,
        "sectors": performance,
        "tickers": classified,
        "sector_count": classified["synthetic_sector"].nunique()
    }
    
    if chart_data:
        result["chart"] = chart_data
    
    return result


async def _quick_news(args: Dict, ctx: Dict) -> Dict:
    """Fast news lookup from Benzinga (<1 second)."""
    from research.grok_research import fetch_benzinga_news
    
    symbol = args.get("symbol", "").upper()
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
    
    symbol = args.get("symbol", "").upper()
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

        response = client.models.generate_content(
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
    symbol = args.get("symbol", "").upper()
    
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
