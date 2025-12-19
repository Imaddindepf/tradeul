"""
Scraping Jobs for ARQ
=====================
Jobs de background para scraping de SEC filings.
Estos jobs se ejecutan de forma asíncrona en el worker ARQ.
"""

import asyncio
import json
from typing import Any, Dict, Optional
from datetime import datetime

from shared.utils.logger import get_logger

logger = get_logger(__name__)


async def scrape_sec_dilution(
    ctx: Dict[str, Any],
    ticker: str,
    company_name: Optional[str] = None,
    force_refresh: bool = False
) -> Dict[str, Any]:
    """
    Job principal para scraping de dilution de SEC.
    
    Este job:
    1. Obtiene filings de SEC
    2. Extrae información de dilution con Grok
    3. Guarda en cache (Redis) y DB (TimescaleDB)
    4. Notifica via Pub/Sub cuando completa
    
    Args:
        ctx: Contexto del worker (contiene redis_cache, db_pool)
        ticker: Símbolo del ticker
        company_name: Nombre de la empresa (opcional)
        force_refresh: Forzar re-scraping incluso si hay cache
        
    Returns:
        Dict con resultado del scraping
    """
    job_id = ctx.get("job_id", "unknown")
    redis = ctx.get("redis_cache")
    db_pool = ctx.get("db_pool")
    
    logger.info(
        "scrape_sec_dilution_job_started",
        job_id=job_id,
        ticker=ticker,
        force_refresh=force_refresh
    )
    
    start_time = datetime.utcnow()
    result = {
        "ticker": ticker,
        "job_id": job_id,
        "status": "processing",
        "started_at": start_time.isoformat(),
    }
    
    try:
        # Actualizar estado en Redis
        await _update_job_status(redis, ticker, "processing", job_id)
        
        # Importar servicio y clientes aquí para evitar imports circulares
        from services.sec_dilution_service import SECDilutionService
        from shared.utils.timescale_client import TimescaleClient
        from shared.utils.redis_client import RedisClient
        
        # Crear conexiones con nuestros clientes wrapper (NO el aioredis directo)
        db_client = TimescaleClient()
        await db_client.connect()
        redis_client = RedisClient()
        await redis_client.connect()
        
        try:
            # Crear instancia del servicio con clientes compatibles
            service = SECDilutionService(db_client, redis_client)
        
            # Ejecutar scraping completo
            profile = await service.get_dilution_profile(
                ticker, 
                force_refresh=force_refresh
            )
        finally:
            # Cerrar conexiones
            await db_client.disconnect()
            await redis_client.disconnect()
        
        # Calcular duración
        duration = (datetime.utcnow() - start_time).total_seconds()
        
        # Preparar resultado
        result.update({
            "status": "completed",
            "completed_at": datetime.utcnow().isoformat(),
            "duration_seconds": duration,
            "has_warrants": bool(profile.warrants) if profile else False,
            "has_atm": bool(profile.atm_offerings) if profile else False,
            "has_shelf": bool(profile.shelf_registrations) if profile else False,
            "filings_analyzed": len(profile.metadata.source_filings) if profile and profile.metadata else 0,
        })
        
        logger.info(
            "scrape_sec_dilution_job_completed",
            job_id=job_id,
            ticker=ticker,
            duration=duration,
            warrants=result["has_warrants"],
            atm=result["has_atm"]
        )
        
        # Notificar completado via Pub/Sub
        await _notify_job_complete(redis, ticker, result)
        await _update_job_status(redis, ticker, "completed", job_id)
        
        return result
        
    except Exception as e:
        duration = (datetime.utcnow() - start_time).total_seconds()
        
        result.update({
            "status": "failed",
            "error": str(e),
            "completed_at": datetime.utcnow().isoformat(),
            "duration_seconds": duration,
        })
        
        logger.error(
            "scrape_sec_dilution_job_failed",
            job_id=job_id,
            ticker=ticker,
            error=str(e),
            duration=duration
        )
        
        # Notificar fallo
        await _notify_job_complete(redis, ticker, result)
        await _update_job_status(redis, ticker, "failed", job_id, error=str(e))
        
        # Re-raise para que ARQ haga retry si está configurado
        raise


async def scrape_sec_dilution_priority(
    ctx: Dict[str, Any],
    ticker: str,
    company_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Job de alta prioridad para scraping.
    Se ejecuta antes que los jobs normales.
    
    Útil para tickers que el usuario está viendo activamente.
    """
    return await scrape_sec_dilution(
        ctx, 
        ticker, 
        company_name, 
        force_refresh=True  # Siempre refresh para prioridad
    )


async def _update_job_status(
    redis,
    ticker: str,
    status: str,
    job_id: str,
    error: Optional[str] = None
) -> None:
    """Actualiza el estado del job en Redis."""
    if not redis:
        return
        
    key = f"dilution:job:{ticker}"
    data = {
        "status": status,
        "job_id": job_id,
        "updated_at": datetime.utcnow().isoformat(),
    }
    if error:
        data["error"] = error
        
    await redis.hset(key, mapping=data)
    await redis.expire(key, 3600)  # Expira en 1 hora


async def _notify_job_complete(
    redis,
    ticker: str,
    result: Dict[str, Any]
) -> None:
    """
    Notifica via Redis Pub/Sub que un job completó.
    El frontend puede suscribirse a este canal para actualizaciones en tiempo real.
    """
    if not redis:
        return
        
    channel = "dilution:job:complete"
    message = json.dumps({
        "ticker": ticker,
        "result": result,
        "timestamp": datetime.utcnow().isoformat()
    })
    
    await redis.publish(channel, message)
    
    logger.debug(
        "job_completion_published",
        ticker=ticker,
        channel=channel
    )

