"""
MCP Server: Earnings
Benzinga earnings calendar with EPS/revenue estimates, actuals, and surprises.
"""
from fastmcp import FastMCP
from clients.http_client import service_get
from config import config
from typing import Optional

mcp = FastMCP(
    "TradeUL Earnings",
    instructions="Earnings calendar service with scheduled and reported earnings data. "
    "Includes EPS/revenue estimates vs actuals, surprise percentages, and guidance.",
)


@mcp.tool()
async def get_today_earnings(
    status: Optional[str] = None,
    time_slot: Optional[str] = None,
) -> dict:
    """Get today's earnings calendar.

    Args:
        status: 'scheduled' (pending) or 'reported' (with results)
        time_slot: 'BMO' (before market open) or 'AMC' (after market close)

    Returns per company: symbol, company_name, time_slot, eps_estimate,
    eps_actual, revenue_estimate, revenue_actual, surprise_pct, guidance.
    """
    params = {}
    if status:
        params["status"] = status
    if time_slot:
        params["time_slot"] = time_slot
    try:
        return await service_get(config.api_gateway_url, "/api/earnings/today", params=params)
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def get_upcoming_earnings(days: int = 7) -> dict:
    """Get upcoming earnings for the next N days.
    Useful for planning and anticipating market-moving events."""
    try:
        return await service_get(
            config.api_gateway_url, "/api/earnings/upcoming", params={"days": days}
        )
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def get_earnings_by_ticker(ticker: str) -> dict:
    """Get earnings history for a specific ticker.
    Shows past earnings with beats/misses and surprise percentages."""
    try:
        return await service_get(
            config.api_gateway_url, f"/api/earnings/ticker/{ticker.upper()}"
        )
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def get_earnings_by_date(date: str) -> dict:
    """Get earnings for a specific date (YYYY-MM-DD format).
    Returns all companies reporting on that date."""
    try:
        return await service_get(config.api_gateway_url, f"/api/earnings/date/{date}")
    except Exception as e:
        return {"error": str(e)}
