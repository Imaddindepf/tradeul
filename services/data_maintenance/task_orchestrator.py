"""
Task Orchestrator
Coordina la ejecución de todas las tareas de mantenimiento con tolerancia a fallos
"""

import asyncio
import json
from datetime import datetime, date
from typing import Dict, List, Optional
from enum import Enum

import sys
sys.path.append('/app')

from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import get_logger

from tasks.load_ohlc import LoadOHLCTask
from tasks.load_volume_slots import LoadVolumeSlotsTask
from tasks.calculate_atr import CalculateATRTask
from tasks.calculate_rvol_averages import CalculateRVOLHistoricalAveragesTask
from tasks.enrich_metadata import EnrichMetadataTask
from tasks.auto_recover_missing_tickers import AutoRecoverMissingTickersTask
from tasks.sync_redis import SyncRedisTask

logger = get_logger(__name__)


class TaskStatus(str, Enum):
    """Estados de las tareas"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class TaskOrchestrator:
    """
    Orchestrador de tareas de mantenimiento
    
    Características:
    - Ejecuta tareas en orden secuencial
    - Rastrea estado en Redis para tolerancia a fallos
    - Reanuda desde la última tarea completada
    - Reporta progreso y estadísticas
    """
    
    def __init__(self, redis_client: RedisClient, timescale_client: TimescaleClient):
        self.redis = redis_client
        self.db = timescale_client
        
        # Definir tareas en orden de ejecución
        self.tasks = [
            LoadOHLCTask(redis_client, timescale_client),
            LoadVolumeSlotsTask(redis_client, timescale_client),
            CalculateATRTask(redis_client, timescale_client),  # Calcular ATR después de cargar OHLC
            CalculateRVOLHistoricalAveragesTask(redis_client, timescale_client),  # Calcular promedios RVOL después de cargar volume_slots
            EnrichMetadataTask(redis_client, timescale_client),
            AutoRecoverMissingTickersTask(redis_client, timescale_client),  # Auto-detectar y agregar tickers nuevos
            SyncRedisTask(redis_client, timescale_client),
        ]
    
    async def run_maintenance_cycle(self, target_date: Optional[date] = None) -> bool:
        """
        Ejecutar ciclo completo de mantenimiento
        
        Args:
            target_date: Fecha para la cual ejecutar mantenimiento (default: today if after market close)
        
        Returns:
            True si todas las tareas se completaron exitosamente
        """
        if target_date is None:
            from datetime import timedelta
            from zoneinfo import ZoneInfo
            
            # Obtener hora actual en Eastern Time
            now_et = datetime.now(ZoneInfo("America/New_York"))
            current_hour = now_et.hour
            
            # Si ejecuta después del cierre (16:00+), usar fecha ACTUAL
            # El mercado de HOY ya cerró, entonces cargamos datos de HOY
            if current_hour >= 16:
                target_date = now_et.date()
            else:
                # Si ejecuta de madrugada (antes de market open), usar día anterior
                target_date = now_et.date() - timedelta(days=1)
        
        date_str = target_date.isoformat()
        
        # 🔥 VERIFICAR SI YA SE COMPLETÓ HOY (CON TODAS LAS TAREAS EXITOSAS)
        status_key = f"maintenance:status:{date_str}"
        existing_state_raw = await self.redis.get(status_key)
        
        if existing_state_raw:
            import json
            try:
                existing_state = json.loads(existing_state_raw) if isinstance(existing_state_raw, str) else existing_state_raw
                
                # Verificar si todas las tareas están completadas Y el ciclo fue exitoso
                tasks_status = existing_state.get("tasks", {})
                all_completed = all(
                    tasks_status.get(task.name) == TaskStatus.COMPLETED
                    for task in self.tasks
                )
                all_success = existing_state.get("all_success", False)
                completed_at = existing_state.get("completed_at")
                
                # Solo saltarse si TODAS las tareas completaron Y todas fueron exitosas
                if all_completed and all_success and completed_at:
                    logger.info(
                        "maintenance_already_completed",
                        date=date_str,
                        completed_at=completed_at,
                        all_success=all_success
                    )
                    return True
                else:
                    # Si hay estado pero no completó exitosamente, re-intentar
                    logger.warning(
                        "maintenance_incomplete_or_failed",
                        date=date_str,
                        all_completed=all_completed,
                        all_success=all_success,
                        action="re_executing"
                    )
            except (json.JSONDecodeError, AttributeError) as e:
                logger.warning("failed_to_parse_existing_state", error=str(e))
        
        logger.info(
            "starting_maintenance_cycle",
            date=date_str,
            tasks_count=len(self.tasks)
        )
        
        # Inicializar o recuperar estado
        state = await self._load_state(status_key, target_date)
        
        cycle_start = datetime.now()
        all_success = True
        
        # Ejecutar cada tarea
        for task in self.tasks:
            task_name = task.name
            
            # Verificar si ya está completada
            if state["tasks"].get(task_name) == TaskStatus.COMPLETED:
                logger.info(
                    "task_already_completed",
                    task=task_name,
                    date=date_str
                )
                continue
            
            # Marcar como en progreso
            state["tasks"][task_name] = TaskStatus.IN_PROGRESS
            await self._save_state(status_key, state)
            
            logger.info(
                "task_starting",
                task=task_name,
                date=date_str
            )
            
            task_start = datetime.now()
            
            try:
                # Ejecutar tarea
                result = await task.execute(target_date)
                
                task_duration = (datetime.now() - task_start).total_seconds()
                
                if result.get("success", False):
                    # 🔥 VALIDACIÓN ADICIONAL: Verificar que tenga datos significativos
                    validation_passed = self._validate_task_result(task_name, result)
                    
                    if validation_passed:
                        state["tasks"][task_name] = TaskStatus.COMPLETED
                        
                        # Excluir duration_seconds de result para evitar duplicados
                        log_data = {k: v for k, v in result.items() if k != "duration_seconds"}
                        
                        logger.info(
                            "task_completed",
                            task=task_name,
                            duration_seconds=round(task_duration, 2),
                            **log_data
                        )
                    else:
                        # Validación falló - marcar como FAILED
                        state["tasks"][task_name] = TaskStatus.FAILED
                        all_success = False
                        logger.error(
                            "task_validation_failed",
                            task=task_name,
                            reason="Insufficient data loaded",
                            duration_seconds=round(task_duration, 2),
                            **result
                        )
                else:
                    state["tasks"][task_name] = TaskStatus.FAILED
                    all_success = False
                    logger.error(
                        "task_failed",
                        task=task_name,
                        error=result.get("error"),
                        duration_seconds=round(task_duration, 2)
                    )
                    
                    # Continuar con las demás tareas aunque falle una
            
            except Exception as e:
                state["tasks"][task_name] = TaskStatus.FAILED
                all_success = False
                logger.error(
                    "task_exception",
                    task=task_name,
                    error=str(e),
                    error_type=type(e).__name__
                )
            
            # Guardar estado después de cada tarea
            await self._save_state(status_key, state)
        
        # Marcar ciclo como completado
        cycle_duration = (datetime.now() - cycle_start).total_seconds()
        state["completed_at"] = datetime.now().isoformat()
        state["duration_seconds"] = round(cycle_duration, 2)
        state["all_success"] = all_success
        
        await self._save_state(status_key, state)
        
        # Actualizar last_run
        await self.redis.set("maintenance:last_run", date_str)
        
        # Log final
        completed_count = sum(
            1 for status in state["tasks"].values() 
            if status == TaskStatus.COMPLETED
        )
        failed_count = sum(
            1 for status in state["tasks"].values() 
            if status == TaskStatus.FAILED
        )
        
        logger.info(
            "maintenance_cycle_finished",
            date=date_str,
            duration_seconds=round(cycle_duration, 2),
            duration_human=self._format_duration(cycle_duration),
            completed=completed_count,
            failed=failed_count,
            total=len(self.tasks),
            success=all_success
        )
        
        return all_success
    
    async def _load_state(self, status_key: str, target_date: date) -> Dict:
        """Cargar o inicializar estado de mantenimiento"""
        try:
            state_json = await self.redis.get(status_key)
            
            if state_json:
                state = json.loads(state_json)
                logger.info(
                    "state_recovered",
                    date=target_date.isoformat(),
                    tasks=state.get("tasks", {})
                )
                return state
        
        except Exception as e:
            logger.warning(
                "state_load_failed",
                error=str(e)
            )
        
        # Inicializar estado nuevo
        state = {
            "date": target_date.isoformat(),
            "started_at": datetime.now().isoformat(),
            "completed_at": None,
            "duration_seconds": None,
            "all_success": None,
            "tasks": {
                task.name: TaskStatus.PENDING
                for task in self.tasks
            }
        }
        
        logger.info(
            "state_initialized",
            date=target_date.isoformat()
        )
        
        return state
    
    async def _save_state(self, status_key: str, state: Dict):
        """Guardar estado en Redis"""
        try:
            state_json = json.dumps(state)
            await self.redis.set(status_key, state_json, ttl=86400 * 7)  # 7 días
        
        except Exception as e:
            logger.error(
                "state_save_failed",
                error=str(e)
            )
    
    def _validate_task_result(self, task_name: str, result: Dict) -> bool:
        """
        🔥 VALIDACIÓN: Verificar que la tarea cargó suficientes datos
        """
        # Si no cargó nada porque todo ya estaba completo, es OK
        days_skipped = result.get("days_skipped", 0)
        days_loaded = result.get("days_loaded", 0)
        
        if days_loaded == 0 and days_skipped > 0:
            return True  # No había nada que cargar
        
        # Validaciones por tipo de tarea
        records = result.get("records_inserted", 0)
        symbols_success = result.get("symbols_success", 0)
        
        if task_name == "ohlc_daily":
            MIN_OHLC = 10000
            if days_loaded > 0 and records < MIN_OHLC:
                logger.warning("ohlc_validation_failed", expected=MIN_OHLC, actual=records)
                return False
        
        elif task_name == "volume_slots":
            MIN_SLOTS = 500000
            if days_loaded > 0 and records < MIN_SLOTS:
                logger.warning("volume_slots_validation_failed", expected=MIN_SLOTS, actual=records)
                return False
        
        elif task_name == "calculate_atr":
            MIN_ATR = 10000
            if symbols_success < MIN_ATR:
                logger.warning("atr_validation_failed", expected=MIN_ATR, actual=symbols_success)
                return False
        
        return True
    
    def _format_duration(self, seconds: float) -> str:
        """Formatear duración en formato legible"""
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            minutes = seconds / 60
            return f"{minutes:.1f}m"
        else:
            hours = seconds / 3600
            return f"{hours:.1f}h"

