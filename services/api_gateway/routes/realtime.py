"""
Real-time ticker data endpoint
Reads from Redis Hash snapshot:enriched:latest for live data.

Uses HGET for single ticker lookups (~500 bytes instead of ~7MB).
"""

from fastapi import APIRouter, HTTPException
from typing import Optional
import orjson

router = APIRouter(prefix="/api/v1/realtime", tags=["realtime"])

# Redis client will be injected from main.py
redis_client = None

def set_redis_client(client):
    global redis_client
    redis_client = client


@router.get("/ticker/{symbol}")
async def get_realtime_ticker(symbol: str):
    """
    Get real-time data for a specific ticker from the enriched snapshot hash.
    
    Uses HGET to read ONLY this ticker (~500 bytes) instead of
    reading the full snapshot (~7MB) and searching through it.
    """
    if not redis_client:
        raise HTTPException(status_code=503, detail="Redis not available")
    
    try:
        # Read ONLY this ticker from the hash (HGET = ~500 bytes vs GET = ~7MB)
        ticker_json = await redis_client.client.hget("snapshot:enriched:latest", symbol.upper())
        
        if not ticker_json:
            raise HTTPException(
                status_code=404, 
                detail=f"Ticker {symbol} not found in snapshot"
            )
        
        # Parse the single ticker JSON
        try:
            ticker_data = orjson.loads(ticker_json)
        except Exception:
            raise HTTPException(status_code=500, detail="Failed to parse ticker data")
        
        # Read metadata for timestamp
        meta_raw = await redis_client.client.hget("snapshot:enriched:latest", "__meta__")
        meta = orjson.loads(meta_raw) if meta_raw else {}
        
        # Extract relevant data for chart
        min_data = ticker_data.get("min", {})
        day_data = ticker_data.get("day", {})
        last_trade = ticker_data.get("lastTrade", {})
        
        return {
            "symbol": symbol.upper(),
            "timestamp": meta.get("timestamp"),
            "minute": {
                "time": min_data.get("t", 0),  # timestamp in ms
                "open": min_data.get("o", 0),
                "high": min_data.get("h", 0),
                "low": min_data.get("l", 0),
                "close": min_data.get("c", 0),
                "volume": min_data.get("v", 0),
                "volume_accumulated": min_data.get("av", 0),
            },
            "day": {
                "open": day_data.get("o", 0),
                "high": day_data.get("h", 0),
                "low": day_data.get("l", 0),
                "close": day_data.get("c", 0),
                "volume": day_data.get("v", 0),
            },
            "last_price": last_trade.get("p", ticker_data.get("current_price", 0)),
            "intraday_high": ticker_data.get("intraday_high"),
            "intraday_low": ticker_data.get("intraday_low"),
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

