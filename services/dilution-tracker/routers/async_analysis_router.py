"""
Async Analysis Router
Análisis asíncrono con resultados parciales y notificaciones de progreso
"""

import sys
sys.path.append('/app')

import asyncio
import uuid
from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum

from shared.utils.timescale_client import TimescaleClient
from shared.utils.redis_client import RedisClient
from shared.utils.logger import get_logger
from shared.config.settings import settings

from strategies.search_tracker import SearchTracker
from services.data.data_aggregator import DataAggregator

logger = get_logger(__name__)

router = APIRouter(prefix="/api/analysis/async", tags=["async-analysis"])

# Estados del análisis
class AnalysisPhase(str, Enum):
    INIT = "init"
    VALIDATING = "validating"
    FETCHING_METADATA = "fetching_metadata"
    FETCHING_FINANCIALS = "fetching_financials"
    FETCHING_HOLDERS = "fetching_holders"
    FETCHING_FILINGS = "fetching_filings"
    ANALYZING_SEC = "analyzing_sec"
    CALCULATING_RISK = "calculating_risk"
    COMPLETED = "completed"
    ERROR = "error"

# Mensajes amigables para cada fase (estilo terminal)
PHASE_MESSAGES = {
    AnalysisPhase.INIT: "Initializing analysis engine...",
    AnalysisPhase.VALIDATING: "Validating ticker in market universe...",
    AnalysisPhase.FETCHING_METADATA: "Retrieving company metadata from sources...",
    AnalysisPhase.FETCHING_FINANCIALS: "Downloading financial statements (10-K, 10-Q)...",
    AnalysisPhase.FETCHING_HOLDERS: "Scanning institutional holders database...",
    AnalysisPhase.FETCHING_FILINGS: "Indexing SEC EDGAR filings...",
    AnalysisPhase.ANALYZING_SEC: "Deep analysis of regulatory filings...",
    AnalysisPhase.CALCULATING_RISK: "Computing dilution risk metrics...",
    AnalysisPhase.COMPLETED: "Analysis complete ✓",
    AnalysisPhase.ERROR: "Analysis failed ✗"
}


