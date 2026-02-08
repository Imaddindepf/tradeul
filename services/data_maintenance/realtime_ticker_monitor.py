"""
Real-Time Ticker Monitor
Monitorea continuamente durante trading hours para detectar tickers nuevos/cambiados
y los carga inmediatamente sin esperar al ciclo nocturno
"""

import asyncio
from datetime import datetime, date
from typing import Set
import structlog

import sys
sys.path.append('/app')

from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import get_logger
from tasks.auto_recover_missing_tickers import AutoRecoverMissingTickersTask

logger = get_logger(__name__)


class RealtimeTickerMonitor:
    """
    Monitor en tiempo real de tickers
    
    Corre continuamente durante trading hours:
    - Cada 5 minutos revisa snapshot
    - Detecta tickers faltantes
    - Los carga INMEDIATAMENTE
    - No espera al ciclo nocturno
    """
    
    def __init__(self, redis_client: RedisClient, timescale_client: TimescaleClient):
        self.redis = redis_client
        self.db = timescale_client
        self.recovery_task = AutoRecoverMissingTickersTask(redis_client, timescale_client)
        
        # Tracking
        self.last_check = None
        self.tickers_recovered_today = []
        self.is_running = False
        
        # Configuración
        self.check_interval = 300  # 5 minutos
        self.min_missing_to_trigger = 3  # Mínimo 3 tickers faltantes para activar
    
    async def start(self):
        """Iniciar monitoreo en background"""
        self.is_running = True
        logger.info("realtime_ticker_monitor_started", interval_seconds=self.check_interval)
        
        while self.is_running:
            try:
                await self._check_and_recover()
                await asyncio.sleep(self.check_interval)
            
            except asyncio.CancelledError:
                logger.info("realtime_monitor_cancelled")
                break
            
            except Exception as e:
                logger.error("realtime_monitor_error", error=str(e))
                await asyncio.sleep(60)  # Esperar 1 min en error
    
    async def stop(self):
        """Detener monitoreo"""
        self.is_running = False
        logger.info("realtime_ticker_monitor_stopped")
    
    async def _check_and_recover(self):
        """Revisar y recuperar tickers faltantes"""
        try:
            logger.info("checking_for_missing_tickers")
            
            # 1. Detectar faltantes
            missing_count = await self._count_missing_tickers()
            
            if missing_count == 0:
                logger.info("no_missing_tickers_found")
                return
            
            logger.info(f"missing_tickers_found", count=missing_count)
            
            # 2. Si hay suficientes faltantes, ejecutar recovery
            if missing_count >= self.min_missing_to_trigger:
                logger.info("triggering_immediate_recovery", missing_count=missing_count)
                
                # Ejecutar recovery COMPLETO (agrega + carga datos)
                result = await self.recovery_task.execute(date.today() - timedelta(days=1))
                
                if result.get('success'):
                    recovered = result.get('tickers_recovered', 0)
                    if recovered > 0:
                        self.tickers_recovered_today.extend(result.get('valid_found', []))
                        logger.info(
                            "immediate_recovery_completed",
                            recovered=recovered,
                            total_today=len(self.tickers_recovered_today)
                        )
                else:
                    logger.error("immediate_recovery_failed", error=result.get('error'))
            
            self.last_check = datetime.now()
        
        except Exception as e:
            logger.error("check_and_recover_failed", error=str(e))
    
    async def _count_missing_tickers(self) -> int:
        """Contar cuántos tickers del snapshot no están en universo"""
        try:
            # Snapshot actual (read keys only from Redis Hash)
            all_keys = await self.redis.client.hkeys("snapshot:enriched:latest")
            if not all_keys:
                return 0
            
            snapshot_tickers = {k for k in all_keys if k != "__meta__"}
            
            # Universo desde tickers_unified
            rows = await self.db.fetch("SELECT symbol FROM tickers_unified WHERE is_actively_trading = true")
            universe_tickers = {r['symbol'] for r in rows}
            
            # Diferencia
            missing = snapshot_tickers - universe_tickers
            return len(missing)
        
        except Exception as e:
            logger.error("failed_to_count_missing", error=str(e))
            return 0
    
    def get_stats(self) -> dict:
        """Estadísticas del monitor"""
        return {
            "is_running": self.is_running,
            "last_check": self.last_check.isoformat() if self.last_check else None,
            "tickers_recovered_today": len(self.tickers_recovered_today),
            "recovered_symbols": self.tickers_recovered_today
        }


# Importar timedelta
from datetime import timedelta


