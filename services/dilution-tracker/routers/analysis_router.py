"""
Analysis Router
Endpoint principal para análisis completo de dilución
"""

import sys
sys.path.append('/app')

from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
from datetime import datetime

from shared.utils.timescale_client import TimescaleClient
from shared.utils.redis_client import RedisClient
from shared.utils.logger import get_logger
from shared.config.settings import settings

from strategies.search_tracker import SearchTracker
from models.dilution_models import DilutionMetricsResponse

logger = get_logger(__name__)

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.get("/{ticker}")
async def get_ticker_analysis(ticker: str):
    """
    Obtener análisis completo de un ticker
    
    Retorna:
    - Información básica del ticker (reutiliza ticker-metadata-service)
    - Métricas de dilución calculadas
    - Risk scores
    - Cash runway analysis
    """
    try:
        ticker = ticker.upper()
        
        # 1. Track search
        # TODO: Implementar tracking
        
        # 2. Check cache
        redis = RedisClient()
        await redis.connect()
        cache_key = f"dilution:analysis:{ticker}"
        
        cached = await redis.get(cache_key)
        await redis.disconnect()
        
        if cached:
            logger.info("cache_hit", ticker=ticker, endpoint="analysis")
            return cached
        
        # 3. Get from DB or fetch from API
        # TODO: Implementar lazy loading con fetch
        
        # Por ahora retornar estructura básica
        response = {
            "ticker": ticker,
            "timestamp": datetime.now().isoformat(),
            "status": "pending_implementation",
            "message": "Service structure created, data fetching to be implemented"
        }
        
        return response
        
    except Exception as e:
        logger.error("get_ticker_analysis_failed", ticker=ticker, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{ticker}/summary")
async def get_ticker_summary(ticker: str):
    """
    Obtener resumen rápido del ticker
    
    Retorna solo info básica sin análisis profundo
    """
    try:
        ticker = ticker.upper()
        
        # Obtener metadata básica desde ticker-metadata-service
        # o desde BD directamente
        
        response = {
            "ticker": ticker,
            "company_name": None,
            "sector": None,
            "market_cap": None,
            "float_shares": None,
            "shares_outstanding": None
        }
        
        return response
        
    except Exception as e:
        logger.error("get_ticker_summary_failed", ticker=ticker, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{ticker}/risk-scores")
async def get_risk_scores(ticker: str):
    """
    Obtener risk scores calculados
    """
    try:
        ticker = ticker.upper()
        
        # Obtener desde dilution_metrics table
        
        response = {
            "ticker": ticker,
            "overall_risk_score": None,
            "cash_need_score": None,
            "dilution_risk_score": None,
            "risk_level": "unknown",
            "calculated_at": None
        }
        
        return response
        
    except Exception as e:
        logger.error("get_risk_scores_failed", ticker=ticker, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{ticker}/refresh")
async def refresh_ticker_data(ticker: str):
    """
    Forzar actualización de datos del ticker
    """
    try:
        ticker = ticker.upper()
        
        # Invalidate cache
        redis = RedisClient()
        await redis.connect()
        await redis.delete(f"dilution:analysis:{ticker}")
        await redis.delete(f"dilution:financials:{ticker}")
        await redis.delete(f"dilution:holders:{ticker}")
        await redis.disconnect()
        
        # Trigger background job to fetch new data
        # TODO: Implementar job trigger
        
        return {
            "ticker": ticker,
            "status": "refresh_initiated",
            "message": "Data refresh has been initiated"
        }
        
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

