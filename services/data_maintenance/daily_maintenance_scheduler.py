"""
Daily Maintenance Scheduler
===========================

Scheduler que ejecuta mantenimiento en dos fases:

FASE 1 - 1:00 AM ET: Refresh de metadata
- Actualiza shares_outstanding, market_cap, free_float de TODOS los tickers
- Captura cambios por splits, emisiones, etc.
- Sincroniza Redis y vista

FASE 2 - 3:00 AM ET: Mantenimiento principal
- SIEMPRE carga datos históricos si hay día de trading pendiente
- SOLO limpia caches si HOY es día de trading

Casos:
- Día normal (Lun-Vie): Metadata refresh → Cargar datos ayer → Limpiar caches
- Fin de semana: SKIP (no hay datos nuevos)
- Festivo después de trading: Metadata + Cargar datos + NO limpiar caches
- Día después de festivo: (datos ya cargados) + Limpiar caches
"""

import asyncio
import json
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from typing import Optional, Dict, List

import sys
sys.path.append('/app')

from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import get_logger

logger = get_logger(__name__)

NY_TZ = ZoneInfo("America/New_York")

# Festivos de FALLBACK (solo si Redis no tiene datos de Polygon)
FALLBACK_HOLIDAYS = {
    # 2024
    date(2024, 1, 1), date(2024, 1, 15), date(2024, 2, 19), date(2024, 3, 29),
    date(2024, 5, 27), date(2024, 6, 19), date(2024, 7, 4), date(2024, 9, 2),
    date(2024, 11, 28), date(2024, 12, 25),
    # 2025
    date(2025, 1, 1), date(2025, 1, 20), date(2025, 2, 17), date(2025, 4, 18),
    date(2025, 5, 26), date(2025, 6, 19), date(2025, 7, 4), date(2025, 9, 1),
    date(2025, 11, 27), date(2025, 12, 25),
    # 2026
    date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 4, 3),
    date(2026, 5, 25), date(2026, 6, 19), date(2026, 7, 3), date(2026, 9, 7),
    date(2026, 11, 26), date(2026, 12, 25),
}


