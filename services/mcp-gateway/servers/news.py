"""
MCP Server: Benzinga News
Real-time news streaming and catalyst alerts from Benzinga.
"""
from fastmcp import FastMCP
from clients.redis_client import redis_zrevrange_parsed
from clients.http_client import service_get
from config import config
from typing import Optional

mcp = FastMCP(
    "TradeUL News",
    instructions="Benzinga news feed with real-time articles and catalyst alerts. "
    "Use for breaking news, ticker-specific news, and understanding why stocks are moving.",
)


@mcp.tool()
async def get_latest_news(count: int = 50) -> dict:
    """Get the latest news articles from Benzinga.
    Returns: title, summary, tickers mentioned, published timestamp, URL, author.
    Sorted by most recent first."""
    articles = await redis_zrevrange_parsed("cache:benzinga:news:latest", 0, count - 1)
    return {"articles": articles, "count": len(articles)}


@mcp.tool()
async def get_news_by_ticker(symbol: str, count: int = 20) -> dict:
    """Get recent news for a specific ticker.
    Returns articles that mention this ticker, sorted by most recent."""
    articles = await redis_zrevrange_parsed(
        f"cache:benzinga:news:ticker:{symbol.upper()}", 0, count - 1
    )
    return {"symbol": symbol, "articles": articles, "count": len(articles)}


@mcp.tool()
async def get_catalyst_alerts(count: int = 20) -> dict:
    """Get recent catalyst alerts - significant news events that could move stock prices.
    Catalysts include: FDA approvals, earnings surprises, M&A, analyst upgrades/downgrades,
    contract wins, guidance changes, and more."""
    try:
        return await service_get(
            config.benzinga_news_url,
            "/api/v1/catalysts/recent",
            params={"limit": count},
        )
    except Exception:
        # Fallback: filter latest news for catalyst-like articles
        articles = await redis_zrevrange_parsed("cache:benzinga:news:latest", 0, count * 3)
        return {"articles": articles[:count], "count": min(len(articles), count)}
