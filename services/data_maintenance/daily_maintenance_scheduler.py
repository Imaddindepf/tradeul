"""
Daily Maintenance Scheduler
===========================

Scheduler ÚNICO que ejecuta todo el mantenimiento a las 3:00 AM ET (1h antes del pre-market).

Flujo completo:
1. Verificar si es día de trading
2. Limpiar caches de tiempo real (scanner, websocket, snapshots)
3. Cargar datos del DÍA ANTERIOR (OHLC, volume_slots)
4. Calcular indicadores (ATR, RVOL)
5. Enriquecer metadata
6. Sincronizar Redis
7. Publicar evento "new_trading_day"

IMPORTANTE:
- Se ejecuta a las 3:00 AM ET, NO a las 17:00 ET
- Siempre carga datos del DÍA ANTERIOR (el día de trading que acaba de terminar)
- En fines de semana/festivos: NO ejecuta
"""

import asyncio
import json
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
from typing import Optional, Dict, List

import sys
sys.path.append('/app')

from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import get_logger

logger = get_logger(__name__)

# Timezone de Nueva York
NY_TZ = ZoneInfo("America/New_York")

# Festivos 2024-2025 (mercado cerrado)
MARKET_HOLIDAYS = {
    # 2024
    date(2024, 1, 1), date(2024, 1, 15), date(2024, 2, 19), date(2024, 3, 29),
    date(2024, 5, 27), date(2024, 6, 19), date(2024, 7, 4), date(2024, 9, 2),
    date(2024, 11, 28), date(2024, 12, 25),
    # 2025
    date(2025, 1, 1), date(2025, 1, 20), date(2025, 2, 17), date(2025, 4, 18),
    date(2025, 5, 26), date(2025, 6, 19), date(2025, 7, 4), date(2025, 9, 1),
    date(2025, 11, 27), date(2025, 12, 25),
}