class DailyMaintenanceScheduler:
    """
    Scheduler de mantenimiento diario con lógica mejorada para festivos.
    """
    
    def __init__(self, redis_client: RedisClient, timescale_client: TimescaleClient):
        self.redis = redis_client
        self.db = timescale_client
        self.is_running = False
        
        # Configuración de horarios (ET)
        self.today_bars_cleanup_hour = 0    # 00:00 AM ET - Borrar today.parquet
        self.today_bars_cleanup_minute = 0
        self.metadata_refresh_hour = 1      # 1:00 AM ET - Refresh metadata
        self.metadata_refresh_minute = 0
        self.maintenance_hour = 3           # 3:00 AM ET - Mantenimiento principal
        self.maintenance_minute = 0
        self.cache_cleanup_hour = 3         # 3:45 AM ET - Limpieza de caches
        self.cache_cleanup_minute = 45
        self.check_interval = 30            # Segundos entre checks
        
        # Estado
        self.last_today_bars_cleanup_date: Optional[date] = None  # Último cleanup de today.parquet
        self.last_metadata_refresh_date: Optional[date] = None  # Último refresh de metadata
        self.last_data_load_date: Optional[date] = None  # Último día de trading cargado
        self.last_cache_cleanup_date: Optional[date] = None
        self._holidays_cache: Dict[str, bool] = {}
    
    # =========================================================================
    # HELPERS DE CALENDARIO
    # =========================================================================
    
    async def _is_market_holiday(self, check_date: date, exchange: str = "NYSE") -> bool:
        """Verificar si es festivo (mercado cerrado)"""
        date_str = check_date.isoformat()
        cache_key = f"{date_str}:{exchange}"
        
        if cache_key in self._holidays_cache:
            return self._holidays_cache[cache_key]
        
        try:
            redis_key = f"market:holiday:{date_str}:{exchange}"
            holiday_data = await self.redis.get(redis_key)
            
            is_holiday = (
                holiday_data is not None and 
                holiday_data.get("status") == "closed"
            )
            
            self._holidays_cache[cache_key] = is_holiday
            
            if is_holiday:
                logger.info("market_holiday_detected", date=date_str, name=holiday_data.get("name"))
            
            return is_holiday
            
        except Exception as e:
            logger.warning("holiday_check_failed_using_fallback", error=str(e))
            is_holiday = check_date in FALLBACK_HOLIDAYS
            self._holidays_cache[cache_key] = is_holiday
            return is_holiday
    
    async def _is_trading_day(self, check_date: date) -> bool:
        """Verificar si es día de trading (weekday y no festivo)"""
        if check_date.weekday() >= 5:
            return False
        return not await self._is_market_holiday(check_date)
    
    def _is_trading_day_sync(self, check_date: date) -> bool:
        """Versión síncrona (usa fallback holidays)"""
        if check_date.weekday() >= 5:
            return False
        return check_date not in FALLBACK_HOLIDAYS
    
    async def _get_last_trading_day_async(self, from_date: date) -> date:
        """Obtener último día de trading (versión async)"""
        check_date = from_date - timedelta(days=1)
        for _ in range(10):
            if await self._is_trading_day(check_date):
                return check_date
            check_date -= timedelta(days=1)
        return check_date
    
    def _get_last_trading_day(self, from_date: date) -> date:
        """Obtener último día de trading (versión sync)"""
        check_date = from_date - timedelta(days=1)
        for _ in range(10):
            if self._is_trading_day_sync(check_date):
                return check_date
            check_date -= timedelta(days=1)
        return check_date
    
    # =========================================================================
    # VERIFICACIÓN DE DATOS PENDIENTES
    # =========================================================================
    
    async def _has_pending_data_load(self, target_date: date) -> bool:
        """Verificar si hay datos pendientes de cargar para una fecha"""
        status_key = f"maintenance:status:{target_date.isoformat()}"
        status_raw = await self.redis.get(status_key)
        
        if not status_raw:
            return True
        
        try:
            status = json.loads(status_raw) if isinstance(status_raw, str) else status_raw
            return not status.get("all_success", False)
        except:
            return True
    
    # =========================================================================
    # LOOP PRINCIPAL
    # =========================================================================
    
    async def run(self):
        """Loop principal del scheduler"""
        self.is_running = True
        logger.info(
            "daily_maintenance_scheduler_started", 
            metadata_refresh="1:00 AM ET",
            data_load="3:00 AM ET"
        )
        
        await self._load_state()
        
        # Recovery al iniciar
        try:
            await self._check_and_recover_missing()
        except Exception as e:
            logger.error("initial_recovery_failed", error=str(e))
        
        while self.is_running:
            try:
                await self._check_and_execute()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("scheduler_loop_error", error=str(e))
                await asyncio.sleep(60)
    
    async def _load_state(self):
        """Cargar estado desde Redis"""
        try:
            # Estado de today bars cleanup
            last_today_cleanup = await self.redis.get("maintenance:last_today_bars_cleanup")
            if last_today_cleanup:
                self.last_today_bars_cleanup_date = date.fromisoformat(last_today_cleanup)
                logger.info("loaded_last_today_bars_cleanup_date", date=str(self.last_today_bars_cleanup_date))
            
            # Estado de metadata refresh
            last_metadata = await self.redis.get("maintenance:last_metadata_refresh")
            if last_metadata:
                self.last_metadata_refresh_date = date.fromisoformat(last_metadata)
                logger.info("loaded_last_metadata_refresh_date", date=str(self.last_metadata_refresh_date))
            
            # Estado de data load
            last_data = await self.redis.get("maintenance:last_data_load")
            if last_data:
                self.last_data_load_date = date.fromisoformat(last_data)
                logger.info("loaded_last_data_load_date", date=str(self.last_data_load_date))
            
            # Estado de cache cleanup
            last_cleanup = await self.redis.get("maintenance:last_cache_cleanup")
            if last_cleanup:
                self.last_cache_cleanup_date = date.fromisoformat(last_cleanup)
        except Exception as e:
            logger.warning("failed_to_load_state", error=str(e))
    
    async def _check_and_execute(self):
        """Verificar y ejecutar tareas pendientes"""
        now_et = datetime.now(NY_TZ)
        current_date = now_et.date()
        current_hour = now_et.hour
        current_minute = now_et.minute
        
        # =============================================
        # -1. CLEANUP DE TODAY.PARQUET (00:00 AM ET)
        # Borra el archivo de minute bars de hoy para que
        # Polygon pueda descargar el flat file oficial
        # =============================================
        is_today_bars_cleanup_time = (
            current_hour == self.today_bars_cleanup_hour and
            self.today_bars_cleanup_minute <= current_minute <= self.today_bars_cleanup_minute + 5
        )
        
        if is_today_bars_cleanup_time and self.last_today_bars_cleanup_date != current_date:
            await self._execute_today_bars_cleanup(current_date)
        
        # =============================================
        # 0. REFRESH DE METADATA (1:00 AM ET)
        # Actualiza shares_outstanding, market_cap, free_float de TODOS los tickers
        # Se ejecuta ANTES del mantenimiento principal para tener datos frescos
        # =============================================
        is_metadata_refresh_time = (
            current_hour == self.metadata_refresh_hour and
            self.metadata_refresh_minute <= current_minute <= self.metadata_refresh_minute + 5
        )
        
        if is_metadata_refresh_time and self.last_metadata_refresh_date != current_date:
            # Ejecutar refresh de metadata
            await self._execute_metadata_refresh(current_date)
        
        # =============================================
        # 1. CARGA DE DATOS HISTÓRICOS (3:00 AM ET)
        # Se ejecuta SIEMPRE que haya día de trading pendiente
        # =============================================
        is_data_load_time = (
            current_hour == self.maintenance_hour and
            self.maintenance_minute <= current_minute <= self.maintenance_minute + 5
        )
        
        if is_data_load_time:
            # ¿Cuál es el último día de trading?
            last_trading_day = await self._get_last_trading_day_async(current_date)
            
            # ¿Ya cargamos esos datos?
            if self.last_data_load_date != last_trading_day:
                if await self._has_pending_data_load(last_trading_day):
                    is_today_trading = await self._is_trading_day(current_date)
                    await self._execute_data_load(last_trading_day, clear_caches=is_today_trading)
        
        # =============================================
        # 2. LIMPIEZA DE CACHES (3:45 AM ET)
        # SOLO si HOY es día de trading
        # =============================================
        is_cache_cleanup_time = (
            current_hour == self.cache_cleanup_hour and
            self.cache_cleanup_minute <= current_minute <= self.cache_cleanup_minute + 5
        )
        
        if is_cache_cleanup_time and self.last_cache_cleanup_date != current_date:
            if await self._is_trading_day(current_date):
                await self._execute_cache_cleanup(current_date)
            else:
                logger.info(
                    "skipping_cache_cleanup_not_trading_day",
                    date=str(current_date)
                )
                self.last_cache_cleanup_date = current_date
    
    # =========================================================================
    # EJECUCIÓN DE TAREAS
    # =========================================================================
    
    async def _execute_today_bars_cleanup(self, current_date: date):
        """
        Borrar today.parquet al inicio de cada día.
        
        El archivo se regenera por el Today Bars Worker durante el mercado.
        Al día siguiente, Polygon provee el flat file oficial.
        """
        logger.info("starting_today_bars_cleanup", date=str(current_date))
        
        try:
            from tasks.cleanup_today_bars import cleanup_today_bars
            
            result = await cleanup_today_bars()
            
            self.last_today_bars_cleanup_date = current_date
            await self.redis.set("maintenance:last_today_bars_cleanup", current_date.isoformat())
            
            logger.info(
                "today_bars_cleanup_completed",
                date=str(current_date),
                action=result.get("action"),
                size_mb=result.get("size_mb", 0)
            )
            
        except Exception as e:
            logger.error("today_bars_cleanup_exception", date=str(current_date), error=str(e))
    
    async def _execute_metadata_refresh(self, current_date: date):
        """
        Ejecutar refresh de toda la metadata desde Polygon.
        
        Actualiza shares_outstanding, market_cap, free_float, beta, etc.
        para TODOS los tickers activos.
        """
        logger.info("📊 starting_metadata_refresh", date=str(current_date))
        
        start_time = datetime.now()
        
        try:
            from tasks.refresh_all_metadata import RefreshAllMetadataTask
            
            task = RefreshAllMetadataTask(self.redis, self.db)
            result = await task.execute(current_date)
            
            elapsed = (datetime.now() - start_time).total_seconds()
            
            if result.get("success"):
                self.last_metadata_refresh_date = current_date
                await self.redis.set("maintenance:last_metadata_refresh", current_date.isoformat())
                
                logger.info(
                    "✅ metadata_refresh_completed",
                    date=str(current_date),
                    updated=result.get("updated", 0),
                    total=result.get("total_tickers", 0),
                    duration_seconds=round(elapsed, 2)
                )
            else:
                logger.error(
                    "❌ metadata_refresh_failed",
                    date=str(current_date),
                    error=result.get("error")
                )
                
        except Exception as e:
            logger.error("metadata_refresh_exception", date=str(current_date), error=str(e))
    
    async def _execute_data_load(self, target_date: date, clear_caches: bool = True):
        """
        Ejecutar carga de datos históricos.
        
        Args:
            target_date: Día de trading a procesar
            clear_caches: Si True, también limpia caches (solo si hoy es día de trading)
        """
        logger.info(
            "🔧 starting_data_load",
            target_date=str(target_date),
            clear_caches=clear_caches
        )
        
        start_time = datetime.now()
        
        try:
            from maintenance_orchestrator import MaintenanceOrchestrator
            
            orchestrator = MaintenanceOrchestrator(self.redis, self.db)
            success = await orchestrator.run_full_cycle(
                target_date, 
                skip_cache_clear=not clear_caches
            )
            
            elapsed = (datetime.now() - start_time).total_seconds()
            
            if success:
                self.last_data_load_date = target_date
                await self.redis.set("maintenance:last_data_load", target_date.isoformat())
                
                # Compatibilidad con código antiguo
                await self.redis.set("maintenance:last_run", datetime.now(NY_TZ).date().isoformat())
                
                logger.info(
                    "✅ data_load_completed",
                    target_date=str(target_date),
                    duration_seconds=round(elapsed, 2),
                    caches_cleared=clear_caches
                )
            else:
                logger.error("❌ data_load_failed", target_date=str(target_date))
                
        except Exception as e:
            logger.error("data_load_exception", target_date=str(target_date), error=str(e))
    
    async def _execute_cache_cleanup(self, today: date):
        """Limpiar caches del scanner (solo si hoy es día de trading)"""
        logger.info("🧹 starting_cache_cleanup", today=str(today))
        
        start_time = datetime.now()
        
        try:
            patterns = [
                "scanner:category:*",
                "scanner:sequence:*",
                "scanner:filtered_complete:*",
            ]
            
            total_deleted = 0
            for pattern in patterns:
                try:
                    deleted = await self.redis.delete_pattern(pattern)
                    total_deleted += deleted
                except Exception as e:
                    logger.warning(f"Failed to delete {pattern}: {e}")
            
            # Notificar via Pub/Sub
            await self.redis.client.publish(
                "trading:new_day",
                json.dumps({
                    "event": "cache_cleanup",
                    "date": today.isoformat(),
                    "keys_deleted": total_deleted
                })
            )
            
            self.last_cache_cleanup_date = today
            await self.redis.set("maintenance:last_cache_cleanup", today.isoformat())
            
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.info(
                "✅ cache_cleanup_completed",
                keys_deleted=total_deleted,
                duration_seconds=round(elapsed, 2)
            )
            
        except Exception as e:
            logger.error("cache_cleanup_exception", error=str(e))
    
    # =========================================================================
    # RECOVERY
    # =========================================================================
    
    async def _check_and_recover_missing(self):
        """Verificar y recuperar días faltantes al iniciar"""
        logger.info("checking_for_missing_data")
        
        now_et = datetime.now(NY_TZ)
        current_date = now_et.date()
        recovered = []
        
        # Verificar últimos 7 días de trading
        for days_ago in range(1, 8):
            check_date = current_date - timedelta(days=days_ago)
            
            if not await self._is_trading_day(check_date):
                continue
            
            if await self._has_pending_data_load(check_date):
                logger.info("⚡ recovering_missing_data", date=str(check_date))
                
                # En recovery, NO limpiar caches (preservar datos actuales)
                await self._execute_data_load(check_date, clear_caches=False)
                recovered.append(check_date)
        
        if recovered:
            logger.info("recovery_completed", dates=[str(d) for d in recovered])
        else:
            logger.info("✅ no_missing_data")
    
    # =========================================================================
    # API MANUAL
    # =========================================================================
    
    async def trigger_manual(
        self, 
        target_date: Optional[date] = None,
        clear_caches: bool = False
    ) -> Dict:
        """
        Trigger manual de carga de datos.
        
        Args:
            target_date: Fecha a procesar (default: último día de trading)
            clear_caches: Si True, también limpia caches
        """
        now_et = datetime.now(NY_TZ)
        
        if target_date is None:
            target_date = await self._get_last_trading_day_async(now_et.date())
        
        logger.info("⚡ manual_trigger", target_date=str(target_date), clear_caches=clear_caches)
        
        try:
            from maintenance_orchestrator import MaintenanceOrchestrator
            
            orchestrator = MaintenanceOrchestrator(self.redis, self.db)
            success = await orchestrator.run_full_cycle(target_date, skip_cache_clear=not clear_caches)
            
            if success:
                self.last_data_load_date = target_date
                await self.redis.set("maintenance:last_data_load", target_date.isoformat())
            
            return {
                "success": success,
                "target_date": str(target_date),
                "caches_cleared": clear_caches,
                "triggered_at": now_et.isoformat()
            }
            
        except Exception as e:
            return {"success": False, "error": str(e), "target_date": str(target_date)}
    
    def stop(self):
        """Detener el scheduler"""
        self.is_running = False
        logger.info("daily_maintenance_scheduler_stopped")
