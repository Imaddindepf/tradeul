"""
Calculate RVOL Historical Averages Task
Calcula promedios históricos acumulados por slot para RVOL y los guarda en Redis

Implementa la lógica del PineScript:
- Calcula promedio acumulado por slot para últimos N días
- Guarda SOLO en Redis hash rvol:hist:avg:{symbol}:{days}
- Vacía Redis antes de recalcular para evitar datos obsoletos
- Pre-calienta Redis con TODOS los símbolos activos para evitar misses en analytics
"""

import asyncio
import sys
sys.path.append('/app')

from datetime import date
from typing import Dict, List
from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import get_logger

logger = get_logger(__name__)


class CalculateRVOLHistoricalAveragesTask:
    """
    Tarea: Calcular promedios históricos acumulados por slot para RVOL
    
    Proceso:
    1. Vaciar Redis de promedios históricos antiguos (rvol:hist:avg:*)
    2. Obtener símbolos activos del universo
    3. Para cada símbolo:
       - Calcular promedio acumulado por slot (0-191) para últimos N días
       - Guardar en Redis hash rvol:hist:avg:{symbol}:{days}
    4. TTL en Redis: 8 horas (suficiente para día de trading)
    5. Pre-calienta Redis con TODOS los símbolos activos para evitar misses en analytics
    
    Lógica PineScript:
    - Volumen acumulado HOY en slot X
    - Promedio volumen acumulado en slot X de últimos N días
    - Si falta slot, busca hacia atrás (manejado por SQL window function)
    - RVOL = acumulado_hoy / promedio_historico
    """
    
    name = "calculate_rvol_averages"
    
    def __init__(self, redis_client: RedisClient, timescale_client: TimescaleClient):
        self.redis = redis_client
        self.db = timescale_client
        
        # Configuración
        self.lookback_days = 5  # N días históricos (igual que PineScript default)
        self.max_slot = 191  # Slots 0-191 (4:00 AM - 8:00 PM ET)
        self.batch_size = 50  # Procesar símbolos en lotes de 50
        self.redis_ttl = 28800  # 8 horas TTL en Redis
    
    async def execute(self, target_date: date) -> Dict:
        """
        Ejecutar cálculo de promedios históricos
        
        Args:
            target_date: Fecha objetivo (no usado directamente, calcula desde BD)
        
        Returns:
            Dict con resultado
        """
        logger.info(
            "rvol_averages_task_starting",
            lookback_days=self.lookback_days,
            max_slot=self.max_slot
        )
        
        try:
            # 1. Vaciar Redis de promedios históricos antiguos
            await self._clear_redis_averages()
            
            # 2. Obtener símbolos activos
            symbols = await self._get_active_symbols()
            
            if not symbols:
                logger.warning("no_symbols_found")
                return {
                    "success": False,
                    "error": "No symbols found"
                }
            
            logger.info(
                "rvol_averages_symbols_loaded",
                count=len(symbols)
            )
            
            # 3. Calcular promedios en lotes
            total_processed = 0
            total_redis_inserted = 0
            
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
                
                # Procesar batch en paralelo
                semaphore = asyncio.Semaphore(10)  # Max 10 concurrent
                
                async def process_symbol(symbol: str):
                    async with semaphore:
                        return await self._calculate_and_save_averages(symbol)
                
                tasks = [process_symbol(sym) for sym in batch]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Contar resultados
                for result in results:
                    if isinstance(result, Exception):
                        logger.error(
                            "symbol_processing_error",
                            error=str(result),
                            error_type=type(result).__name__
                        )
                    elif isinstance(result, dict):
                        if result.get("success"):
                            total_processed += 1
                            total_redis_inserted += result.get("redis_inserted", 0)
            
            logger.info(
                "rvol_averages_task_completed",
                symbols_total=len(symbols),
                symbols_processed=total_processed,
                redis_inserted=total_redis_inserted
            )
            
            return {
                "success": True,
                "symbols_total": len(symbols),
                "symbols_processed": total_processed,
                "redis_inserted": total_redis_inserted
            }
        
        except Exception as e:
            logger.error(
                "rvol_averages_task_failed",
                error=str(e),
                error_type=type(e).__name__
            )
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _clear_redis_averages(self):
        """Vaciar Redis de promedios históricos antiguos"""
        try:
            pattern = "rvol:hist:avg:*"
            deleted = await self.redis.delete_pattern(pattern)
            logger.info(
                "redis_averages_cleared",
                pattern=pattern,
                deleted_count=deleted
            )
        except Exception as e:
            logger.warning(
                "redis_clear_failed",
                error=str(e)
            )
    
    async def _get_active_symbols(self) -> List[str]:
        """Obtener símbolos activos del universo"""
        try:
            query = """
                SELECT DISTINCT symbol 
                FROM ticker_universe 
                WHERE is_active = true
                ORDER BY symbol
            """
            rows = await self.db.fetch(query)
            return [row['symbol'] for row in rows]
        except Exception as e:
            logger.error("failed_to_get_symbols", error=str(e))
            return []
    
    async def _calculate_and_save_averages(self, symbol: str) -> Dict:
        """
        Calcular y guardar promedios históricos para un símbolo
        
        Implementa la misma lógica que historical service pero guarda en BD también
        """
        try:
            sym = symbol.upper()
            
            # Query SQL igual que historical service (lógica PineScript)
            # Calcula promedio acumulado por slot para últimos N días
            query = (
                "WITH last_days AS ("
                "  SELECT DISTINCT date"
                "  FROM volume_slots"
                "  WHERE symbol = $1 AND date < CURRENT_DATE"
                "  ORDER BY date DESC"
                "  LIMIT $2"
                "), filled AS ("
                "  SELECT vs.date, vs.slot_number,"
                "         MAX(vs.volume_accumulated) OVER ("
                "             PARTITION BY vs.date"
                "             ORDER BY vs.slot_number"
                "             ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW"
                "         ) AS vol_acc"
                "  FROM volume_slots vs"
                "  JOIN last_days d ON vs.date = d.date"
                "  WHERE vs.symbol = $1 AND vs.slot_number <= $3"
                "), slots AS ("
                "  SELECT generate_series(0, $3) AS slot_number"
                ")"
                "SELECT s.slot_number, AVG("
                "  (SELECT MAX(f.vol_acc) FROM filled f WHERE f.date = d.date AND f.slot_number <= s.slot_number)"
                ") AS avg_vol"
                "  FROM (SELECT date FROM last_days) d"
                "  CROSS JOIN slots s"
                " GROUP BY s.slot_number"
                " ORDER BY s.slot_number"
            )
            
            rows = await self.db.fetch(query, sym, self.lookback_days, self.max_slot)
            
            if not rows:
                logger.debug("no_historical_data", symbol=sym)
                return {
                    "success": False,
                    "error": "No historical data",
                    "redis_inserted": 0
                }
            
            # Preparar datos para Redis (hash)
            redis_mapping = {}
            
            for row in rows:
                slot_num = int(row["slot_number"]) if isinstance(row, dict) else int(row[0])
                raw_avg = row["avg_vol"] if isinstance(row, dict) else row[1]
                avg_val = int(raw_avg or 0)
                
                # Solo guardar slots con datos válidos
                if avg_val > 0:
                    redis_mapping[str(slot_num)] = str(avg_val)
            
            # Guardar SOLO en Redis (hash) - La tabla BD es redundante
            # Los promedios se usan desde Redis directamente en analytics
            redis_inserted = 0
            if redis_mapping:
                hash_key = f"rvol:hist:avg:{sym}:{self.lookback_days}"
                try:
                    # hmset con serialize=False para guardar strings directamente
                    await self.redis.hmset(hash_key, redis_mapping, serialize=False)
                    # Expirar después de TTL
                    await self.redis.expire(hash_key, self.redis_ttl)
                    redis_inserted = len(redis_mapping)
                except Exception as e:
                    logger.error(
                        "redis_insert_failed",
                        symbol=sym,
                        error=str(e)
                    )
            
            return {
                "success": True,
                "redis_inserted": redis_inserted
            }
        
        except Exception as e:
            logger.error(
                "calculate_averages_error",
                symbol=symbol,
                error=str(e),
                error_type=type(e).__name__
            )
            return {
                "success": False,
                "error": str(e),
                "redis_inserted": 0
            }

