"""
MCP Server: Pattern Matching
FAISS-based pattern similarity search for technical chart patterns.
"""
from fastmcp import FastMCP
from clients.http_client import service_get
from config import config

mcp = FastMCP(
    "Tradeul Pattern Matching",
    instructions="FAISS-powered pattern similarity search. Finds historical chart patterns "
    "similar to current price action. Use for technical analysis and pattern recognition.",
)


@mcp.tool()
async def find_similar_patterns(
    symbol: str,
    top_k: int = 50,
    cross_asset: bool = True,
) -> dict:
    """FAISS pattern-similarity forecast for a ticker's recent intraday action.

    Matches the ticker's last ~45 minutes of price action against millions of
    historical windows and returns a statistical forecast of the next 15 min.

    Args:
        symbol: Ticker to analyze
        top_k: Number of nearest historical neighbors to use (1-200, default 50)
        cross_asset: Match against ALL tickers' history, not just this symbol

    Returns: forecast with mean_return, prob_up/prob_down, best/worst case,
    confidence, mean/std trajectories, and the matched historical neighbors.
    """
    try:
        return await service_get(
            config.pattern_matching_url,
            f"/api/search/{symbol.upper()}",
            params={
                "k": max(1, min(int(top_k), 200)),
                "cross_asset": cross_asset,
            },
        )
    except Exception as e:
        return {"error": str(e)}
