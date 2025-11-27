"""
Cache Clear Scheduler
Limpia caches a las 3:00 AM (1h antes del pre-market)

IMPORTANTE: Verifica si es día de trading antes de limpiar.
En días festivos NO limpia caches para mantener datos del último día de trading.
"""

import asyncio
from datetime import datetime, time, date
from zoneinfo import ZoneInfo

import sys
sys.path.append('/app')

from shared.config.settings import settings
from shared.utils.redis_client import RedisClient
from shared.utils.logger import get_logger
from shared.events import EventBus
from tasks.clear_realtime_caches import ClearRealtimeCachesTask

logger = get_logger(__name__)


class CacheClearScheduler:
    """
    Scheduler que ejecuta limpieza de caches a las 3:00 AM EST
    
    NOTA: Verifica estado del mercado antes de limpiar.
    En días festivos, NO limpia caches.
    """
    
    def __init__(self, redis_client: RedisClient):
        self.redis = redis_client
        self.event_bus = EventBus(redis_client, "data_maintenance")
        self.clear_task = ClearRealtimeCachesTask(redis_client)
        self.is_running = False
        self.last_clear_date = None
    
    async def _is_trading_day(self, check_date: date) -> bool:
        """
        Verifica si una fecha es día de trading (no festivo, no fin de semana)
        Lee el estado desde Redis (cacheado por market_session)
        """
        # Verificar fin de semana
        if check_date.weekday() >= 5:
            return False
        
        # Verificar festivo en Redis
        try:
            date_str = check_date.strftime('%Y-%m-%d')
            
            for exchange in ["NYSE", "NASDAQ"]:
                key = f"{settings.key_prefix_market}:holiday:{date_str}:{exchange}"
                holiday_data = await self.redis.get(key)
                
                if holiday_data and holiday_data.get("status") == "closed":
                    return False
            
            return True
        
        except Exception as e:
            logger.error("error_checking_trading_day", error=str(e))
            # En caso de error, asumir día normal (mejor limpiar que no)
            return True
    
    async def start(self):
        """Iniciar scheduler"""
        self.is_running = True
        logger.info("cache_clear_scheduler_started", trigger_time="03:00 EST")
        
        # Crear tarea en background
        asyncio.create_task(self._schedule_loop())
        
        logger.info(
            "cache_clear_scheduler_ready",
            note="Will clear caches 1 hour before pre-market (3:00 AM EST)"
        )
    
    async def stop(self):
        """Detener scheduler"""
        self.is_running = False
        logger.info("cache_clear_scheduler_stopped")
    
    async def _schedule_loop(self):
        """
        Loop principal: verifica cada minuto si es hora de limpiar caches
        """
        logger.info("cache_clear_schedule_loop_started")
        
        while self.is_running:
            try:
                # Obtener hora actual en Eastern Time
                now_et = datetime.now(ZoneInfo("America/New_York"))
                current_time = now_et.time()
                current_date = now_et.date()
                
                # Verificar si es 3:00 AM (con ventana de 1 minuto)
                target_time = time(3, 0)  # 3:00 AM
                
                is_clear_time = (
                    current_time.hour == target_time.hour and
                    current_time.minute == target_time.minute
                )
                
                # Solo ejecutar una vez por día
                if is_clear_time and self.last_clear_date != current_date:
                    logger.info(
                        "cache_clear_time_detected",
                        time="03:00 AM EST",
                        date=str(current_date)
                    )
                    
                    # 🚨 VERIFICAR SI ES DÍA DE TRADING
                    is_trading = await self._is_trading_day(current_date)
                    
                    if not is_trading:
                        logger.info(
                            "⏭️ skipping_cache_clear_holiday",
                            date=str(current_date),
                            reason="Not a trading day (holiday or weekend)"
                        )
                        self.last_clear_date = current_date  # Marcar como procesado
                        continue
                    
                    try:
                        # Ejecutar limpieza de caches
                        result = await self.clear_task.execute(current_date)
                        
                        if result.get("success"):
                            self.last_clear_date = current_date
                            logger.info(
                                "cache_clear_executed_successfully",
                                date=str(current_date),
                                services_notified=len(result.get("services_notified", [])),
                                caches_cleared=len(result.get("caches_cleared", []))
                            )
                        else:
                            logger.error(
                                "cache_clear_failed",
                                date=str(current_date),
                                errors=result.get("errors", [])
                            )
                    
                    except Exception as e:
                        logger.error(
                            "cache_clear_execution_error",
                            date=str(current_date),
                            error=str(e)
                        )
                
                # Verificar cada 30 segundos
                await asyncio.sleep(30)
            
            except asyncio.CancelledError:
                logger.info("cache_clear_schedule_loop_cancelled")
                break
            except Exception as e:
                logger.error("cache_clear_schedule_loop_error", error=str(e))
                await asyncio.sleep(60)  # Esperar más en caso de error
    
    async def force_clear_now(self):
        """
        Forzar limpieza inmediata (para testing)
        """
        now_et = datetime.now(ZoneInfo("America/New_York"))
        current_date = now_et.date()
        
        logger.info("force_cache_clear_requested", date=str(current_date))
        
        try:
            result = await self.clear_task.execute(current_date)
            
            if result.get("success"):
                self.last_clear_date = current_date
                logger.info(
                    "force_cache_clear_completed",
                    date=str(current_date)
                )
                return result
            else:
                logger.error(
                    "force_cache_clear_failed",
                    errors=result.get("errors", [])
                )
                return result
        
        except Exception as e:
            logger.error("force_cache_clear_error", error=str(e))
            return {
                "success": False,
                "error": str(e)
            }

