"""
Maintenance Orchestrator
========================

Coordina la ejecución de todas las tareas de mantenimiento en orden.

Flujo:
1. clear_caches         - Limpiar caches de tiempo real
2. load_ohlc            - Cargar OHLC del día anterior
3. load_volume_slots    - Cargar volume slots del día anterior
4. calculate_atr        - Calcular ATR para todos los tickers
5. calculate_rvol       - Calcular RVOL historical averages
6. sync_ticker_universe - Sincronizar universo de tickers con Polygon (nuevos/delistados/nombres)
7. enrich_metadata      - Enriquecer metadata de tickers (market_cap, sector, company_name)
8. sync_redis           - Sincronizar Redis con datos frescos
9. notify_services      - Notificar a otros servicios que hay nuevo día

PRINCIPIOS:
- Cada tarea es independiente y reporta su éxito/fallo
- El orchestrator NO valida resultados - cada tarea se valida a sí misma
- Si una tarea falla, las demás continúan
- Estado se guarda en Redis para recovery
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

logger = get_logger(__name__)


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class MaintenanceOrchestrator:
    """
    Orquestador de tareas de mantenimiento diario
    """
    
    def __init__(self, redis_client: RedisClient, timescale_client: TimescaleClient):
        self.redis = redis_client
        self.db = timescale_client
    
    async def run_full_cycle(self, target_date: date, skip_cache_clear: bool = False) -> bool:
        """
        Ejecutar ciclo completo de mantenimiento
        
        Args:
            target_date: Fecha del día de trading a procesar
            skip_cache_clear: Si True, no limpia caches ni notifica nuevo día
                             (útil para festivos donde el usuario debe seguir viendo datos)
            
        Returns:
            True si todas las tareas fueron exitosas
        """
        logger.info(
            "🔄 maintenance_cycle_starting",
            target_date=str(target_date),
            skip_cache_clear=skip_cache_clear
        )
        
        cycle_start = datetime.now()
        state = self._init_state(target_date)
        
        # Lista ordenada de tareas
        # Si skip_cache_clear=True, omitir clear_caches, sync_redis y notify_services
        if skip_cache_clear:
            tasks = [
                ("load_ohlc", self._task_load_ohlc),
                ("load_volume_slots", self._task_load_volume_slots),
                ("calculate_atr", self._task_calculate_atr),
                ("calculate_rvol", self._task_calculate_rvol),
                ("sync_ticker_universe", self._task_sync_ticker_universe),
                ("enrich_metadata", self._task_enrich_metadata),
                ("export_screener_metadata", self._task_export_screener_metadata),
            ]
            logger.info("📦 data_only_mode - skipping cache clear and notifications")
        else:
            tasks = [
                ("clear_caches", self._task_clear_caches),
                ("load_ohlc", self._task_load_ohlc),
                ("load_volume_slots", self._task_load_volume_slots),
                ("calculate_atr", self._task_calculate_atr),
                ("calculate_rvol", self._task_calculate_rvol),
                ("sync_ticker_universe", self._task_sync_ticker_universe),
                ("enrich_metadata", self._task_enrich_metadata),
                ("export_screener_metadata", self._task_export_screener_metadata),
                ("sync_redis", self._task_sync_redis),
                ("notify_services", self._task_notify_services),
            ]
        
        all_success = True
        
        for task_name, task_func in tasks:
            state["tasks"][task_name] = TaskStatus.RUNNING
            await self._save_state(target_date, state)
            
            task_start = datetime.now()
            
            try:
                result = await task_func(target_date)
                task_duration = (datetime.now() - task_start).total_seconds()
                
                if result.get("success"):
                    state["tasks"][task_name] = TaskStatus.SUCCESS
                    logger.info(
                        f"✅ task_completed",
                        task=task_name,
                        duration_seconds=round(task_duration, 2),
                        **{k: v for k, v in result.items() if k != "success"}
                    )
                else:
                    state["tasks"][task_name] = TaskStatus.FAILED
                    all_success = False
                    logger.error(
                        f"❌ task_failed",
                        task=task_name,
                        duration_seconds=round(task_duration, 2),
                        error=result.get("error", "Unknown error")
                    )
                    
            except Exception as e:
                state["tasks"][task_name] = TaskStatus.FAILED
                all_success = False
                logger.error(
                    f"💥 task_exception",
                    task=task_name,
                    error=str(e),
                    error_type=type(e).__name__
                )
            
            await self._save_state(target_date, state)
        
        # Finalizar
        cycle_duration = (datetime.now() - cycle_start).total_seconds()
        state["completed_at"] = datetime.now().isoformat()
        state["duration_seconds"] = round(cycle_duration, 2)
        state["all_success"] = all_success
        
        await self._save_state(target_date, state)
        
        success_count = sum(1 for s in state["tasks"].values() if s == TaskStatus.SUCCESS)
        failed_count = sum(1 for s in state["tasks"].values() if s == TaskStatus.FAILED)
        
        logger.info(
            "🏁 maintenance_cycle_finished",
            target_date=str(target_date),
            duration_seconds=round(cycle_duration, 2),
            duration_human=self._format_duration(cycle_duration),
            success_count=success_count,
            failed_count=failed_count,
            all_success=all_success
        )
        
        return all_success
    
    def _init_state(self, target_date: date) -> Dict:
        """Inicializar estado del ciclo"""
        return {
            "date": target_date.isoformat(),
            "started_at": datetime.now().isoformat(),
            "completed_at": None,
            "duration_seconds": None,
            "all_success": None,
            "tasks": {
                "clear_caches": TaskStatus.PENDING,
                "load_ohlc": TaskStatus.PENDING,
                "load_volume_slots": TaskStatus.PENDING,
                "calculate_atr": TaskStatus.PENDING,
                "calculate_rvol": TaskStatus.PENDING,
                "sync_ticker_universe": TaskStatus.PENDING,
                "enrich_metadata": TaskStatus.PENDING,
                "export_screener_metadata": TaskStatus.PENDING,
                "sync_redis": TaskStatus.PENDING,
                "notify_services": TaskStatus.PENDING,
            }
        }
    
    async def _save_state(self, target_date: date, state: Dict):
        """Guardar estado en Redis"""
        try:
            key = f"maintenance:status:{target_date.isoformat()}"
            await self.redis.set(key, json.dumps(state), ttl=86400 * 7)
        except Exception as e:
            logger.warning("failed_to_save_state", error=str(e))
    
    def _format_duration(self, seconds: float) -> str:
        """Formatear duración en formato legible"""
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            return f"{seconds / 60:.1f}m"
        else:
            return f"{seconds / 3600:.1f}h"
    
    # =========================================================================
    # TAREAS
    # =========================================================================
    
    async def _task_clear_caches(self, target_date: date) -> Dict:
        """
        Tarea 1: Limpiar caches de tiempo real
        
        Limpia:
        - snapshot:* (snapshots del día anterior)
        - realtime:* (datos en tiempo real viejos)
        
        NOTA: Los caches del scanner (scanner:*) se limpian a las 3:45 AM ET
        en una tarea separada del scheduler, DESPUÉS del reset de Polygon (~3:30 AM).
        Esto evita que el scanner repueble los caches con datos viejos.
        """
        try:
            patterns = [
                # NO limpiar scanner:* aquí - se hace a las 3:45 AM
                "snapshot:enriched:*",
                "snapshot:polygon:*",
                "realtime:*",
            ]
            
            total_deleted = 0
            
            for pattern in patterns:
                try:
                    deleted = await self.redis.delete_pattern(pattern)
                    total_deleted += deleted
                    if deleted > 0:
                        logger.debug(f"Deleted {deleted} keys matching {pattern}")
                except Exception as e:
                    logger.warning(f"Failed to delete pattern {pattern}: {e}")
            
            # Publicar evento de nuevo día
            await self.redis.client.publish(
                "trading:new_day",
                json.dumps({
                    "event": "new_trading_day",
                    "date": target_date.isoformat(),
                    "action": "caches_cleared"
                })
            )
            
            return {
                "success": True,
                "keys_deleted": total_deleted,
                "patterns_processed": len(patterns)
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _task_load_ohlc(self, target_date: date) -> Dict:
        """
        Tarea 2: Cargar datos OHLC del día anterior
        
        Usa el nuevo OHLCLoader que solo carga un día específico.
        """
        try:
            from tasks.ohlc_loader import OHLCLoader
            
            loader = OHLCLoader(self.redis, self.db)
            result = await loader.load_day(target_date)
            
            return result
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _task_load_volume_slots(self, target_date: date) -> Dict:
        """
        Tarea 3: Cargar volume slots del día anterior
        
        Usa LoadVolumeSlotsTask que carga últimos días faltantes.
        """
        try:
            from tasks.load_volume_slots import LoadVolumeSlotsTask
            
            loader = LoadVolumeSlotsTask(self.redis, self.db)
            result = await loader.execute(target_date)
            
            return result
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _task_calculate_atr(self, target_date: date) -> Dict:
        """
        Tarea 4: Calcular ATR para todos los tickers
        
        Usa el nuevo ATRCalculatorTask que solo calcula si no está en cache.
        """
        try:
            from tasks.atr_calculator import ATRCalculatorTask
            
            calculator = ATRCalculatorTask(self.redis, self.db)
            result = await calculator.calculate_all(target_date)
            
            return result
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _task_calculate_rvol(self, target_date: date) -> Dict:
        """
        Tarea 5: Calcular RVOL historical averages
        """
        try:
            from tasks.calculate_rvol_averages import CalculateRVOLHistoricalAveragesTask
            
            calculator = CalculateRVOLHistoricalAveragesTask(self.redis, self.db)
            result = await calculator.execute(target_date)
            
            return result
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _task_sync_ticker_universe(self, target_date: date) -> Dict:
        """
        Tarea 6: Sincronizar universo de tickers con Polygon
        
        - Agrega tickers nuevos de Polygon
        - Desactiva tickers delistados
        - Actualiza nombres faltantes
        """
        try:
            from tasks.sync_ticker_universe import SyncTickerUniverseTask
            
            syncer = SyncTickerUniverseTask(self.redis, self.db)
            result = await syncer.execute(target_date)
            
            return result
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _task_enrich_metadata(self, target_date: date) -> Dict:
        """
        Tarea 7: Enriquecer metadata de tickers (market_cap, sector, company_name, etc.)
        """
        try:
            from tasks.enrich_metadata import EnrichMetadataTask
            
            enricher = EnrichMetadataTask(self.redis, self.db)
            result = await enricher.execute(target_date)
            
            return result
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _task_export_screener_metadata(self, target_date: date) -> Dict:
        """
        Tarea 8: Exportar metadata a Parquet para el Screener service
        """
        try:
            from tasks.export_screener_metadata import ExportScreenerMetadataTask
            
            exporter = ExportScreenerMetadataTask(self.redis, self.db)
            result = await exporter.execute(target_date)
            
            return result
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _task_sync_redis(self, target_date: date) -> Dict:
        """
        Tarea 8: Sincronizar Redis con datos frescos
        """
        try:
            from tasks.sync_redis import SyncRedisTask
            
            syncer = SyncRedisTask(self.redis, self.db)
            result = await syncer.execute(target_date)
            
            return result
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _task_notify_services(self, target_date: date) -> Dict:
        """
        Tarea 9: Notificar a otros servicios que el mantenimiento completó
        """
        try:
            # Publicar evento de mantenimiento completado
            await self.redis.client.publish(
                "maintenance:completed",
                json.dumps({
                    "event": "maintenance_completed",
                    "date": target_date.isoformat(),
                    "timestamp": datetime.now().isoformat()
                })
            )
            
            # Actualizar key de último mantenimiento exitoso
            await self.redis.set(
                f"maintenance:executed:{target_date.isoformat()}",
                "1",
                ttl=86400 * 7
            )
            
            return {
                "success": True,
                "events_published": ["maintenance:completed"],
                "date": target_date.isoformat()
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}

