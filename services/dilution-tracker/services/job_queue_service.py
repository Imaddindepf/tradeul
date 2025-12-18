"""
Job Queue Service
=================
Servicio para encolar y gestionar jobs de scraping usando ARQ.
"""

import json
from typing import Any, Dict, Optional
from datetime import datetime, timedelta

from arq import create_pool
from arq.connections import RedisSettings, ArqRedis

from shared.config.settings import settings
from shared.utils.logger import get_logger

logger = get_logger(__name__)


class JobQueueService:
    """
    Servicio para encolar jobs de scraping en ARQ.
    
    Uso:
        queue = JobQueueService()
        await queue.connect()
        job = await queue.enqueue_scraping("AAPL")
        status = await queue.get_job_status("AAPL")
    """
    
    def __init__(self):
        self._pool: Optional[ArqRedis] = None
        self._redis_settings = RedisSettings(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.redis_password,
            database=2,  # Misma DB que el worker
        )
    
    async def connect(self) -> None:
        """Conectar al pool de Redis para ARQ."""
        if self._pool is None:
            self._pool = await create_pool(self._redis_settings)
            logger.info("job_queue_connected")
    
    async def close(self) -> None:
        """Cerrar conexión al pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("job_queue_disconnected")
    
    async def enqueue_scraping(
        self,
        ticker: str,
        company_name: Optional[str] = None,
        force_refresh: bool = False,
        priority: bool = False,
        defer_seconds: int = 0
    ) -> Dict[str, Any]:
        """
        Encola un job de scraping de SEC dilution.
        
        Args:
            ticker: Símbolo del ticker
            company_name: Nombre de la empresa (opcional)
            force_refresh: Forzar re-scraping
            priority: Si True, usa job de alta prioridad
            defer_seconds: Segundos a esperar antes de ejecutar
            
        Returns:
            Dict con info del job encolado
        """
        if not self._pool:
            await self.connect()
        
        # Verificar si ya hay un job en proceso para este ticker
        existing = await self.get_job_status(ticker)
        if existing and existing.get("status") == "processing":
            logger.info(
                "job_already_processing",
                ticker=ticker,
                job_id=existing.get("job_id")
            )
            return {
                "status": "already_processing",
                "ticker": ticker,
                "existing_job_id": existing.get("job_id"),
            }
        
        # Seleccionar función del job
        job_function = (
            "scrape_sec_dilution_priority" if priority 
            else "scrape_sec_dilution"
        )
        
        # Encolar el job
        defer_until = None
        if defer_seconds > 0:
            defer_until = datetime.utcnow() + timedelta(seconds=defer_seconds)
        
        job = await self._pool.enqueue_job(
            job_function,
            ticker,
            company_name,
            force_refresh,
            _defer_until=defer_until,
        )
        
        logger.info(
            "job_enqueued",
            ticker=ticker,
            job_id=job.job_id,
            priority=priority,
            defer_seconds=defer_seconds
        )
        
        return {
            "status": "queued",
            "ticker": ticker,
            "job_id": job.job_id,
            "priority": priority,
            "queued_at": datetime.utcnow().isoformat(),
        }
    
    async def get_job_status(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene el estado actual de un job para un ticker.
        
        Returns:
            Dict con estado del job o None si no existe
        """
        if not self._pool:
            await self.connect()
        
        # El estado se guarda en Redis por los jobs
        import redis.asyncio as aioredis
        redis = await aioredis.from_url(
            f"redis://:{settings.redis_password}@{settings.REDIS_HOST}:{settings.REDIS_PORT}/0",
            encoding="utf-8",
            decode_responses=True
        )
        
        try:
            key = f"dilution:job:{ticker}"
            data = await redis.hgetall(key)
            
            if data:
                return data
            return None
        finally:
            await redis.close()
    
    async def get_queue_stats(self) -> Dict[str, Any]:
        """
        Obtiene estadísticas de la cola de jobs.
        
        Returns:
            Dict con estadísticas (pending, processing, completed, failed)
        """
        if not self._pool:
            await self.connect()
        
        # ARQ guarda info en Redis que podemos consultar
        queued = await self._pool.queued_jobs()
        
        return {
            "queued_jobs": len(queued) if queued else 0,
            "timestamp": datetime.utcnow().isoformat(),
        }


# Singleton para uso global
_queue_service: Optional[JobQueueService] = None


async def get_job_queue() -> JobQueueService:
    """Obtiene la instancia singleton del servicio de cola."""
    global _queue_service
    
    if _queue_service is None:
        _queue_service = JobQueueService()
        await _queue_service.connect()
    
    return _queue_service

