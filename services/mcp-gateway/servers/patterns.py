"""
MCP Server: Pattern Matching
FAISS-based pattern similarity search for technical chart patterns.
"""
from fastmcp import FastMCP
from clients.http_client import service_get
from config import config

mcp = FastMCP(
    "TradeUL Pattern Matching",
    instructions="FAISS-powered pattern similarity search. Finds historical chart patterns "
    "similar to current price action. Use for technical analysis and pattern recognition.",
)


@mcp.tool()
async def find_similar_patterns(
    symbol: str,
    lookback_days: int = 20,
    top_k: int = 10,
) -> dict:
    """Find historical chart patterns similar to a ticker's recent price action.

    Args:
        symbol: Ticker to analyze
        lookback_days: Number of recent days to use as the pattern (default 20)
        top_k: Number of similar patterns to return (default 10)

    Returns: list of similar patterns with: matched_ticker, matched_date,
    similarity_score, subsequent_return (what happened after the pattern).
    """
    try:
        return await service_get(
            config.pattern_matching_url,
            "/api/v1/patterns/similar",
            params={
                "symbol": symbol.upper(),
                "lookback_days": lookback_days,
                "top_k": top_k,
            },
        )
    except Exception as e:
        return {"error": str(e)}
