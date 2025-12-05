"""
Real-time ticker data endpoint
Reads from Redis snapshot:enriched:latest for live data
"""

from fastapi import APIRouter, HTTPException
from typing import Optional
import json

router = APIRouter(prefix="/api/v1/realtime", tags=["realtime"])

# Redis client will be injected from main.py
redis_client = None

def set_redis_client(client):
    global redis_client
    redis_client = client


@router.get("/ticker/{symbol}")
async def get_realtime_ticker(symbol: str):
    """
    Get real-time data for a specific ticker from the enriched snapshot.
    
    Returns OHLCV data for the current minute, suitable for chart updates.
    """
    if not redis_client:
        raise HTTPException(status_code=503, detail="Redis not available")
    
    try:
        # Read from enriched snapshot
        snapshot_data = await redis_client.get("snapshot:enriched:latest")
        
        if not snapshot_data:
            raise HTTPException(status_code=404, detail="No snapshot available")
        
        # Find the ticker
        tickers = snapshot_data.get("tickers", [])
        ticker_data = next(
            (t for t in tickers if t.get("ticker") == symbol.upper()),
            None
        )
        
        if not ticker_data:
            raise HTTPException(
                status_code=404, 
                detail=f"Ticker {symbol} not found in snapshot"
            )
        
        # Extract relevant data for chart
        min_data = ticker_data.get("min", {})
        day_data = ticker_data.get("day", {})
        last_trade = ticker_data.get("lastTrade", {})
        
        return {
            "symbol": symbol.upper(),
            "timestamp": snapshot_data.get("timestamp"),
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