def serialize_for_json(obj):
    """Convertir objetos no serializables a JSON"""
    import json
    from datetime import date, datetime as dt
    from decimal import Decimal
    
    if isinstance(obj, dict):
        return {k: serialize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [serialize_for_json(item) for item in obj]
    elif isinstance(obj, (date, dt)):
        return obj.isoformat()
    elif isinstance(obj, Decimal):
        return float(obj)
    elif hasattr(obj, '__dict__'):
        return serialize_for_json(obj.__dict__)
    return obj


async def update_job_status(
    redis: RedisClient,
    job_id: str,
    phase: AnalysisPhase,
    progress: int,
    data: Optional[Dict] = None,
    error: Optional[str] = None
):
    """Actualizar estado del job en Redis"""
    status = {
        "job_id": job_id,
        "phase": phase.value,
        "phase_message": PHASE_MESSAGES[phase],
        "progress": progress,
        "updated_at": datetime.utcnow().isoformat(),
        "data": serialize_for_json(data) if data else {},
        "error": error
    }
    await redis.set(f"job:analysis:{job_id}", status, ttl=3600)  # 1 hour TTL
    
    # Publicar en canal para WebSocket
    await redis.publish(f"job:progress:{job_id}", status)


async def run_async_analysis(job_id: str, ticker: str):
    """Ejecutar análisis en background con actualizaciones de progreso"""
    db = TimescaleClient()
    redis = RedisClient()
    
    try:
        await db.connect()
        await redis.connect()
        
        aggregator = DataAggregator(db, redis)
        result = {}
        
        # Phase 1: Init
        await update_job_status(redis, job_id, AnalysisPhase.INIT, 5)
        await asyncio.sleep(0.3)  # Pequeña pausa para efecto visual
        
        # Phase 2: Validating
        await update_job_status(redis, job_id, AnalysisPhase.VALIDATING, 10)
        is_valid = await aggregator._validate_ticker(ticker)
        if not is_valid:
            await update_job_status(redis, job_id, AnalysisPhase.ERROR, 0, error=f"Ticker {ticker} not found in universe")
            return
        
        # Phase 3: Metadata
        await update_job_status(redis, job_id, AnalysisPhase.FETCHING_METADATA, 20)
        summary = await aggregator._get_or_fetch_summary(ticker)
        result["summary"] = serialize_for_json(summary)
        await update_job_status(redis, job_id, AnalysisPhase.FETCHING_METADATA, 25, data={"summary": result["summary"]})
        
        # Phase 4: Financials
        await update_job_status(redis, job_id, AnalysisPhase.FETCHING_FINANCIALS, 30)
        financials = await aggregator._get_or_fetch_financials(ticker)
        result["financials"] = serialize_for_json(financials)
        await update_job_status(redis, job_id, AnalysisPhase.FETCHING_FINANCIALS, 40, data={"financials_count": len(financials)})
        
        # Phase 5: Holders
        await update_job_status(redis, job_id, AnalysisPhase.FETCHING_HOLDERS, 45)
        holders = await aggregator._get_or_fetch_holders(ticker)
        result["holders"] = serialize_for_json(holders)
        await update_job_status(redis, job_id, AnalysisPhase.FETCHING_HOLDERS, 55, data={"holders_count": len(holders)})
        
        # Phase 6: Filings
        await update_job_status(redis, job_id, AnalysisPhase.FETCHING_FILINGS, 60)
        filings = await aggregator._get_or_fetch_filings(ticker)
        result["filings"] = serialize_for_json(filings)
        await update_job_status(redis, job_id, AnalysisPhase.FETCHING_FILINGS, 70, data={"filings_count": len(filings)})
        
        # Phase 7: SEC Analysis (lo más lento - puede omitirse para primera carga)
        await update_job_status(redis, job_id, AnalysisPhase.ANALYZING_SEC, 75)
        # Este paso es opcional para carga inicial rápida
        dilution_data = None
        try:
            # Solo intentar si hay cache o es refresh explícito
            cached_dilution = await redis.get(f"sec_dilution:profile:{ticker}")
            if cached_dilution:
                dilution_data = cached_dilution
        except:
            pass
        result["dilution"] = dilution_data
        await update_job_status(redis, job_id, AnalysisPhase.ANALYZING_SEC, 85, data={"dilution_available": dilution_data is not None})
        
        # Phase 8: Risk calculation
        await update_job_status(redis, job_id, AnalysisPhase.CALCULATING_RISK, 90)
        risk_scores = aggregator._calculate_risk_scores(financials, filings)
        result["risk_scores"] = risk_scores
        
        # Serializar todo el resultado para JSON
        serialized_result = serialize_for_json(result)
        
        # Phase 9: Completed
        await update_job_status(redis, job_id, AnalysisPhase.COMPLETED, 100, data=serialized_result)
        
        # Cache final result
        await redis.set(f"dilution:analysis:{ticker}", serialized_result, ttl=3600)
        
        logger.info("async_analysis_completed", job_id=job_id, ticker=ticker)
        
    except Exception as e:
        logger.error("async_analysis_failed", job_id=job_id, ticker=ticker, error=str(e))
        await update_job_status(redis, job_id, AnalysisPhase.ERROR, 0, error=str(e))
    finally:
        await db.disconnect()
        await redis.disconnect()


@router.post("/{ticker}/start")
async def start_async_analysis(ticker: str, background_tasks: BackgroundTasks):
    """
    Iniciar análisis asíncrono de un ticker
    
    Devuelve job_id para consultar el estado y resultados parciales
    """
    ticker = ticker.upper()
    job_id = str(uuid.uuid4())[:8]  # Short job ID
    
    # Iniciar análisis en background
    background_tasks.add_task(run_async_analysis, job_id, ticker)
    
    logger.info("async_analysis_started", job_id=job_id, ticker=ticker)
    
    return {
        "job_id": job_id,
        "ticker": ticker,
        "status": "started",
        "poll_url": f"/api/analysis/async/{ticker}/status/{job_id}",
        "ws_channel": f"job:progress:{job_id}"
    }


@router.get("/{ticker}/status/{job_id}")
async def get_analysis_status(ticker: str, job_id: str):
    """
    Obtener estado actual del análisis
    """
    redis = RedisClient()
    await redis.connect()
    
    try:
        status = await redis.get(f"job:analysis:{job_id}")
        
        if not status:
            raise HTTPException(status_code=404, detail="Job not found or expired")
        
        return status
        
    finally:
        await redis.disconnect()


@router.get("/{ticker}/quick")
async def get_quick_analysis(ticker: str):
    """
    Análisis rápido - solo datos básicos sin SEC deep analysis
    
    Devuelve: metadata, financials, holders, filings (sin análisis LLM)
    Ideal para carga inicial mientras el análisis profundo corre en background
    """
    ticker = ticker.upper()
    
    db = TimescaleClient()
    redis = RedisClient()
    await db.connect()
    await redis.connect()
    
    try:
        aggregator = DataAggregator(db, redis)
        
        # Validar ticker
        is_valid = await aggregator._validate_ticker(ticker)
        if not is_valid:
            raise HTTPException(status_code=404, detail=f"Ticker {ticker} not found")
        
        # Obtener datos en paralelo (más rápido)
        summary_task = asyncio.create_task(aggregator._get_or_fetch_summary(ticker))
        financials_task = asyncio.create_task(aggregator._get_or_fetch_financials(ticker))
        holders_task = asyncio.create_task(aggregator._get_or_fetch_holders(ticker))
        filings_task = asyncio.create_task(aggregator._get_or_fetch_filings(ticker))
        
        summary, financials, holders, filings = await asyncio.gather(
            summary_task, financials_task, holders_task, filings_task
        )
        
        # Calcular risk scores básicos
        risk_scores = aggregator._calculate_risk_scores(financials, filings)
        
        return {
            "summary": summary,
            "financials": financials,
            "holders": holders,
            "filings": filings,
            "risk_scores": risk_scores,
            "dilution": None,  # Se obtiene con deep analysis
            "is_quick_analysis": True,
            "deep_analysis_available": False
        }
        
    finally:
        await db.disconnect()
        await redis.disconnect()