class DailyMaintenanceScheduler:
    """
    Scheduler que ejecuta mantenimiento diario a las 3:00 AM ET
    """
    
    def __init__(self, redis_client: RedisClient, timescale_client: TimescaleClient):
        self.redis = redis_client
        self.db = timescale_client
        self.is_running = False
        
        # Configuración
        self.maintenance_hour = 3   # 3:00 AM ET
        self.maintenance_minute = 0
        self.check_interval = 30    # Verificar cada 30 segundos
        
        # Estado
        self.last_maintenance_date: Optional[date] = None
        
    def _is_trading_day(self, check_date: date) -> bool:
        """
        Verificar si una fecha es día de trading
        
        Returns:
            True si es día de trading (weekday y no festivo)
        """
        # Fin de semana
        if check_date.weekday() >= 5:
            return False
        
        # Festivo
        if check_date in MARKET_HOLIDAYS:
            return False
        
        return True
    
    def _get_last_trading_day(self, from_date: date) -> date:
        """
        Obtener el último día de trading antes de una fecha dada
        
        Args:
            from_date: Fecha desde la cual buscar hacia atrás
            
        Returns:
            El día de trading más reciente
        """
        check_date = from_date - timedelta(days=1)
        
        # Buscar hacia atrás hasta encontrar un día de trading
        while not self._is_trading_day(check_date):
            check_date -= timedelta(days=1)
            
            # Límite de seguridad (máximo 10 días atrás)
            if (from_date - check_date).days > 10:
                logger.warning("get_last_trading_day_exceeded_limit", from_date=str(from_date))
                break
        
        return check_date
    
    async def run(self):
        """Loop principal del scheduler"""
        self.is_running = True
        logger.info(
            "daily_maintenance_scheduler_started",
            schedule="3:00 AM ET daily",
            check_interval_seconds=self.check_interval
        )
        
        # Verificar estado inicial
        await self._load_last_maintenance_date()
        
        while self.is_running:
            try:
                await self._check_and_execute()
                await asyncio.sleep(self.check_interval)
                
            except asyncio.CancelledError:
                logger.info("daily_maintenance_scheduler_cancelled")
                raise
                
            except Exception as e:
                logger.error(
                    "scheduler_loop_error",
                    error=str(e),
                    error_type=type(e).__name__
                )
                await asyncio.sleep(60)
    
    async def _load_last_maintenance_date(self):
        """Cargar la última fecha de mantenimiento desde Redis"""
        try:
            last_run = await self.redis.get("maintenance:last_run")
            if last_run:
                self.last_maintenance_date = date.fromisoformat(last_run)
                logger.info(
                    "loaded_last_maintenance_date",
                    date=str(self.last_maintenance_date)
                )
        except Exception as e:
            logger.warning("failed_to_load_last_maintenance_date", error=str(e))
    
    async def _check_and_execute(self):
        """Verificar si es momento de ejecutar mantenimiento"""
        now_et = datetime.now(NY_TZ)
        current_date = now_et.date()
        current_hour = now_et.hour
        current_minute = now_et.minute
        
        # ¿Es la hora de mantenimiento? (3:00 AM con ventana de 1 minuto)
        is_maintenance_time = (
            current_hour == self.maintenance_hour and
            current_minute == self.maintenance_minute
        )
        
        if not is_maintenance_time:
            return
        
        # ¿Ya se ejecutó hoy?
        if self.last_maintenance_date == current_date:
            return
        
        # ¿Es día de trading?
        if not self._is_trading_day(current_date):
            logger.info(
                "skipping_maintenance_not_trading_day",
                date=str(current_date),
                weekday=current_date.strftime("%A")
            )
            self.last_maintenance_date = current_date
            await self.redis.set("maintenance:last_run", current_date.isoformat())
            return
        
        # Ejecutar mantenimiento
        logger.info(
            "🚀 maintenance_time_reached",
            current_time=now_et.strftime("%H:%M:%S %Z"),
            date=str(current_date)
        )
        
        await self._execute_daily_maintenance(current_date)
    
    async def _execute_daily_maintenance(self, today: date):
        """
        Ejecutar el ciclo completo de mantenimiento diario
        
        Args:
            today: Fecha actual (el día que está por empezar)
        """
        # El día de trading a procesar es el ANTERIOR
        target_date = self._get_last_trading_day(today)
        
        logger.info(
            "🔧 starting_daily_maintenance",
            today=str(today),
            target_date=str(target_date),
            reason="Processing yesterday's trading data"
        )
        
        start_time = datetime.now()
        
        try:
            # Importar orchestrator aquí para evitar circular imports
            from maintenance_orchestrator import MaintenanceOrchestrator
            
            orchestrator = MaintenanceOrchestrator(self.redis, self.db)
            success = await orchestrator.run_full_cycle(target_date)
            
            elapsed = (datetime.now() - start_time).total_seconds()
            
            if success:
                self.last_maintenance_date = today
                await self.redis.set("maintenance:last_run", today.isoformat())
                
                logger.info(
                    "✅ daily_maintenance_completed",
                    target_date=str(target_date),
                    duration_seconds=round(elapsed, 2)
                )
            else:
                logger.error(
                    "❌ daily_maintenance_failed",
                    target_date=str(target_date),
                    duration_seconds=round(elapsed, 2)
                )
                
        except Exception as e:
            logger.error(
                "daily_maintenance_exception",
                target_date=str(target_date),
                error=str(e),
                error_type=type(e).__name__
            )
    
    async def trigger_manual(self, target_date: Optional[date] = None) -> Dict:
        """
        Trigger manual de mantenimiento (para testing o recuperación)
        
        Args:
            target_date: Fecha específica a procesar (default: último día de trading)
        """
        now_et = datetime.now(NY_TZ)
        
        if target_date is None:
            target_date = self._get_last_trading_day(now_et.date())
        
        logger.info(
            "⚡ manual_maintenance_triggered",
            target_date=str(target_date)
        )
        
        try:
            from maintenance_orchestrator import MaintenanceOrchestrator
            
            orchestrator = MaintenanceOrchestrator(self.redis, self.db)
            success = await orchestrator.run_full_cycle(target_date)
            
            return {
                "success": success,
                "target_date": str(target_date),
                "triggered_at": now_et.isoformat()
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "target_date": str(target_date)
            }
    
    def stop(self):
        """Detener el scheduler"""
        self.is_running = False
        logger.info("daily_maintenance_scheduler_stopped")

