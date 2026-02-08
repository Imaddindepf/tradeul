"""
Halts API Routes

Endpoints for querying trading halts and resumes.
Data sourced from polygon_ws service LULD stream.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import httpx

from shared.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/halts", tags=["halts"])

# polygon_ws service URL
POLYGON_WS_URL = "http://polygon_ws:8006"


@router.get("/active")
async def get_active_halts():
    """
    Get currently active trading halts.
    
    Returns list of tickers that are currently halted (not yet resumed).
    Updated in real-time from Polygon LULD stream.
    
    Returns:
        Active halts with full details (symbol, halt_time, reason, bands, etc.)
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{POLYGON_WS_URL}/halts/active")
            response.raise_for_status()
            return response.json()
            
    except httpx.HTTPStatusError as e:
        logger.error("get_active_halts_http_error", status=e.response.status_code)
        raise HTTPException(status_code=e.response.status_code, detail="Failed to fetch active halts")
    except httpx.RequestError as e:
        logger.error("get_active_halts_request_error", error=str(e))
        raise HTTPException(status_code=503, detail="Halt service unavailable")
    except Exception as e:
        logger.error("get_active_halts_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_halts_history(
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format (default: today)")
):
    """
    Get halt history for a specific day.
    
    Returns all halts (including resumed) for the specified date.
    Useful for reviewing market activity and identifying volatile periods.
    
    Args:
        date: Date to query (YYYY-MM-DD). Defaults to current day.
    
    Returns:
        Complete halt history with statistics (total, active, resumed)
    """
    try:
        params = {}
        if date:
            params['date'] = date
            
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{POLYGON_WS_URL}/halts/history", params=params)
            response.raise_for_status()
            return response.json()
            
    except httpx.HTTPStatusError as e:
        logger.error("get_halts_history_http_error", status=e.response.status_code)
        raise HTTPException(status_code=e.response.status_code, detail="Failed to fetch halt history")
    except httpx.RequestError as e:
        logger.error("get_halts_history_request_error", error=str(e))
        raise HTTPException(status_code=503, detail="Halt service unavailable")
    except Exception as e:
        logger.error("get_halts_history_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{symbol}")
async def get_halt_status(symbol: str):
    """
    Get halt status for a specific ticker.
    
    Check if a ticker is currently halted and get halt details if so.
    
    Args:
        symbol: Ticker symbol (e.g., AAPL)
    
    Returns:
        Halt status (is_halted) and details if halted
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{POLYGON_WS_URL}/halts/{symbol}")
            response.raise_for_status()
            return response.json()
            
    except httpx.HTTPStatusError as e:
        logger.error("get_halt_status_http_error", symbol=symbol, status=e.response.status_code)
        raise HTTPException(status_code=e.response.status_code, detail="Failed to fetch halt status")
    except httpx.RequestError as e:
        logger.error("get_halt_status_request_error", symbol=symbol, error=str(e))
        raise HTTPException(status_code=503, detail="Halt service unavailable")
    except Exception as e:
        logger.error("get_halt_status_error", symbol=symbol, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
