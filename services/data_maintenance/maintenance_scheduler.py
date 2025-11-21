"""
Maintenance Scheduler
Monitorea el estado del mercado y ejecuta mantenimiento cuando cierra
"""

import asyncio
from datetime import datetime, time, date
from zoneinfo import ZoneInfo

import sys
sys.path.append('/app')

from shared.enums.market_session import MarketSession
from shared.utils.logger import get_logger
from task_orchestrator import TaskOrchestrator

logger = get_logger(__name__)


class MaintenanceScheduler:
    """
    Scheduler que monitorea el mercado y ejecuta mantenimiento
    
    Lógica:
    1. Monitorear estado del mercado cada minuto
    2. Detectar transición: MARKET_OPEN → POST_MARKET → CLOSED
    3. Esperar 1 hora después del cierre (17:00 ET)
    4. Ejecutar ciclo de mantenimiento
    5. Marcar como completado para ese día
    """
    
    def __init__(self, orchestrator: TaskOrchestrator):
        self.orchestrator = orchestrator
        self.timezone = ZoneInfo("America/New_York")
        self.is_running = False
        
        # Configuración
        self.check_interval = 60  # Revisar cada 60 segundos
        self.maintenance_hour = 17  # 5:00 PM ET (1h después del cierre)
        self.maintenance_minute = 0
        
        # Estado
        self.last_session = None
        self.maintenance_run_today = False
    
    async def run(self):
        """Loop principal del scheduler"""
        self.is_running = True
        logger.info("maintenance_scheduler_started")
        
        while True:
            try:
                await self._check_and_execute()
                await asyncio.sleep(self.check_interval)
            
            except asyncio.CancelledError:
                logger.info("maintenance_scheduler_cancelled")
                raise
            
            except Exception as e:
                logger.error(
                    "scheduler_error",
                    error=str(e),
                    error_type=type(e).__name__
                )
                await asyncio.sleep(60)  # Esperar 1 minuto antes de reintentar
    
    async def _check_and_execute(self):
        """Verificar si es momento de ejecutar mantenimiento"""
        now_et = datetime.now(self.timezone)
        current_date = now_et.date()
        current_hour = now_et.hour
        current_minute = now_et.minute
        
        # Determinar sesión actual
        current_session = MarketSession.from_time_et(current_hour, current_minute)
        
        # Detectar cambio de día (resetear flag)
        if not hasattr(self, '_last_check_date') or self._last_check_date != current_date:
            self._last_check_date = current_date
            self.maintenance_run_today = False
            logger.info(
                "new_trading_day",
                date=current_date.isoformat(),
                maintenance_pending=True
            )
        
        # Log cambio de sesión
        if self.last_session != current_session:
            logger.info(
                "market_session_changed",
                from_session=self.last_session.value if self.last_session else "INIT",
                to_session=current_session.value,
                time=now_et.strftime("%H:%M:%S %Z")
            )
            self.last_session = current_session
        
        # Condiciones para ejecutar mantenimiento:
        # 1. No se ha ejecutado hoy
        # 2. Es la hora configurada (17:00 ET por defecto)
        # 3. Es día de semana (lunes a viernes)
        
        is_weekday = current_date.weekday() < 5  # 0=Monday, 4=Friday
        is_maintenance_time = (
            current_hour == self.maintenance_hour and 
            current_minute <= 5  # Ventana de 5 minutos
        )
        
        if not self.maintenance_run_today and is_weekday and is_maintenance_time:
            logger.info(
                "maintenance_time_reached",
                date=current_date.isoformat(),
                time=now_et.strftime("%H:%M:%S %Z"),
                session=current_session.value
            )
            
            # Ejecutar mantenimiento
            await self._execute_maintenance(current_date)
    
    async def _execute_maintenance(self, date):
        """Ejecutar ciclo de mantenimiento completo"""
        logger.info(
            "🚀 starting_maintenance_cycle",
            date=date.isoformat()
        )
        
        try:
            # Ejecutar orchestrator
            success = await self.orchestrator.run_maintenance_cycle(date)
            
            if success:
                logger.info(
                    "✅ maintenance_cycle_completed",
                    date=date.isoformat()
                )
                self.maintenance_run_today = True
            else:
                logger.error(
                    "❌ maintenance_cycle_failed",
                    date=date.isoformat()
                )
        
        except Exception as e:
            logger.error(
                "maintenance_execution_error",
                date=date.isoformat(),
                error=str(e),
                error_type=type(e).__name__
            )
    
    def get_next_maintenance_time(self) -> datetime:
        """Calcular próxima ejecución de mantenimiento"""
        now_et = datetime.now(self.timezone)
        next_time = now_et.replace(
            hour=self.maintenance_hour,
            minute=self.maintenance_minute,
            second=0,
            microsecond=0
        )
        
        # Si ya pasó hoy, programar para mañana
        if now_et >= next_time:
            from datetime import timedelta
            next_time += timedelta(days=1)
        
        return next_time

