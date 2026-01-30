"""
Market Tools V2 - Clean Tool Definitions (2025)
================================================

Key changes from V1:
- NO hardcoded SQL examples in execute_analysis
- Schema is injected via system prompt, not tool description
- Simpler, cleaner tool definitions

The LLM knows financial concepts. We just tell it where the data is.
"""

from typing import Dict, Any, List, Optional
import asyncio
import structlog

logger = structlog.get_logger(__name__)


# Clean tool definitions - NO SQL EXAMPLES
MARKET_TOOLS = [
    {
        "name": "get_market_snapshot",
        "description": """Get real-time market data from scanner.

USE FOR:
- Check if specific ticker(s) are in scanner: symbols=["AAOI", "TSLA"]
- Current gainers/losers: filter_type="gainers"/"losers"
- Volume leaders: filter_type="volume"

Returns: symbol, price, change_percent, volume, market_cap, sector, rvol, vwap.

Parameters:
- symbols: List of tickers to check if in scanner (e.g., ["AAOI"])
- filter_type: "all", "gainers", "losers", "volume", "premarket", "postmarket"
- limit: Max results (default 50)
- min_volume, min_price, min_market_cap: Optional filters
- generate_chart: Set true for visualization""",
        "parameters": {
            "type": "object",
            "properties": {
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Check if specific ticker(s) are in scanner"
                },
                "filter_type": {
                    "type": "string",
                    "enum": ["all", "gainers", "losers", "volume", "premarket", "postmarket"]
                },
                "limit": {"type": "integer"},
                "min_volume": {"type": "integer"},
                "min_price": {"type": "number"},
                "min_market_cap": {"type": "number"},
                "generate_chart": {"type": "boolean"}
            }
        }
    },
    {
        "name": "get_top_movers",
        "description": """Get pre-aggregated top movers for a date.
Faster than execute_analysis for simple top N queries.
Returns: symbol, change_percent, volume, open, close.

Parameters:
- date_str: 'today', 'yesterday', or 'YYYY-MM-DD'
- limit: Max results
- direction: 'up' for gainers, 'down' for losers""",
        "parameters": {
            "type": "object",
            "properties": {
                "date_str": {"type": "string"},
                "limit": {"type": "integer"},
                "direction": {"type": "string", "enum": ["up", "down"]}
            }
        }
    },
    {
        "name": "execute_analysis",
        "description": """Execute Python/DuckDB code for custom market analysis.

USE THIS FOR: Complex queries, multi-day analysis, statistics, custom calculations.

The data schema is in your system prompt. Write SQL based on that schema.
You know financial concepts (gaps, VWAP, momentum) - just query the data.

Code requirements:
1. Use historical_query(sql) to run DuckDB queries
2. MUST call save_output(result, 'name') to return data
3. Use current dates (2026-01-XX), not old dates

Example structure:
```python
sql = '''SELECT ... FROM read_parquet('/data/polygon/day_aggs/2026-01-*.parquet') ...'''
result = historical_query(sql)
save_output(result, 'analysis_name')
```""",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code with DuckDB SQL"
                }
            },
            "required": ["code"]
        }
    },
    {
        "name": "research_ticker",
        "description": """Deep research on a ticker.
Searches news, X.com, web for information.
USE FOR: "Why is X up/down?", news, sentiment, analysis.

Parameters:
- ticker: Stock symbol
- query: What to research (optional)""",
        "parameters": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "query": {"type": "string"}
            },
            "required": ["ticker"]
        }
    },
    {
        "name": "quick_news",
        "description": """Get recent news for a ticker.
Faster than research_ticker for simple news lookups.

Parameters:
- ticker: Stock symbol
- limit: Max news items""",
        "parameters": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "limit": {"type": "integer"}
            },
            "required": ["ticker"]
        }
    },
    {
        "name": "get_ticker_info",
        "description": """Basic ticker information lookup.
Returns: name, price, market_cap, sector, industry.

Parameters:
- ticker: Stock symbol""",
        "parameters": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"}
            },
            "required": ["ticker"]
        }
    },
    {
        "name": "classify_synthetic_sectors",
        "description": """Create thematic ETF portfolios (synthetic ETFs).
Themes: Nuclear, AI, EV, Cannabis, Space, Biotech, Quantum, Robotics, China Tech, etc.

Parameters:
- date: 'today' or 'YYYY-MM-DD'
- themes: List of themes (optional, default all)
- min_tickers_per_sector: Minimum stocks per ETF/theme (e.g., 5)
- min_market_cap: Minimum market cap filter (e.g., 1000000000 for $1B)
- min_volume: Minimum volume filter
- min_price: Minimum price filter
- max_price: Maximum price filter
- generate_chart: Create visualization""",
        "parameters": {
            "type": "object",
            "properties": {
                "date": {"type": "string"},
                "themes": {"type": "array", "items": {"type": "string"}},
                "min_tickers_per_sector": {"type": "integer"},
                "min_market_cap": {"type": "number", "description": "Minimum market cap (e.g., 1000000000 for $1B)"},
                "min_volume": {"type": "integer"},
                "min_price": {"type": "number"},
                "max_price": {"type": "number"},
                "generate_chart": {"type": "boolean"}
            }
        }
    },
    {
        "name": "get_earnings_calendar",
        "description": """Get earnings calendar.
Shows which companies report earnings.

Parameters:
- date: 'today' or 'YYYY-MM-DD'
- days_ahead: How many days to look ahead""",
        "parameters": {
            "type": "object",
            "properties": {
                "date": {"type": "string"},
                "days_ahead": {"type": "integer"}
            }
        }
    },
]


async def execute_tool_v2(tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a tool by name with given arguments.
    
    This is a dispatcher that routes to actual implementations.
    """
    # Import implementations
    from .tools import execute_tool as execute_tool_v1
    
    # For now, delegate to V1 implementations
    # In production, would have cleaner implementations here
    return await execute_tool_v1(tool_name, args)


def get_tool_names() -> List[str]:
    """Get list of available tool names."""
    return [t["name"] for t in MARKET_TOOLS]


def get_tool_by_name(name: str) -> Optional[Dict]:
    """Get tool definition by name."""
    for tool in MARKET_TOOLS:
        if tool["name"] == name:
            return tool
    return None
