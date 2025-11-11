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
from tasks.enrich_metadata import EnrichMetadataTask
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
            CalculateATRTask(redis_client, timescale_client),  # ← NUEVA: Calcular ATR después de cargar OHLC
            EnrichMetadataTask(redis_client, timescale_client),
            SyncRedisTask(redis_client, timescale_client),
        ]
    
    async def run_maintenance_cycle(self, target_date: Optional[date] = None) -> bool:
        """
        Ejecutar ciclo completo de mantenimiento
        
        Args:
            target_date: Fecha para la cual ejecutar mantenimiento (default: yesterday)
        
        Returns:
            True si todas las tareas se completaron exitosamente
        """
        if target_date is None:
            from datetime import timedelta
            target_date = (datetime.now().date() - timedelta(days=1))
        
        date_str = target_date.isoformat()
        
        logger.info(
            "starting_maintenance_cycle",
            date=date_str,
            tasks_count=len(self.tasks)
        )
        
        # Inicializar o recuperar estado
        status_key = f"maintenance:status:{date_str}"
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
                    state["tasks"][task_name] = TaskStatus.COMPLETED
                    logger.info(
                        "task_completed",
                        task=task_name,
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

