"""
Symbols Router - Symbol lookup and filtering endpoints

Uses TimescaleDB (has indexed market_cap column) - faster than Redis SCAN for this query.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException

from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/symbols", tags=["symbols"])

_timescale_client: Optional[TimescaleClient] = None


def set_timescale_client(client: TimescaleClient):
    global _timescale_client
    _timescale_client = client


@router.get("/by-market-cap")
async def get_symbols_by_market_cap(min_market_cap: float = 0):
    """
    Get all symbols that meet minimum market cap requirement.
    Uses TimescaleDB with indexed market_cap column (~150ms).
    
    Args:
        min_market_cap: Minimum market cap in dollars (e.g., 1000000000 for 1B)
    
    Returns:
        List of symbols meeting the criteria
    """
    try:
        if not _timescale_client:
            raise HTTPException(status_code=503, detail="Database not available")
        
        query = """
            SELECT symbol 
            FROM tickers_unified 
            WHERE market_cap >= $1
            ORDER BY market_cap DESC
        """
        
        rows = await _timescale_client.fetch(query, min_market_cap)
        symbols = [row["symbol"] for row in rows]
        
        logger.info("symbols_by_market_cap", min_cap=min_market_cap, count=len(symbols))
        
        return {
            "min_market_cap": min_market_cap,
            "count": len(symbols),
            "symbols": symbols
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("symbols_by_market_cap_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
