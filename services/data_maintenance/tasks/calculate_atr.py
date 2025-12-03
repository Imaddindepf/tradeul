"""
Calculate ATR Task
Calcula ATR(14) para todos los tickers del universo y lo guarda en Redis
"""

import asyncio
from datetime import date, timedelta
from typing import Dict, List
import httpx

import sys
sys.path.append('/app')
sys.path.append('/app/services/analytics')

from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import get_logger
from shared.utils.atr_calculator import ATRCalculator

logger = get_logger(__name__)


class CalculateATRTask:
    """
    Tarea: Calcular ATR para todos los tickers activos
    
    Proceso:
    1. Obtener universo de tickers activos desde ticker_universe
    2. Calcular ATR(14) para cada ticker usando datos OHLC
    3. Guardar en Redis hash atr:daily
    4. TTL: 24 horas (se recalcula diariamente)
    """
    
    name = "calculate_atr"
    
    def __init__(self, redis_client: RedisClient, timescale_client: TimescaleClient):
        self.redis = redis_client
        self.db = timescale_client
        self.calculator = ATRCalculator(
            redis_client=redis_client,
            timescale_client=timescale_client,
            period=14,
            use_ema=True
        )
        
        # Configuración
        self.batch_size = 100  # Procesar en lotes de 100
        self.max_concurrent = 10  # 10 cálculos simultáneos por lote
    
    async def execute(self, target_date: date) -> Dict:
        """
        Ejecutar cálculo de ATR
        
        Args:
            target_date: Fecha para la cual calcular ATR (normalmente ayer)
        
        Returns:
            Dict con resultado de la ejecución
        """
        logger.info(
            "calculate_atr_task_started",
            date=target_date.isoformat()
        )
        
        start_time = asyncio.get_event_loop().time()
        
        try:
            # 1. Obtener universo de tickers activos
            symbols = await self._get_active_symbols()
            
            if not symbols:
                return {
                    "success": False,
                    "error": "No active symbols found",
                    "symbols_total": 0
                }
            
            logger.info(
                "symbols_loaded",
                count=len(symbols)
            )
            
            # 2. Calcular ATR en lotes
            results = await self._calculate_batch(symbols, target_date)
            
            # 3. Estadísticas
            success_count = results["success"]
            failed_count = results["failed"]
            skipped_count = results["skipped"]
            
            elapsed = asyncio.get_event_loop().time() - start_time
            
            logger.info(
                "calculate_atr_task_completed",
                symbols_total=len(symbols),
                success=success_count,
                failed=failed_count,
                skipped=skipped_count,
                duration_seconds=round(elapsed, 2),
                rate_per_second=round(success_count / elapsed, 2) if elapsed > 0 else 0
            )
            
            # 🔥 VALIDACIÓN: Verificar que se calculó ATR para suficientes tickers
            # Los "skipped" cuentan como éxito porque ya tienen ATR válido en cache
            MIN_ATR_VALID = 10000
            valid_count = success_count + skipped_count  # Skipped = ya en cache = válido
            valid_rate = valid_count / len(symbols) if len(symbols) > 0 else 0
            
            if valid_count < MIN_ATR_VALID or valid_rate < 0.8:
                logger.error(
                    "insufficient_atr_calculated",
                    expected_min=MIN_ATR_VALID,
                    actual=valid_count,
                    new_calculated=success_count,
                    from_cache=skipped_count,
                    valid_rate=f"{valid_rate*100:.1f}%"
                )
                return {
                    "success": False,
                    "error": f"Insufficient ATR: {valid_count} < {MIN_ATR_VALID} (rate: {valid_rate*100:.1f}%)",
                    "symbols_total": len(symbols),
                    "symbols_success": success_count,
                    "symbols_failed": failed_count,
                    "symbols_skipped": skipped_count,
                    "duration_seconds": round(elapsed, 2)
                }
            
            return {
                "success": True,
                "symbols_total": len(symbols),
                "symbols_success": success_count,
                "symbols_failed": failed_count,
                "symbols_skipped": skipped_count,
                "duration_seconds": round(elapsed, 2)
            }
        
        except Exception as e:
            logger.error(
                "calculate_atr_task_failed",
                error=str(e),
                error_type=type(e).__name__
            )
            
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__
            }
    
    async def _get_active_symbols(self) -> List[str]:
        """Obtener símbolos activos desde ticker_universe"""
        try:
            query = """
                SELECT symbol
                FROM tickers_unified
                WHERE is_actively_trading = true
                ORDER BY symbol
            """
            
            rows = await self.db.fetch(query)
            symbols = [row['symbol'] for row in rows]
            
            return symbols
        
        except Exception as e:
            logger.error(
                "get_symbols_failed",
                error=str(e)
            )
            return []
    
    async def _calculate_batch(self, symbols: List[str], target_date: date) -> Dict:
        """Calcular ATR en lotes para optimizar performance"""
        success = 0
        failed = 0
        skipped = 0
        
        # Dividir en lotes
        for i in range(0, len(symbols), self.batch_size):
            batch = symbols[i:i + self.batch_size]
            batch_num = (i // self.batch_size) + 1
            total_batches = (len(symbols) + self.batch_size - 1) // self.batch_size
            
            logger.info(
                "processing_batch",
                batch=batch_num,
                total_batches=total_batches,
                batch_size=len(batch)
            )
            
            # Procesar batch con concurrencia limitada
            semaphore = asyncio.Semaphore(self.max_concurrent)
            
            async def calculate_with_semaphore(symbol):
                async with semaphore:
                    return await self._calculate_single(symbol, target_date)
            
            tasks = [calculate_with_semaphore(symbol) for symbol in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Contar resultados
            for result in results:
                if isinstance(result, Exception):
                    failed += 1
                elif result == "success":
                    success += 1
                elif result == "skipped":
                    skipped += 1
                else:
                    failed += 1
            
            # Log progreso
            if batch_num % 10 == 0 or batch_num == total_batches:
                logger.info(
                    "batch_progress",
                    processed=min(i + self.batch_size, len(symbols)),
                    total=len(symbols),
                    success=success,
                    failed=failed,
                    skipped=skipped
                )
        
        return {
            "success": success,
            "failed": failed,
            "skipped": skipped
        }
    
    async def _calculate_single(self, symbol: str, target_date: date) -> str:
        """Calcular ATR para un símbolo individual"""
        try:
            # Verificar si ya existe en caché (válido para hoy)
            cached = await self.calculator._get_from_cache(symbol)
            
            if cached:
                # Ya está calculado
                return "skipped"
            
            # Calcular ATR
            result = await self.calculator.calculate_atr(
                symbol=symbol,
                current_price=None,  # Se calculará desde los datos históricos
                trading_date=target_date
            )
            
            if result:
                return "success"
            else:
                # Sin suficientes datos históricos
                return "skipped"
        
        except Exception as e:
            logger.debug(
                "atr_calculation_error",
                symbol=symbol,
                error=str(e)
            )
            return "failed"

