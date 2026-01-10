"""
Market Analysis Tools
=====================
Function declarations for Gemini Function Calling.

Each tool is a capability the LLM can invoke to get data or perform actions.
The LLM decides which tools to use based on the user's query.
"""

import pandas as pd
import httpx
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from pathlib import Path
import pytz
import structlog

logger = structlog.get_logger(__name__)
ET = pytz.timezone('America/New_York')

# =============================================================================
# TOOL DEFINITIONS (Gemini Function Declarations)
# =============================================================================

MARKET_TOOLS = [
    {
        "name": "get_market_snapshot",
        "description": """Get real-time market data snapshot. Returns ~1000 most active tickers with current prices, 
        changes, volume, and technical indicators. Use for: current gainers/losers, real-time rankings, 
        sector analysis, volume leaders. Data includes: symbol, price, change_percent, volume_today, 
        market_cap, sector, rvol, vwap, pre/post market data.""",
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
                "sector": {
                    "type": "string",
                    "description": "Filter by sector name"
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
        "description": """Get pre-aggregated top gainers or losers for a date/time range. Much faster than 
        manual aggregation. Use for: top gainers yesterday, after-hours movers, pre-market leaders.
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
                    "description": "Start hour in ET (e.g., 16 for after-hours)"
                },
                "end_hour": {
                    "type": "integer",
                    "description": "End hour in ET"
                },
                "direction": {
                    "type": "string",
                    "enum": ["up", "down"],
                    "description": "Gainers (up) or losers (down)"
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
        "name": "classify_synthetic_sectors",
        "description": """Classify tickers into THEMATIC sectors (synthetic ETFs). Creates dynamic groupings 
        like: Nuclear, AI & Semiconductors, Electric Vehicles, Biotech, Crypto, Cannabis, Space, etc.
        Use when user asks about: 'sectores sintéticos', 'synthetic ETFs', 'thematic sectors', 
        'sector nuclear', 'sector AI'. Returns sector performance rankings.""",
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
                }
            },
            "required": ["date"]
        }
    },
    {
        "name": "research_ticker",
        "description": """Deep research on a specific ticker using news, social media (X.com), and web search.
        Use when user asks: WHY is X moving?, news about X, what happened to X, sentiment on X.
        Returns: summary, citations, key events, sentiment analysis.""",
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
        "description": """Execute Python code in sandbox. ONLY use for complex analysis other tools can't do.

SANDBOX FUNCTIONS (all return pandas DataFrame, check with df.empty):
- get_minute_bars(date_str, symbol=None, start_hour=None, end_hour=None)
  Example: get_minute_bars('yesterday', symbol='AAPL')
  Returns: DataFrame[symbol,datetime,open,high,low,close,volume]

- get_top_movers(date_str, start_hour=None, end_hour=None, min_volume=100000, limit=20, ascending=False)
  Example: get_top_movers('yesterday', limit=5)
  Returns: DataFrame[symbol,open_price,close_price,change_pct,volume]

- available_dates() -> list of date strings ['2026-01-07', 'today']
- historical_query(sql) -> DataFrame from raw SQL
- save_output(data, 'name') -> save DataFrame for display (positional args!)

EXAMPLE CODE:
  movers = get_top_movers('yesterday', limit=5)
  if not movers.empty:
      for sym in movers['symbol']:
          bars = get_minute_bars('yesterday', symbol=sym)
          if not bars.empty: ...

DO NOT use: default_api, api, requests. Only functions above work.""",
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
        elif tool_name == "classify_synthetic_sectors":
            return await _classify_synthetic_sectors(args, context)
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
            sector = args.get("sector")
            
            if min_volume and "volume_today" in df.columns:
                df = df[df["volume_today"] >= min_volume]
            if min_price and "price" in df.columns:
                df = df[df["price"] >= min_price]
            if sector and "sector" in df.columns:
                df = df[df["sector"].str.contains(sector, case=False, na=False)]
            
            # Sort by filter type
            if filter_type == "gainers" and "change_percent" in df.columns:
                df = df.nlargest(limit, "change_percent")
            elif filter_type == "losers" and "change_percent" in df.columns:
                df = df.nsmallest(limit, "change_percent")
            elif filter_type == "volume" and "volume_today" in df.columns:
                df = df.nlargest(limit, "volume_today")
            elif filter_type in ["premarket", "postmarket"]:
                col = f"{filter_type}_change_percent"
                if col in df.columns:
                    df = df.dropna(subset=[col]).nlargest(limit, col)
            else:
                df = df.head(limit)
            
            return {
                "success": True,
                "data": df,
                "count": len(df),
                "source": "scanner"
            }
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
    
    if not Path(file_path).exists():
        return {"success": False, "error": f"No data for {date_str}"}
    
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
    """Get pre-aggregated top movers using DuckDB layer."""
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
        return hist_result
    
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


async def _classify_synthetic_sectors(args: Dict, ctx: Dict) -> Dict:
    """Classify tickers into thematic sectors."""
    from research.synthetic_sectors import (
        classify_tickers_into_synthetic_sectors,
        calculate_synthetic_sector_performance
    )
    
    date_str = args.get("date", "today")
    max_sectors = args.get("max_sectors", 15)
    
    llm_client = ctx.get("llm_client")
    if not llm_client:
        return {"success": False, "error": "LLM client required"}
    
    # Get data based on date
    if date_str == "today":
        snapshot = await _get_market_snapshot({"limit": 1000}, ctx)
        if not snapshot["success"]:
            return snapshot
        df = snapshot["data"]
    else:
        # For historical: get top 500 movers (250 gainers + 250 losers)
        # This gives better coverage than just 100
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
    
    # Classify
    classified = await classify_tickers_into_synthetic_sectors(
        df, llm_client, max_sectors=max_sectors
    )
    
    if classified.empty:
        return {"success": False, "error": "Classification failed"}
    
    performance = calculate_synthetic_sector_performance(classified)
    
    return {
        "success": True,
        "sectors": performance,
        "tickers": classified,
        "sector_count": classified["synthetic_sector"].nunique()
    }


async def _research_ticker(args: Dict, ctx: Dict) -> Dict:
    """Research a ticker using Grok."""
    from research.grok_research import research_ticker
    
    symbol = args.get("symbol", "").upper()
    include_technicals = args.get("include_technicals", True)
    
    if not symbol:
        return {"success": False, "error": "Symbol required"}
    
    result = await research_ticker(
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
    """Execute custom analysis in sandbox."""
    from sandbox.manager import SandboxManager
    
    code = args.get("code", "")
    description = args.get("description", "Custom analysis")
    
    if not code:
        return {"success": False, "error": "Code required"}
    
    sandbox = ctx.get("sandbox") or SandboxManager()
    
    # Inject available data
    data = {}
    if "scanner_data" in ctx:
        data["scanner_data"] = ctx["scanner_data"]
    if "historical_bars" in ctx:
        data["historical_bars"] = ctx["historical_bars"]
    
    result = await sandbox.execute(code, data=data)
    
    return {
        "success": result.success,
        "stdout": result.stdout,
        "outputs": result.output_files,
        "error": result.error_message if not result.success else None
    }


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
