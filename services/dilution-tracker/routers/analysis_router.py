"""
Analysis Router
Endpoint principal para análisis completo de dilución
"""

import sys
sys.path.append('/app')

from fastapi import APIRouter, HTTPException
from typing import Optional
from datetime import datetime

from shared.utils.timescale_client import TimescaleClient
from shared.utils.redis_client import RedisClient
from shared.utils.logger import get_logger
from shared.config.settings import settings

from strategies.search_tracker import SearchTracker
from services.data.data_aggregator import DataAggregator

logger = get_logger(__name__)

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.get("/{ticker}")
async def get_ticker_analysis(ticker: str):
    """
    Obtener análisis completo de un ticker
    
    Solo permite tickers que existen en el universo de Polygon (ticker_metadata)
    """
    try:
        ticker = ticker.upper()
        
        # Inicializar servicios
        db = TimescaleClient()
        await db.connect()
        redis = RedisClient()
        await redis.connect()
        
        try:
            # Track search
            tracker = SearchTracker(db, redis)
            await tracker.track_search(ticker)
            
            # Get analysis
            aggregator = DataAggregator(db, redis)
            analysis = await aggregator.get_ticker_analysis(ticker)
            
            if not analysis:
                raise HTTPException(
                    status_code=404,
                    detail=f"Ticker {ticker} not found in universe or no data available"
                )
            
            return analysis
            
        finally:
            await db.disconnect()
            await redis.disconnect()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_ticker_analysis_failed", ticker=ticker, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/validate/{ticker}")
async def validate_ticker(ticker: str):
    """
    Validar si un ticker existe en el universo
    """
    try:
        ticker = ticker.upper()
        
        db = TimescaleClient()
        await db.connect()
        
        try:
            query = """
            SELECT symbol, company_name, sector, is_actively_trading
            FROM ticker_metadata
            WHERE symbol = $1
            """
            
            result = await db.fetchrow(query, ticker)
            
            if not result:
                return {
                    "valid": False,
                    "ticker": ticker,
                    "message": "Ticker not found in universe"
                }
            
            if not result['is_actively_trading']:
                return {
                    "valid": False,
                    "ticker": ticker,
                    "message": "Ticker is not actively trading"
                }
            
            return {
                "valid": True,
                "ticker": ticker,
                "company_name": result['company_name'],
                "sector": result['sector']
            }
            
        finally:
            await db.disconnect()
        
    except Exception as e:
        logger.error("validate_ticker_failed", ticker=ticker, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))




@router.post("/{ticker}/refresh")
async def refresh_ticker_data(ticker: str):
    """
    Forzar actualización de datos del ticker
    """
    try:
        ticker = ticker.upper()
        
        db = TimescaleClient()
        await db.connect()
        redis = RedisClient()
        await redis.connect()
        
        try:
            # Invalidate cache
            await redis.delete(f"dilution:analysis:{ticker}")
            
            # Force refresh
            aggregator = DataAggregator(db, redis)
            analysis = await aggregator.get_ticker_analysis(ticker, force_refresh=True)
            
            if not analysis:
                raise HTTPException(status_code=404, detail="Ticker not found")
            
            return {
                "ticker": ticker,
                "status": "refreshed",
                "message": "Data has been refreshed successfully"
            }
            
        finally:
            await db.disconnect()
            await redis.disconnect()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("refresh_ticker_failed", ticker=ticker, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trending")
async def get_trending_tickers(limit: int = 50):
    """
    Obtener tickers más buscados (trending)
    """
    try:
        db = TimescaleClient()
        await db.connect()
        redis = RedisClient()
        await redis.connect()
        
        tracker = SearchTracker(db, redis)
        trending = await tracker.get_trending_tickers(days=7, limit=limit)
        
        return {
            "trending": trending,
            "period": "7_days",
            "count": len(trending)
        }
        
    except Exception as e:
        logger.error("get_trending_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

