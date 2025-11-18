#!/usr/bin/env python3
"""
Data Maintenance Service
Servicio dedicado al mantenimiento de datos históricos

Responsabilidades:
- Ejecutar tareas de mantenimiento al cierre del mercado
- Cargar OHLC diario para ATR
- Cargar volume slots para RVOL
- Enriquecer metadata (market cap, float, sector)
- Sincronizar caches de Redis

Tolerante a fallos:
- Rastrea estado de cada tarea en Redis
- Reanuda desde la última tarea completada si se reinicia
"""

import asyncio
import sys
from datetime import datetime
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
from datetime import date
import uvicorn

# Agregar paths
sys.path.append('/app')

from shared.config.settings import settings
from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import get_logger

from maintenance_scheduler import MaintenanceScheduler
from task_orchestrator import TaskOrchestrator
from realtime_ticker_monitor import RealtimeTickerMonitor

# Logger
logger = get_logger(__name__)

# Global instances
redis_client: RedisClient = None
timescale_client: TimescaleClient = None
scheduler: MaintenanceScheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestión del ciclo de vida del servicio"""
    global redis_client, timescale_client, scheduler
    
    logger.info("🚀 Starting Data Maintenance Service")
    
    # Inicializar clientes
    redis_client = RedisClient()
    timescale_client = TimescaleClient()
    
    await redis_client.connect()
    await timescale_client.connect()
    
    logger.info("✅ Connected to Redis and TimescaleDB")
    
    # 🔥 AUTO-RECOVERY: Verificar salud de Redis y recuperar si es necesario
    from redis_health_checker import RedisHealthChecker
    
    health_checker = RedisHealthChecker(redis_client, timescale_client)
    recovery_result = await health_checker.check_and_recover()
    
    if recovery_result.get("needs_recovery"):
        logger.warning(
            "⚠️ Redis auto-recovery executed",
            issues=recovery_result.get("issues_found", []),
            tasks=recovery_result.get("recovery_results", {}).get("tasks_executed", [])
        )
    else:
        logger.info("✅ Redis health check passed - no recovery needed")
    
    # Inicializar orchestrator y scheduler
    orchestrator = TaskOrchestrator(redis_client, timescale_client)
    scheduler = MaintenanceScheduler(orchestrator)
    
    # Iniciar scheduler en background
    scheduler_task = asyncio.create_task(scheduler.run())
    
    # Iniciar monitor en tiempo real
    realtime_monitor = RealtimeTickerMonitor(redis_client, timescale_client)
    monitor_task = asyncio.create_task(realtime_monitor.start())
    
    logger.info("🔄 Maintenance scheduler started")
    logger.info(f"📅 Schedule: Daily maintenance after market close (post-market end: {settings.post_market_end})")
    logger.info("✅ Real-time ticker monitor started (checks every 5 min)")
    
    yield
    
    # Detener monitor en tiempo real
    await realtime_monitor.stop()
    if monitor_task:
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass
    
    # Cleanup
    logger.info("🛑 Shutting down Data Maintenance Service")
    
    scheduler_task.cancel()
    try:
        await scheduler_task
    except asyncio.CancelledError:
        pass
    
        await timescale_client.disconnect()
        await redis_client.disconnect()
    
    logger.info("👋 Data Maintenance Service stopped")


# FastAPI app
app = FastAPI(
    title="Data Maintenance Service",
    description="Servicio de mantenimiento automático de datos históricos",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Check Redis
        await redis_client.client.ping()
        
        # Check TimescaleDB
        await timescale_client.fetch("SELECT 1")
        
        # Get last maintenance info
        last_run = await redis_client.get("maintenance:last_run")
        last_status = await redis_client.get(f"maintenance:status:{last_run}" if last_run else "maintenance:status:none")
        
        return {
            "status": "healthy",
            "service": "data_maintenance",
            "timestamp": datetime.now().isoformat(),
            "redis": "connected",
            "timescaledb": "connected",
            "last_maintenance": last_run,
            "scheduler_running": scheduler.is_running if scheduler else False
        }
    except Exception as e:
        logger.error("health_check_failed", error=str(e))
        return {
            "status": "unhealthy",
            "service": "data_maintenance",
            "error": str(e)
        }


@app.get("/status")
async def get_status():
    """Get detailed maintenance status"""
    try:
        # Obtener el valor como string sin deserializar
        last_run = await redis_client.get("maintenance:last_run", deserialize=False)
        
        if not last_run:
            return {
                "status": "no_maintenance_run_yet",
                "message": "No maintenance has been executed yet"
            }
        
        status_key = f"maintenance:status:{last_run}"
        # Obtener el status como string JSON y deserializar manualmente
        status_str = await redis_client.get(status_key, deserialize=False)
        
        if status_str:
            import json
            status_data = json.loads(status_str) if isinstance(status_str, str) else status_str
            
            return {
                "status": "ok",
                "last_maintenance": last_run,
                "details": status_data
            }
        else:
            return {
                "status": "no_status_data",
                "last_maintenance": last_run
            }
    
    except Exception as e:
        import traceback
        logger.error("status_check_failed", error=str(e), traceback=traceback.format_exc())
        return {
            "status": "error",
            "error": str(e)
        }


class TriggerRequest(BaseModel):
    target_date: Optional[str] = None  # ISO format: "2025-11-14"


@app.post("/trigger")
async def trigger_maintenance(request: Optional[TriggerRequest] = None):
    """Trigger maintenance manually (for testing)
    
    Args:
        request: Optional body with target_date in ISO format (e.g., "2025-11-14")
                 If not provided, uses yesterday's date
    """
    try:
        target_date = None
        if request and request.target_date:
            target_date = date.fromisoformat(request.target_date)
            logger.info("⚡ Manual maintenance trigger requested", target_date=request.target_date)
        else:
            logger.info("⚡ Manual maintenance trigger requested (using default: yesterday)")
        
        if scheduler:
            asyncio.create_task(scheduler.orchestrator.run_maintenance_cycle(target_date))
            return {
                "status": "triggered",
                "message": "Maintenance cycle started",
                "target_date": target_date.isoformat() if target_date else "yesterday"
            }
        else:
            return {
                "status": "error",
                "message": "Scheduler not initialized"
            }
    
    except Exception as e:
        logger.error("manual_trigger_failed", error=str(e))
        return {
            "status": "error",
            "error": str(e)
        }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8008,
        log_level="info"
    )
