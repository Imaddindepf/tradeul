"""
Earnings Routes

Proxy routes to the benzinga-earnings service for earnings calendar data.
"""

import os
from typing import Optional
from fastapi import APIRouter, Query, HTTPException
import httpx
import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/earnings", tags=["earnings"])

# Service URL
EARNINGS_SERVICE_URL = os.getenv("BENZINGA_EARNINGS_URL", "http://benzinga-earnings:8022")

# HTTP client
_client: Optional[httpx.AsyncClient] = None


async def get_client() -> httpx.AsyncClient:
    """Get or create HTTP client."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            base_url=EARNINGS_SERVICE_URL,
            timeout=30.0
        )
    return _client


@router.get("/today")
async def get_today_earnings():
    """
    Get today's earnings announcements.
    
    Returns earnings scheduled for today with stats (BMO, AMC, reported).
    """
    try:
        client = await get_client()
        response = await client.get("/api/v1/earnings/today")
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as e:
        logger.error("earnings_today_error", error=str(e))
        raise HTTPException(status_code=502, detail=f"Earnings service error: {str(e)}")


@router.get("/upcoming")
async def get_upcoming_earnings(
    days: int = Query(7, ge=1, le=30, description="Days to look ahead"),
    min_importance: Optional[int] = Query(None, ge=0, le=5, description="Minimum importance"),
    limit: int = Query(200, ge=1, le=1000, description="Max results")
):
    """
    Get upcoming earnings for the next N days.
    
    - **days**: Number of days ahead to fetch (default 7)
    - **min_importance**: Filter by minimum importance (0-5)
    - **limit**: Maximum results to return
    """
    try:
        client = await get_client()
        params = {"days": days, "limit": limit}
        if min_importance is not None:
            params["min_importance"] = min_importance
        
        response = await client.get("/api/v1/earnings/upcoming", params=params)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as e:
        logger.error("earnings_upcoming_error", error=str(e))
        raise HTTPException(status_code=502, detail=f"Earnings service error: {str(e)}")


@router.get("/date/{date}")
async def get_earnings_by_date(
    date: str,
    min_importance: Optional[int] = Query(None, ge=0, le=5),
    time_slot: Optional[str] = Query(None, description="BMO, AMC, or DURING"),
    limit: int = Query(200, ge=1, le=500)
):
    """
    Get earnings for a specific date.
    
    - **date**: Date in YYYY-MM-DD format
    - **min_importance**: Filter by minimum importance
    - **time_slot**: Filter by time slot (BMO, AMC, DURING)
    """
    try:
        client = await get_client()
        params = {"limit": limit}
        if min_importance is not None:
            params["min_importance"] = min_importance
        if time_slot:
            params["time_slot"] = time_slot
        
        response = await client.get(f"/api/v1/earnings/date/{date}", params=params)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as e:
        logger.error("earnings_by_date_error", error=str(e), date=date)
        raise HTTPException(status_code=502, detail=f"Earnings service error: {str(e)}")


@router.get("/ticker/{ticker}")
async def get_earnings_by_ticker(
    ticker: str,
    limit: int = Query(20, ge=1, le=100)
):
    """
    Get earnings history for a specific ticker.
    
    - **ticker**: Stock ticker symbol
    - **limit**: Maximum results (default 20)
    """
    try:
        client = await get_client()
        response = await client.get(
            f"/api/v1/earnings/ticker/{ticker.upper()}",
            params={"limit": limit}
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as e:
        logger.error("earnings_by_ticker_error", error=str(e), ticker=ticker)
        raise HTTPException(status_code=502, detail=f"Earnings service error: {str(e)}")


@router.get("/status")
async def get_earnings_service_status():
    """
    Get earnings service status and statistics.
    """
    try:
        client = await get_client()
        response = await client.get("/status")
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as e:
        logger.error("earnings_status_error", error=str(e))
        return {
            "status": "error",
            "error": str(e)
        }
