"""
MCP Server: Earnings
Benzinga earnings calendar with EPS/revenue estimates, actuals, and surprises.

Actual service: benzinga-earnings:8022
Routes: /api/v1/earnings/today, /api/v1/earnings/upcoming,
        /api/v1/earnings/ticker/{ticker}, /api/v1/earnings/date/{date}
"""
from fastmcp import FastMCP
from clients.http_client import service_get
from config import config
from typing import Optional

mcp = FastMCP(
    "Tradeul Earnings",
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
        return await service_get(
            config.benzinga_earnings_url, "/api/v1/earnings/today", params=params
        )
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def get_upcoming_earnings(
    days: int = 7,
    min_importance: Optional[int] = None,
    limit: int = 200,
) -> dict:
    """Get upcoming earnings for the next N days.

    Args:
        days: Number of days ahead (1-30, default 7)
        min_importance: Minimum importance level 0-5 (higher = bigger company).
                        Use 3+ to filter to mid/large-cap names only.
        limit: Max results to return (default 200)

    Useful for planning and anticipating market-moving events.
    """
    params: dict = {"days": days, "limit": limit}
    if min_importance is not None:
        params["min_importance"] = min_importance
    try:
        return await service_get(
            config.benzinga_earnings_url,
            "/api/v1/earnings/upcoming",
            params=params,
        )
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def get_earnings_by_ticker(ticker: str) -> dict:
    """Get earnings history for a specific ticker.
    Shows past earnings with beats/misses and surprise percentages."""
    try:
        return await service_get(
            config.benzinga_earnings_url,
            f"/api/v1/earnings/ticker/{ticker.upper()}",
        )
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def get_earnings_by_date(date: str) -> dict:
    """Get earnings for a specific date (YYYY-MM-DD format).
    Returns all companies reporting on that date."""
    try:
        return await service_get(
            config.benzinga_earnings_url, f"/api/v1/earnings/date/{date}"
        )
    except Exception as e:
        return {"error": str(e)}
