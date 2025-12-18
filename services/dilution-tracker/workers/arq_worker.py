"""
ARQ Worker Configuration
========================
Worker para procesar jobs de scraping SEC en background.
Se ejecuta como proceso separado del API.

Uso:
    arq workers.arq_worker.WorkerSettings
"""

import sys
sys.path.append('/app')

import asyncio
from typing import Any, Dict, Optional
from datetime import timedelta

from arq import cron
from arq.connections import RedisSettings
import redis.asyncio as aioredis

from shared.config.settings import settings
from shared.utils.logger import get_logger
from jobs.scraping_jobs import (
    scrape_sec_dilution,
    scrape_sec_dilution_priority,
)

logger = get_logger(__name__)


def get_redis_settings() -> RedisSettings:
    """Configuración de Redis para ARQ."""
    return RedisSettings(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        password=settings.redis_password,
        database=2,  # DB separada para jobs (DB 0 es cache)
    )


async def startup(ctx: Dict[str, Any]) -> None:
    """
    Se ejecuta al iniciar el worker.
    Inicializa conexiones a DB, Redis cache, HTTP clients, etc.
    """
    logger.info("arq_worker_starting")
    
    # Conexión a Redis para cache (separada de la cola de jobs)
    ctx["redis_cache"] = await aioredis.from_url(
        f"redis://:{settings.redis_password}@{settings.REDIS_HOST}:{settings.REDIS_PORT}/0",
        encoding="utf-8",
        decode_responses=True
    )
    
    # Conexión a TimescaleDB
    import asyncpg
    ctx["db_pool"] = await asyncpg.create_pool(
        host=settings.TIMESCALE_HOST,
        port=settings.TIMESCALE_PORT,
        user=settings.TIMESCALE_USER,
        password=settings.TIMESCALE_PASSWORD,
        database=settings.TIMESCALE_DB,
        min_size=2,
        max_size=10
    )
    
    # Inicializar HTTP clients (para scraping SEC)
    from http_clients import http_clients
    await http_clients.initialize(
        polygon_api_key=settings.POLYGON_API_KEY,
        fmp_api_key=settings.FMP_API_KEY,
        sec_api_key=getattr(settings, 'SEC_API_IO_KEY', None),
    )
    ctx["http_clients"] = http_clients
    
    logger.info("arq_worker_started", redis="connected", db="connected", http_clients="initialized")


async def shutdown(ctx: Dict[str, Any]) -> None:
    """
    Se ejecuta al cerrar el worker.
    Cierra conexiones limpiamente.
    """
    logger.info("arq_worker_shutting_down")
    
    if "http_clients" in ctx:
        await ctx["http_clients"].close()
    
    if "redis_cache" in ctx:
        await ctx["redis_cache"].close()
    
    if "db_pool" in ctx:
        await ctx["db_pool"].close()
    
    logger.info("arq_worker_shutdown_complete")


async def on_job_start(ctx: Dict[str, Any]) -> None:
    """Hook que se ejecuta al iniciar cada job."""
    job_id = ctx.get("job_id", "unknown")
    logger.info("job_started", job_id=job_id)


async def on_job_end(ctx: Dict[str, Any]) -> None:
    """Hook que se ejecuta al terminar cada job."""
    job_id = ctx.get("job_id", "unknown")
    logger.info("job_ended", job_id=job_id)


class WorkerSettings:
    """
    Configuración del worker ARQ.
    """
    # Conexión a Redis
    redis_settings = get_redis_settings()
    
    # Jobs disponibles
    functions = [
        scrape_sec_dilution,
        scrape_sec_dilution_priority,
    ]
    
    # Hooks de ciclo de vida
    on_startup = startup
    on_shutdown = shutdown
    on_job_start = on_job_start
    on_job_end = on_job_end
    
    # Configuración del worker
    max_jobs = 3  # Jobs concurrentes máximos
    job_timeout = 3600  # 1 hora - análisis exhaustivo puede tardar
    max_tries = 3  # Reintentos automáticos
    retry_delay = 10  # Segundos entre reintentos
    
    # Usar queue por defecto de ARQ (arq:queue)
    # queue_name = "arq:queue"  # Default
    
    # Health check
    health_check_interval = 30
    
    # Cron jobs (opcional - para tareas programadas)
    # cron_jobs = [
    #     cron(cleanup_old_jobs, hour=3, minute=0),  # Limpiar jobs viejos a las 3am
    # ]

