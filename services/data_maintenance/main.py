#!/usr/bin/env python3
"""
Data Maintenance Service
========================

Servicio de mantenimiento de datos que se ejecuta a las 3:00 AM ET.

Funcionalidades:
1. Scheduler diario (3:00 AM ET, 1h antes del pre-market)
2. Limpieza de caches de tiempo real
3. Carga de datos históricos (OHLC, volume slots)
4. Cálculo de indicadores (ATR, RVOL)
5. Sincronización de Redis
6. API para monitoreo y triggers manuales

Arquitectura:
- DailyMaintenanceScheduler: Ejecuta el ciclo completo a las 3:00 AM ET
- MaintenanceOrchestrator: Coordina las tareas individuales
- Tareas individuales: Cada una es independiente y auto-validada
"""

import asyncio
import json
import sys
from datetime import datetime, date
from contextlib import asynccontextmanager
from typing import Optional

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

# Agregar paths
sys.path.append('/app')

from shared.config.settings import settings
from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import get_logger

# Imports del servicio
from daily_maintenance_scheduler import DailyMaintenanceScheduler
from maintenance_orchestrator import MaintenanceOrchestrator
from realtime_ticker_monitor import RealtimeTickerMonitor

logger = get_logger(__name__)

# Global instances
redis_client: RedisClient = None
timescale_client: TimescaleClient = None
daily_scheduler: DailyMaintenanceScheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestión del ciclo de vida del servicio"""
    global redis_client, timescale_client, daily_scheduler
    
    logger.info("🚀 Starting Data Maintenance Service v2.0")
    
    # Inicializar clientes
    redis_client = RedisClient()
    timescale_client = TimescaleClient()
    
    await redis_client.connect()
    await timescale_client.connect()
    
    logger.info("✅ Connected to Redis and TimescaleDB")
    
    # Verificar salud inicial
    await _check_initial_health()
    
    # Inicializar scheduler
    daily_scheduler = DailyMaintenanceScheduler(redis_client, timescale_client)
    scheduler_task = asyncio.create_task(daily_scheduler.run())
    
    # Iniciar monitor en tiempo real (para nuevos tickers durante el día)
    realtime_monitor = RealtimeTickerMonitor(redis_client, timescale_client)
    monitor_task = asyncio.create_task(realtime_monitor.start())
    
    logger.info("=" * 60)
    logger.info("📅 Schedule: Daily maintenance at 3:00 AM ET")
    logger.info("   (1 hour before pre-market opens at 4:00 AM ET)")
    logger.info("📊 Pattern Matching: Dedicated server 37.27.183.194:8025")
    logger.info("=" * 60)
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down Data Maintenance Service")
    
    await realtime_monitor.stop()
    monitor_task.cancel()
    
    daily_scheduler.stop()
    scheduler_task.cancel()
    
    try:
        await monitor_task
    except asyncio.CancelledError:
        pass
    
    try:
        await scheduler_task
    except asyncio.CancelledError:
        pass
    
    await timescale_client.disconnect()
    await redis_client.disconnect()
    
    logger.info("👋 Data Maintenance Service stopped")


async def _check_initial_health():
    """Verificar salud inicial de Redis y BD"""
    try:
        # Verificar que hay datos en la BD
        count_query = "SELECT COUNT(*) as count FROM tickers_unified WHERE is_actively_trading = true"
        rows = await timescale_client.fetch(count_query)
        ticker_count = rows[0]["count"] if rows else 0
        
        # Verificar Redis universe
        redis_count = await redis_client.client.scard("ticker:universe")
        
        logger.info(
            "📊 Initial health check",
            db_tickers=ticker_count,
            redis_universe=redis_count
        )
        
        # Si hay discrepancia grande, advertir
        if abs(ticker_count - redis_count) > 1000:
            logger.warning(
                "⚠️ DB/Redis mismatch detected",
                db_count=ticker_count,
                redis_count=redis_count,
                action="Will be fixed at next maintenance cycle"
            )
            
    except Exception as e:
        logger.error("health_check_failed", error=str(e))


# FastAPI app
app = FastAPI(
    title="Data Maintenance Service",
    description="Servicio de mantenimiento automático de datos históricos",
    version="2.0.0",
    lifespan=lifespan
)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        await redis_client.client.ping()
        await timescale_client.fetch("SELECT 1")
        
        last_run = await redis_client.get("maintenance:last_run")
        
        return {
            "status": "healthy",
            "service": "data_maintenance",
            "version": "2.0.0",
            "timestamp": datetime.now().isoformat(),
            "redis": "connected",
            "timescaledb": "connected",
            "last_maintenance": last_run,
            "scheduler_running": daily_scheduler.is_running if daily_scheduler else False,
            "schedule": "3:00 AM ET daily"
        }
    except Exception as e:
        logger.error("health_check_failed", error=str(e))
        return {
            "status": "unhealthy",
            "error": str(e)
        }


@app.get("/status")
async def get_status():
    """Get detailed maintenance status"""
    try:
        last_run = await redis_client.get("maintenance:last_run")
        
        if not last_run:
            return {
                "status": "no_maintenance_run_yet",
                "message": "No maintenance has been executed yet",
                "schedule": "3:00 AM ET daily"
            }
        
        status_key = f"maintenance:status:{last_run}"
        status_str = await redis_client.get(status_key)
        
        if status_str:
            status_data = json.loads(status_str) if isinstance(status_str, str) else status_str
            return {
                "status": "ok",
                "last_maintenance": last_run,
                "details": status_data
            }
        
        return {
            "status": "no_status_data",
            "last_maintenance": last_run
        }
        
    except Exception as e:
        logger.error("status_check_failed", error=str(e))
        return {"status": "error", "error": str(e)}


class TriggerRequest(BaseModel):
    target_date: Optional[str] = None  # ISO format: "2025-12-02"
    clear_caches: bool = False  # Si True, también limpia caches


@app.post("/trigger")
async def trigger_maintenance(request: Optional[TriggerRequest] = None):
    """
    Trigger maintenance manually
    
    Args:
        target_date: Fecha específica a procesar (ISO format: "2025-12-02")
                     Si no se proporciona, usa el último día de trading
        clear_caches: Si True, también limpia caches (default: False)
                      Usar False en festivos para preservar datos visibles
    """
    try:
        target = None
        clear_caches = False
        
        if request:
            if request.target_date:
                target = date.fromisoformat(request.target_date)
            clear_caches = request.clear_caches
        
        logger.info(
            "⚡ Manual maintenance trigger requested",
            target_date=str(target) if target else "last_trading_day",
            clear_caches=clear_caches
        )
        
        if daily_scheduler:
            result = await daily_scheduler.trigger_manual(target, clear_caches=clear_caches)
            return result
        
        return {
            "status": "error",
            "message": "Scheduler not initialized"
        }
        
    except Exception as e:
        logger.error("manual_trigger_failed", error=str(e))
        return {"status": "error", "error": str(e)}


@app.post("/clear-caches")
async def clear_caches():
    """
    Limpiar caches de tiempo real manualmente
    
    Útil para forzar un refresh completo del scanner.
    """
    try:
        patterns = [
            "scanner:category:*",
            "scanner:sequence:*",
            "scanner:filtered_complete:*",
            "snapshot:enriched:*",
            "snapshot:polygon:*",
            "realtime:*",
        ]
        
        total_deleted = 0
        
        for pattern in patterns:
            try:
                deleted = await redis_client.delete_pattern(pattern)
                total_deleted += deleted
            except Exception as e:
                logger.warning(f"Failed to delete pattern {pattern}: {e}")
        
        logger.info(
            "🧹 Caches cleared manually",
            keys_deleted=total_deleted
        )
        
        return {
            "status": "ok",
            "keys_deleted": total_deleted,
            "patterns_processed": len(patterns)
        }
        
    except Exception as e:
        logger.error("clear_caches_failed", error=str(e))
        return {"status": "error", "error": str(e)}


@app.get("/next-run")
async def get_next_run():
    """Get info about next scheduled run"""
    from zoneinfo import ZoneInfo
    from datetime import timedelta
    
    now_et = datetime.now(ZoneInfo("America/New_York"))
    
    # Calcular próxima ejecución mantenimiento (3:00 AM ET)
    next_maintenance = now_et.replace(hour=3, minute=0, second=0, microsecond=0)
    if now_et.hour >= 3:
        next_maintenance += timedelta(days=1)
    
    # Calcular próxima ejecución pattern update (8:00 PM ET)
    next_pattern = now_et.replace(hour=20, minute=0, second=0, microsecond=0)
    if now_et.hour >= 20:
        next_pattern += timedelta(days=1)
    
    return {
        "current_time_et": now_et.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "maintenance": {
            "next_run_et": next_maintenance.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "time_until": str(next_maintenance - now_et).split(".")[0],
            "running": daily_scheduler.is_running if daily_scheduler else False
        },
        "pattern_matching": {
            "server": "37.27.183.194:8025",
            "note": "Runs on dedicated server with own cron at 8:00 PM ET",
            "next_run_et": next_pattern.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "time_until": str(next_pattern - now_et).split(".")[0]
        }
    }


class PatternUpdateRequest(BaseModel):
    target_date: Optional[str] = None  # ISO format: "2025-12-26"


@app.post("/trigger-pattern-update")
async def trigger_pattern_update(request: Optional[PatternUpdateRequest] = None):
    """
    Trigger pattern matching update manually
    Proxies to dedicated server at 37.27.183.194:8025
    
    Args:
        target_date: Fecha específica (ISO format: "2025-12-26")
                     Si no se proporciona, actualiza los días faltantes
    """
    import httpx
    
    PATTERN_SERVER = "http://37.27.183.194:8025"
    
    try:
        target = request.target_date if request else None
        
        logger.info(
            "Manual pattern update trigger requested (proxying to dedicated server)",
            target_date=target or "auto",
            server=PATTERN_SERVER
        )
        
        async with httpx.AsyncClient(timeout=600.0) as client:
            payload = {"date": target} if target else {}
            response = await client.post(
                f"{PATTERN_SERVER}/api/data/update-daily",
                json=payload
            )
            return response.json()
        
    except httpx.TimeoutException:
        logger.error("pattern_trigger_timeout")
        return {"status": "error", "error": "Timeout (10 min)"}
    except Exception as e:
        logger.error("manual_pattern_trigger_failed", error=str(e))
        return {"status": "error", "error": str(e)}


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8008,
        log_level="info"
    )

