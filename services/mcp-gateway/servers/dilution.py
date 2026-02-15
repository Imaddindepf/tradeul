"""
MCP Server: Dilution Tracker
SEC filing analysis for stock dilution, warrants, ATM offerings, and cash runway.
"""
from fastmcp import FastMCP
from clients.http_client import service_get
from config import config

mcp = FastMCP(
    "TradeUL Dilution Tracker",
    instructions="Stock dilution analysis service that tracks SEC filings for dilution risk. "
    "Analyzes warrants, ATM offerings, shelf registrations, cash runway, and risk scores. "
    "Critical for small-cap and micro-cap stock analysis.",
)


@mcp.tool()
async def get_dilution_profile(ticker: str) -> dict:
    """Get comprehensive dilution profile for a ticker.
    Returns: shares_outstanding history, dilution events, risk score,
    cash runway estimate, warrant count, ATM offering status."""
    try:
        return await service_get(
            config.dilution_tracker_url,
            f"/api/v1/dilution/{ticker.upper()}/profile",
        )
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def get_warrants(ticker: str) -> dict:
    """Get all outstanding warrants for a ticker.
    Returns: exercise price, expiration date, shares underlying, type, status."""
    try:
        return await service_get(
            config.dilution_tracker_url,
            f"/api/v1/dilution/{ticker.upper()}/warrants",
        )
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def get_atm_offerings(ticker: str) -> dict:
    """Get at-the-market (ATM) offering details for a ticker.
    ATM offerings allow companies to sell shares gradually at market price."""
    try:
        return await service_get(
            config.dilution_tracker_url,
            f"/api/v1/dilution/{ticker.upper()}/atm-offerings",
        )
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def get_shelf_registrations(ticker: str) -> dict:
    """Get shelf registration (S-3) details for a ticker.
    Shelf registrations allow companies to issue securities over time."""
    try:
        return await service_get(
            config.dilution_tracker_url,
            f"/api/v1/dilution/{ticker.upper()}/shelf-registrations",
        )
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def get_cash_runway(ticker: str) -> dict:
    """Get enhanced cash runway analysis for a ticker.
    Estimates how many months of cash the company has remaining
    based on burn rate, cash position, and available financing."""
    try:
        return await service_get(
            config.dilution_tracker_url,
            f"/api/v1/dilution/{ticker.upper()}/cash-runway-enhanced",
        )
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def get_dilution_risk_ratings(ticker: str) -> dict:
    """Get dilution risk ratings and scores.
    Returns overall risk score (1-10), individual risk factors,
    and risk category (LOW, MEDIUM, HIGH, CRITICAL)."""
    try:
        return await service_get(
            config.dilution_tracker_url,
            f"/api/v1/dilution/{ticker.upper()}/risk-ratings",
        )
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def get_shares_history(ticker: str) -> dict:
    """Get shares outstanding history over time.
    Shows how shares have changed (increased = dilution, decreased = buybacks)."""
    try:
        return await service_get(
            config.dilution_tracker_url,
            f"/api/v1/dilution/{ticker.upper()}/shares-history",
        )
    except Exception as e:
        return {"error": str(e)}
