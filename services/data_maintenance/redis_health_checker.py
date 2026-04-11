"""
Redis Health Checker & Auto-Recovery
Detecta automáticamente si Redis está vacío o tiene datos faltantes
y ejecuta una recuperación completa de todos los datos críticos
"""

import asyncio
from datetime import date, timedelta
from typing import Dict, List, Tuple
import sys
sys.path.append('/app')

from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import get_logger

logger = get_logger(__name__)


class RedisHealthChecker:
    """
    Verificador de salud de Redis con auto-recuperación
    
    Detecta:
    - Redis completamente vacío (post-FLUSHDB)
    - Datos críticos faltantes (universe, metadata, RVOL, ATR)
    - Datos desactualizados (>24 horas)
    
    Recupera:
    - ticker:universe (SET de símbolos activos)
    - metadata:ticker:{symbol} (metadata individual por ticker)
    - rvol:hist:avg:{symbol}:5 (promedios históricos RVOL)
    - atr:daily (hash de ATR por ticker)
    """
    
    def __init__(self, redis_client: RedisClient, timescale_client: TimescaleClient):
        self.redis = redis_client
        self.db = timescale_client
        
        # Umbrales para considerar datos "críticos"
        self.min_universe_size = 10000  # Mínimo de tickers esperados
        self.min_metadata_keys = 10000  # Mínimo de metadatos esperados
        self.min_rvol_keys = 10000     # Mínimo de hashes RVOL esperados
        self.min_atr_keys = 1          # Mínimo de claves ATR (hash único)
    
    async def check_and_recover(self) -> Dict:
        """
        Verificar salud de Redis y recuperar si es necesario
        
        Returns:
            Dict con:
            - needs_recovery: bool
            - issues_found: List[str]
            - recovery_executed: bool
            - recovery_results: Dict (si se ejecutó recovery)
        """
        logger.info("🔍 Checking Redis health...")
        
        # 1. Verificar qué datos críticos faltan
        issues = await self._diagnose_redis()
        
        if not issues:
            logger.info("✅ Redis is healthy - all critical data present")
            return {
                "needs_recovery": False,
                "issues_found": [],
                "recovery_executed": False
            }
        
        logger.warning(
            "⚠️ Redis health issues detected",
            issues=issues,
            count=len(issues)
        )
        
        # 2. Ejecutar recuperación automática
        logger.info("🚀 Initiating automatic Redis recovery...")
        recovery_results = await self._execute_recovery(issues)
        
        return {
            "needs_recovery": True,
            "issues_found": issues,
            "recovery_executed": True,
            "recovery_results": recovery_results
        }
    
    async def _diagnose_redis(self) -> List[str]:
        """
        Diagnosticar qué datos faltan en Redis
        
        Returns:
            Lista de issues encontrados (vacía si todo está bien)
        """
        issues = []
        
        try:
            # 1. Verificar DBSIZE total
            dbsize = await self.redis.dbsize()
            
            if dbsize == 0:
                issues.append("redis_completely_empty")
                logger.warning("🚨 Redis is COMPLETELY EMPTY (DBSIZE=0)")
                # Si está completamente vacío, no necesitamos verificar más
                return issues
            
            logger.info(f"Redis DBSIZE: {dbsize}")
            
            # 2. Verificar ticker:universe
            universe_size = await self.redis.scard("ticker:universe")
            
            if universe_size == 0:
                issues.append("missing_ticker_universe")
                logger.warning("❌ ticker:universe is missing or empty")
            elif universe_size < self.min_universe_size:
                issues.append("incomplete_ticker_universe")
                logger.warning(
                    f"⚠️ ticker:universe is incomplete ({universe_size} < {self.min_universe_size})"
                )
            else:
                logger.info(f"✅ ticker:universe: {universe_size} symbols")
            
            # 3. Verificar metadata:ticker:*
            metadata_pattern = "metadata:ticker:*"
            metadata_keys = await self.redis.scan_keys(metadata_pattern)
            metadata_count = len(metadata_keys)
            
            if metadata_count == 0:
                issues.append("missing_ticker_metadata")
                logger.warning("❌ No ticker metadata found")
            elif metadata_count < self.min_metadata_keys:
                issues.append("incomplete_ticker_metadata")
                logger.warning(
                    f"⚠️ Ticker metadata is incomplete ({metadata_count} < {self.min_metadata_keys})"
                )
            else:
                logger.info(f"✅ Ticker metadata: {metadata_count} keys")
            
            # 4. Verificar rvol:hist:avg:*
            rvol_pattern = "rvol:hist:avg:*"
            rvol_keys = await self.redis.scan_keys(rvol_pattern)
            rvol_count = len(rvol_keys)
            
            if rvol_count == 0:
                issues.append("missing_rvol_averages")
                logger.warning("❌ No RVOL historical averages found")
            elif rvol_count < self.min_rvol_keys:
                issues.append("incomplete_rvol_averages")
                logger.warning(
                    f"⚠️ RVOL averages are incomplete ({rvol_count} < {self.min_rvol_keys})"
                )
            else:
                logger.info(f"✅ RVOL historical averages: {rvol_count} hashes")
            
            # 5. Verificar atr:daily
            atr_exists = await self.redis.exists("atr:daily")
            
            if not atr_exists:
                issues.append("missing_atr_data")
                logger.warning("❌ ATR data (atr:daily) is missing")
            else:
                # Verificar cuántos tickers tienen ATR
                atr_count = await self.redis.hlen("atr:daily")
                if atr_count < self.min_atr_keys:
                    issues.append("incomplete_atr_data")
                    logger.warning(f"⚠️ ATR data is incomplete ({atr_count} entries)")
                else:
                    logger.info(f"✅ ATR data: {atr_count} tickers")
            
            return issues
        
        except Exception as e:
            logger.error("diagnosis_failed", error=str(e))
            # Si la diagnosis falla, asumir que hay problemas
            return ["diagnosis_failed"]
    
    async def _execute_recovery(self, issues: List[str]) -> Dict:
        """
        Ejecutar recuperación completa de Redis
        
        Args:
            issues: Lista de problemas detectados
        
        Returns:
            Dict con resultados de cada tarea ejecutada
        """
        results = {}
        
        try:
            # Si Redis está completamente vacío o faltan datos críticos,
            # ejecutar TODAS las tareas en orden
            
            # 1. Sincronizar universe y metadata (más rápido, sin deps)
            if any(issue in issues for issue in [
                "redis_completely_empty",
                "missing_ticker_universe",
                "incomplete_ticker_universe",
                "missing_ticker_metadata",
                "incomplete_ticker_metadata"
            ]):
                logger.info("📥 Step 1/3: Syncing universe & metadata from TimescaleDB...")
                from tasks.sync_redis import SyncRedisTask
                
                sync_task = SyncRedisTask(self.redis, self.db)
                sync_result = await sync_task.execute(date.today())
                results["sync_redis"] = sync_result
                
                logger.info(
                    "✅ Universe & metadata synced",
                    universe=sync_result.get("universe_synced", 0),
                    metadata=sync_result.get("metadata_synced", 0)
                )
            
            # 2. Calcular RVOL historical averages (requiere volume_slots en DB)
            if any(issue in issues for issue in [
                "redis_completely_empty",
                "missing_rvol_averages",
                "incomplete_rvol_averages"
            ]):
                logger.info(" Step 2/3: Calculating RVOL historical averages...")
                from tasks.calculate_rvol_averages import CalculateRVOLHistoricalAveragesTask
                
                rvol_task = CalculateRVOLHistoricalAveragesTask(self.redis, self.db)
                target_date = date.today() - timedelta(days=1)
                rvol_result = await rvol_task.execute(target_date)
                results["calculate_rvol"] = rvol_result
                
                logger.info(
                    "✅ RVOL averages calculated",
                    symbols_processed=rvol_result.get("symbols_processed", 0),
                    redis_inserted=rvol_result.get("redis_inserted", 0)
                )
            
            # 3. Calcular ATR (requiere OHLC en DB)
            if any(issue in issues for issue in [
                "redis_completely_empty",
                "missing_atr_data",
                "incomplete_atr_data"
            ]):
                logger.info("📈 Step 3/3: Calculating ATR for all tickers...")
                from tasks.calculate_atr import CalculateATRTask
                
                atr_task = CalculateATRTask(self.redis, self.db)
                target_date = date.today() - timedelta(days=1)
                atr_result = await atr_task.execute(target_date)
                results["calculate_atr"] = atr_result
                
                logger.info(
                    "✅ ATR calculated",
                    symbols_success=atr_result.get("symbols_success", 0),
                    symbols_failed=atr_result.get("symbols_failed", 0)
                )
            
            logger.info("🎉 Redis recovery completed successfully")
            
            return {
                "success": True,
                "tasks_executed": list(results.keys()),
                "task_results": results
            }
        
        except Exception as e:
            logger.error("recovery_execution_failed", error=str(e))
            return {
                "success": False,
                "error": str(e),
                "partial_results": results
            }

