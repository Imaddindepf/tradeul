"""
MCP Server: Prediction Markets
Polymarket prediction markets aggregation for macro and event analysis.

Actual service: prediction-markets:8021
Routes: /api/v1/predictions/events, /api/v1/predictions/event/{id}
"""
from fastmcp import FastMCP
from clients.http_client import service_get
from config import config
from typing import Optional

mcp = FastMCP(
    "Tradeul Prediction Markets",
    instructions="Polymarket prediction markets data. Provides event probabilities, "
    "price history, and market sentiment for elections, economic events, "
    "Fed decisions, crypto events, and more.",
)


@mcp.tool()
async def get_prediction_events(
    category: Optional[str] = None,
    active: bool = True,
    limit: int = 50,
) -> dict:
    """Get prediction market events from Polymarket.

    Args:
        category: Filter by category (politics, crypto, economics, sports, science, culture)
        active: Only show active (open) markets
        limit: Max results

    Returns: event title, description, markets with current probabilities,
    volume, and liquidity.
    """
    params = {"active": active, "limit": limit}
    if category:
        params["category"] = category
    try:
        return await service_get(
            config.prediction_markets_url, "/api/v1/predictions/events", params=params
        )
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def get_prediction_price_history(
    event_id: str,
    interval: str = "max",
) -> dict:
    """Get price history for a specific prediction market event.
    Shows how probabilities have changed over time."""
    try:
        return await service_get(
            config.prediction_markets_url,
            f"/api/v1/predictions/event/{event_id}/detail",
            params={"interval": interval},
        )
    except Exception as e:
        return {"error": str(e)}
