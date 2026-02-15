"""
TradeUL MCP Gateway
Composite MCP server that exposes all 27 microservices as standardized tools.

Architecture:
- 12 domain-specific MCP servers composed into a single gateway
- ~50 tools covering scanner, events, news, earnings, SEC, financials,
  dilution, screener, historical, analytics, patterns, and prediction markets
- Shared Redis + HTTP clients for efficient resource usage
- Streamable HTTP transport for network access from LangGraph agents

Usage:
  python main.py                          # Start HTTP server on port 8050
  fastmcp dev main.py                     # Interactive development mode
  fastmcp install main.py --name tradeul  # Install as MCP server
"""
import asyncio
import signal
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastmcp import FastMCP
from config import config

# ──────────────────────────────────────────────────────────────────────
# Root MCP Server
# ──────────────────────────────────────────────────────────────────────
gateway = FastMCP(
    "TradeUL Gateway",
    instructions=(
        "TradeUL is a real-time stock trading platform processing 11,000+ tickers. "
        "This gateway provides access to all platform services through standardized tools.\n\n"
        "AVAILABLE DOMAINS:\n"
        "- Scanner: Real-time rankings (gappers, momentum, volume, halts)\n"
        "- Events: 27+ market event types (breakouts, VWAP crosses, volume spikes)\n"
        "- News: Benzinga real-time news and catalyst alerts\n"
        "- Earnings: Calendar with EPS/revenue estimates and actuals\n"
        "- SEC Filings: Real-time EDGAR filings (8-K, 10-K, S-1, etc.)\n"
        "- Financials: XBRL financial statements, ratios, segments\n"
        "- Dilution: Warrant tracking, ATM offerings, cash runway, risk scores\n"
        "- Screener: DuckDB-powered screening with 60+ indicators\n"
        "- Historical: 1760+ days of OHLCV data (minute + daily)\n"
        "- Analytics: RVOL, VWAP, technical indicators, volume/price windows\n"
        "- Patterns: FAISS similarity search for chart patterns\n"
        "- Predictions: Polymarket prediction markets\n\n"
        "TIPS:\n"
        "- For real-time data, use Scanner or Analytics tools\n"
        "- For historical analysis, use Historical tools with DuckDB\n"
        "- For fundamental analysis, combine Financials + Dilution + SEC tools\n"
        "- For news-driven analysis, combine News + Events + Earnings tools"
    ),
)

# ──────────────────────────────────────────────────────────────────────
# Import and mount all domain servers
# ──────────────────────────────────────────────────────────────────────
from servers.scanner import mcp as scanner_mcp
from servers.events import mcp as events_mcp
from servers.news import mcp as news_mcp
from servers.earnings import mcp as earnings_mcp
from servers.sec_filings import mcp as sec_mcp
from servers.financials import mcp as financials_mcp
from servers.dilution import mcp as dilution_mcp
from servers.screener import mcp as screener_mcp
from servers.historical import mcp as historical_mcp
from servers.analytics import mcp as analytics_mcp
from servers.patterns import mcp as patterns_mcp
from servers.predictions import mcp as predictions_mcp

# Mount each domain server with a prefix for namespacing
gateway.mount("scanner", scanner_mcp)
gateway.mount("events", events_mcp)
gateway.mount("news", news_mcp)
gateway.mount("earnings", earnings_mcp)
gateway.mount("sec", sec_mcp)
gateway.mount("financials", financials_mcp)
gateway.mount("dilution", dilution_mcp)
gateway.mount("screener", screener_mcp)
gateway.mount("historical", historical_mcp)
gateway.mount("analytics", analytics_mcp)
gateway.mount("patterns", patterns_mcp)
gateway.mount("predictions", predictions_mcp)


# ──────────────────────────────────────────────────────────────────────
# Gateway-level tools (cross-domain)
# ──────────────────────────────────────────────────────────────────────
@gateway.tool()
async def get_platform_status() -> dict:
    """Get the overall platform status including market session,
    number of active tickers, and service health."""
    from clients.redis_client import redis_get_json, get_redis

    session = await redis_get_json("market:session:status")

    r = await get_redis()
    enriched_count = await r.hlen("snapshot:enriched:latest")

    return {
        "market_session": session or {"session": "UNKNOWN"},
        "active_tickers": enriched_count,
        "mcp_version": "1.0.0",
        "domains": [
            "scanner", "events", "news", "earnings", "sec_filings",
            "financials", "dilution", "screener", "historical",
            "analytics", "patterns", "predictions",
        ],
    }


@gateway.tool()
async def get_full_ticker_analysis(symbol: str) -> dict:
    """Get a comprehensive analysis of a single ticker combining data from
    multiple domains: enriched snapshot, recent events, news, and earnings.

    This is a convenience tool that aggregates data from 4 sources in parallel.
    For deeper analysis of any single domain, use the domain-specific tools.
    """
    import asyncio
    from clients.redis_client import get_redis
    from clients.http_client import service_get
    import orjson

    r = await get_redis()
    sym = symbol.upper()

    # Parallel data fetching
    enriched_task = r.hget("snapshot:enriched:latest", sym)
    news_task = r.zrevrange(f"cache:benzinga:news:ticker:{sym}", 0, 4)

    enriched_raw, news_raw = await asyncio.gather(
        enriched_task, news_task, return_exceptions=True
    )

    result = {"symbol": sym}

    # Enriched data
    if isinstance(enriched_raw, str):
        result["market_data"] = orjson.loads(enriched_raw)
    else:
        result["market_data"] = None

    # News
    if isinstance(news_raw, list):
        articles = []
        for item in news_raw:
            try:
                articles.append(orjson.loads(item))
            except Exception:
                pass
        result["recent_news"] = articles
    else:
        result["recent_news"] = []

    # Events (from stream)
    from clients.redis_client import redis_xrevrange
    events = await redis_xrevrange("stream:events:market", count=200)
    ticker_events = [e for e in events if e.get("symbol") == sym][:10]
    result["recent_events"] = ticker_events

    return result


# ──────────────────────────────────────────────────────────────────────
# Lifecycle management
# ──────────────────────────────────────────────────────────────────────
async def cleanup():
    """Cleanup connections on shutdown."""
    from clients.redis_client import close_redis
    from clients.http_client import close_http_client
    await close_redis()
    await close_http_client()


# ──────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    print(f"Starting TradeUL MCP Gateway on {config.mcp_host}:{config.mcp_port}")
    print(f"Redis: {config.redis_host}:{config.redis_port}")
    print(f"Domains: 12 | Tools: ~50")

    # Run as streamable HTTP server for network access
    gateway.run(
        transport="streamable-http",
        host=config.mcp_host,
        port=config.mcp_port,
    )
