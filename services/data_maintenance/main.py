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
7. FlatFilesWatcher: Monitorea y sincroniza flat files de Polygon (SIN afectar caches)

Arquitectura:
- DailyMaintenanceScheduler: Ejecuta el ciclo completo a las 3:00 AM ET
- MaintenanceOrchestrator: Coordina las tareas individuales
- FlatFilesWatcher: Sincroniza flat files después del cierre del mercado
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
from tasks.sync_flat_files import SyncFlatFilesTask, FlatFilesWatcher

logger = get_logger(__name__)

# Global instances
redis_client: RedisClient = None
timescale_client: TimescaleClient = None
daily_scheduler: DailyMaintenanceScheduler = None
flat_files_watcher: FlatFilesWatcher = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestión del ciclo de vida del servicio"""
    global redis_client, timescale_client, daily_scheduler, flat_files_watcher
    
    logger.info("🚀 Starting Data Maintenance Service v2.1")
    
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
    
    # Iniciar FlatFilesWatcher (monitorea flat files de Polygon después del cierre)
    # Recibe daily_scheduler para usar su lógica de holidays (sin duplicar)
    flat_files_watcher = FlatFilesWatcher(redis_client, daily_scheduler)
    watcher_task = asyncio.create_task(flat_files_watcher.run())
    
    logger.info("=" * 60)
    logger.info("📅 Schedule: Daily maintenance at 3:00 AM ET")
    logger.info("   (1 hour before pre-market opens at 4:00 AM ET)")
    logger.info("📁 FlatFilesWatcher: Monitors Polygon S3 every 30min after close")
    logger.info("📊 Pattern Matching: Dedicated server 37.27.183.194:8025")
    logger.info("=" * 60)
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down Data Maintenance Service")
    
    # Detener FlatFilesWatcher
    flat_files_watcher.stop()
    watcher_task.cancel()
    
    await realtime_monitor.stop()
    monitor_task.cancel()
    
    daily_scheduler.stop()
    scheduler_task.cancel()
    
    try:
        await watcher_task
    except asyncio.CancelledError:
        pass
    
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
    
    return {
        "current_time_et": now_et.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "maintenance": {
            "next_run_et": next_maintenance.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "time_until": str(next_maintenance - now_et).split(".")[0],
            "running": daily_scheduler.is_running if daily_scheduler else False
        },
        "flat_files_watcher": {
            "running": flat_files_watcher.is_running if flat_files_watcher else False,
            "check_interval": "30 minutes",
            "active_hours": "5 PM - 9 AM ET (after market close)",
            "note": "Monitors Polygon S3 and syncs flat files + Pattern Matching automatically"
        },
        "pattern_matching": {
            "server": "37.27.183.194:8025",
            "note": "Managed by FlatFilesWatcher (no separate cron needed)"
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


# =============================================================================
# FLAT FILES ENDPOINTS (SIN AFECTAR CACHES)
# =============================================================================

class FlatFilesSyncRequest(BaseModel):
    target_date: Optional[str] = None  # ISO format: "2026-01-02"


@app.get("/flat-files/status")
async def get_flat_files_status():
    """
    Ver estado de los flat files.
    
    Muestra:
    - Último día de trading
    - Si el flat file está disponible en Polygon
    - Si ya lo tenemos descargado
    - Estado del Pattern Matching
    
    NOTA: Este endpoint NO modifica nada, solo consulta.
    USA daily_scheduler para lógica de holidays (sin duplicar).
    """
    from zoneinfo import ZoneInfo
    
    try:
        sync_task = SyncFlatFilesTask()
        now_et = datetime.now(ZoneInfo("America/New_York"))
        today = now_et.date()
        
        # Usar daily_scheduler para obtener último día de trading (sin duplicar holidays)
        last_trading = await daily_scheduler._get_last_trading_day_async(today)
        
        # Verificar si existe en Polygon
        minute_exists = await sync_task.check_file_exists_in_polygon(last_trading, "minute_aggs")
        day_exists = await sync_task.check_file_exists_in_polygon(last_trading, "day_aggs")
        
        # Verificar estado de Pattern Matching
        pm_status = await sync_task.get_pattern_matching_status()
        
        # Verificar si ya sincronizamos
        sync_key = f"flat_files:synced:{last_trading.isoformat()}"
        already_synced = await redis_client.get(sync_key) is not None
        
        return {
            "current_time_et": now_et.strftime("%Y-%m-%d %H:%M:%S"),
            "last_trading_day": last_trading.isoformat(),
            "polygon_s3": {
                "minute_aggs_available": minute_exists,
                "day_aggs_available": day_exists
            },
            "pattern_matching": {
                "server": "37.27.183.194:8025",
                "newest_flat_file": pm_status.get("newest_flat_file"),
                "total_files": pm_status.get("total_files"),
                "needs_update": pm_status.get("newest_flat_file") != last_trading.isoformat() if pm_status.get("newest_flat_file") else True
            },
            "sync_status": {
                "already_synced_today": already_synced,
                "watcher_running": flat_files_watcher.is_running if flat_files_watcher else False
            }
        }
        
    except Exception as e:
        logger.error("flat_files_status_failed", error=str(e))
        return {"status": "error", "error": str(e)}


@app.post("/flat-files/sync")
async def sync_flat_files(request: Optional[FlatFilesSyncRequest] = None):
    """
    Sincronizar flat files de Polygon MANUALMENTE.
    
    IMPORTANTE: Esta operación:
    - NO limpia caches
    - NO afecta datos del usuario
    - Solo descarga flat files y actualiza Pattern Matching
    
    Puede ejecutarse en cualquier momento (incluso fines de semana)
    sin afectar la experiencia del usuario.
    
    USA daily_scheduler para lógica de holidays (sin duplicar).
    
    Args:
        target_date: Fecha específica (ISO format: "2026-01-02")
                     Si no se proporciona, usa el último día de trading
    """
    from zoneinfo import ZoneInfo
    
    try:
        sync_task = SyncFlatFilesTask()
        
        if request and request.target_date:
            target = date.fromisoformat(request.target_date)
        else:
            # Usar daily_scheduler para obtener último día de trading (sin duplicar holidays)
            now_et = datetime.now(ZoneInfo("America/New_York"))
            target = await daily_scheduler._get_last_trading_day_async(now_et.date())
        
        logger.info(
            "📁 Manual flat files sync requested",
            target_date=target.isoformat()
        )
        
        result = await sync_task.sync_for_date(target)
        
        # Si fue exitoso, marcar como sincronizado
        if result.get("success"):
            sync_key = f"flat_files:synced:{target.isoformat()}"
            await redis_client.set(sync_key, "1", ttl=86400 * 7)
        
        return result
        
    except Exception as e:
        logger.error("flat_files_sync_failed", error=str(e))
        return {"status": "error", "error": str(e)}


@app.get("/flat-files/check-polygon")
async def check_polygon_availability():
    """
    Verificar qué archivos están disponibles en Polygon S3.
    
    Útil para debugging y verificar si Polygon ya liberó los archivos.
    
    NOTA: Este endpoint NO modifica nada, solo consulta Polygon S3.
    """
    from datetime import timedelta
    from zoneinfo import ZoneInfo
    
    try:
        sync_task = SyncFlatFilesTask()
        now_et = datetime.now(ZoneInfo("America/New_York"))
        today = now_et.date()
        
        results = {}
        
        # Verificar últimos 5 días
        for i in range(1, 6):
            check_date = today - timedelta(days=i)
            date_str = check_date.isoformat()
            
            minute_exists = await sync_task.check_file_exists_in_polygon(check_date, "minute_aggs")
            day_exists = await sync_task.check_file_exists_in_polygon(check_date, "day_aggs")
            
            results[date_str] = {
                "weekday": check_date.strftime("%A"),
                "minute_aggs": minute_exists,
                "day_aggs": day_exists
            }
        
        return {
            "checked_at": now_et.isoformat(),
            "dates": results
        }
        
    except Exception as e:
        logger.error("check_polygon_failed", error=str(e))
        return {"status": "error", "error": str(e)}


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8008,
        log_level="info"
    )

