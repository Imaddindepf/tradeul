"""
Calculate Trades Baselines Task
===============================

Pre-calcula baselines de trades (avg, std) para detección de anomalías.
Guarda en Redis para acceso ultra-rápido desde Analytics.

CONCEPTO:
- trades_count = número de transacciones por día (Polygon field "n")
- avg_trades_5d = promedio de trades/día de los últimos 5 días de trading
- std_trades_5d = desviación estándar de trades/día

DETECCIÓN DE ANOMALÍAS:
- Z-Score = (trades_hoy - avg_trades_5d) / std_trades_5d
- Si Z-Score >= 3.0 → ANOMALÍA ESTADÍSTICA (99.7% probabilidad)

ALMACENAMIENTO:
- Redis HASH: trades:baseline:{symbol}:{days} → {avg: "X", std: "Y"}
- TTL: 14 horas (suficiente para día de trading)
- Se limpia y recalcula cada noche

EJEMPLO REAL:
- BIVI: avg_trades_5d = 660, std = 156
- BIVI hoy: trades = 159,263
- Z-Score = (159263 - 660) / 156 = 1015.78 → 🔥 ANOMALÍA EXTREMA
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


class CalculateTradesBaselinesTask:
    """
    Tarea: Calcular baselines de trades para detección de anomalías
    
    Proceso:
    1. Vaciar Redis de baselines antiguos (trades:baseline:*)
    2. Obtener símbolos activos del universo
    3. Para cada símbolo:
       - Calcular suma de trades_count por día (últimos N días)
       - Calcular promedio y desviación estándar
       - Guardar en Redis hash trades:baseline:{symbol}:{days}
    4. TTL en Redis: 14 horas
    
    Se ejecuta durante el mantenimiento nocturno (3:00 AM ET)
    """
    
    name = "calculate_trades_baselines"
    
    def __init__(self, redis_client: RedisClient, timescale_client: TimescaleClient):
        self.redis = redis_client
        self.db = timescale_client
        
        # Configuración
        self.lookback_days = 5  # N días históricos para baseline
        self.batch_size = 100   # Procesar símbolos en lotes
        self.redis_ttl = 50400  # 14 horas TTL
        self.min_days_required = 3  # Mínimo 3 días para baseline válido
    
    async def execute(self, target_date: date) -> Dict:
        """
        Ejecutar cálculo de baselines de trades
        
        Args:
            target_date: Fecha objetivo (para logging)
        
        Returns:
            Dict con resultado
        """
        logger.info(
            "trades_baselines_task_starting",
            lookback_days=self.lookback_days,
            target_date=str(target_date)
        )
        
        try:
            # 1. Vaciar Redis de baselines antiguos
            await self._clear_redis_baselines()
            
            # 2. Obtener símbolos activos con datos de trades
            symbols = await self._get_symbols_with_trades_data()
            
            if not symbols:
                logger.warning("no_symbols_with_trades_data")
                return {
                    "success": False,
                    "error": "No symbols with trades data found"
                }
            
            logger.info(
                "trades_baselines_symbols_loaded",
                count=len(symbols)
            )
            
            # 3. Calcular baselines en lotes
            total_processed = 0
            total_redis_inserted = 0
            
            for i in range(0, len(symbols), self.batch_size):
                batch = symbols[i:i + self.batch_size]
                batch_num = (i // self.batch_size) + 1
                total_batches = (len(symbols) + self.batch_size - 1) // self.batch_size
                
                if batch_num % 10 == 0 or batch_num == 1:
                    logger.info(
                        "processing_batch",
                        batch=batch_num,
                        total_batches=total_batches,
                        batch_size=len(batch)
                    )
                
                # Procesar batch en paralelo
                semaphore = asyncio.Semaphore(50)  # Max 50 concurrent
                
                async def process_symbol(symbol: str):
                    async with semaphore:
                        return await self._calculate_and_save_baseline(symbol)
                
                tasks = [process_symbol(sym) for sym in batch]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Contar resultados
                for result in results:
                    if isinstance(result, Exception):
                        logger.error(
                            "symbol_processing_error",
                            error=str(result)
                        )
                    elif isinstance(result, dict) and result.get("success"):
                        total_processed += 1
                        total_redis_inserted += 1
            
            logger.info(
                "trades_baselines_task_completed",
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
                "trades_baselines_task_failed",
                error=str(e)
            )
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _clear_redis_baselines(self):
        """Vaciar Redis de baselines de trades antiguos"""
        try:
            pattern = "trades:baseline:*"
            deleted = await self.redis.delete_pattern(pattern)
            logger.info(
                "redis_baselines_cleared",
                pattern=pattern,
                deleted_count=deleted
            )
        except Exception as e:
            logger.warning(
                "redis_clear_failed",
                error=str(e)
            )
    
    async def _get_symbols_with_trades_data(self) -> List[str]:
        """
        Obtener símbolos que tienen datos de trades_count en volume_slots
        Solo símbolos con al menos 3 días de datos
        """
        try:
            query = """
                SELECT symbol
                FROM (
                    SELECT symbol, COUNT(DISTINCT date) as days_count
                    FROM volume_slots
                    WHERE trades_count IS NOT NULL 
                      AND trades_count > 0
                      AND date >= CURRENT_DATE - INTERVAL '10 days'
                    GROUP BY symbol
                    HAVING COUNT(DISTINCT date) >= $1
                ) sub
                ORDER BY symbol
            """
            rows = await self.db.fetch(query, self.min_days_required)
            return [row['symbol'] for row in rows]
        except Exception as e:
            logger.error("failed_to_get_symbols", error=str(e))
            return []
    
    async def _calculate_and_save_baseline(self, symbol: str) -> Dict:
        """
        Calcular y guardar baseline para un símbolo
        
        Query:
        - Suma trades_count por día para los últimos N días de trading
        - Calcula AVG y STDDEV de esos totales diarios
        """
        try:
            sym = symbol.upper()
            
            # Query: Obtener estadísticas de trades diarios
            query = """
                WITH trading_days AS (
                    SELECT DISTINCT date
                    FROM volume_slots
                    WHERE symbol = $1 
                      AND date < CURRENT_DATE
                      AND trades_count IS NOT NULL
                      AND trades_count > 0
                    ORDER BY date DESC
                    LIMIT $2
                ),
                daily_trades AS (
                    SELECT 
                        vs.date,
                        SUM(vs.trades_count) as total_trades
                    FROM volume_slots vs
                    JOIN trading_days td ON vs.date = td.date
                    WHERE vs.symbol = $1
                    GROUP BY vs.date
                )
                SELECT 
                    AVG(total_trades) as avg_trades,
                    COALESCE(STDDEV(total_trades), 0) as std_trades,
                    COUNT(*) as days_count
                FROM daily_trades
            """
            
            result = await self.db.fetchrow(query, sym, self.lookback_days)
            
            if not result or result['avg_trades'] is None:
                return {
                    "success": False,
                    "error": "No historical trades data"
                }
            
            avg_trades = float(result['avg_trades'])
            std_trades = float(result['std_trades'] or 0)
            days_count = int(result['days_count'])
            
            # Solo guardar si tenemos suficientes días
            if days_count < self.min_days_required:
                return {
                    "success": False,
                    "error": f"Insufficient days: {days_count}"
                }
            
            # Guardar en Redis HASH
            hash_key = f"trades:baseline:{sym}:{self.lookback_days}"
            try:
                await self.redis.client.hset(hash_key, mapping={
                    'avg': str(round(avg_trades, 2)),
                    'std': str(round(std_trades, 2)),
                    'days': str(days_count)
                })
                await self.redis.expire(hash_key, self.redis_ttl)
                
                return {
                    "success": True,
                    "avg_trades": avg_trades,
                    "std_trades": std_trades,
                    "days_count": days_count
                }
                
            except Exception as e:
                logger.error(
                    "redis_insert_failed",
                    symbol=sym,
                    error=str(e)
                )
                return {
                    "success": False,
                    "error": str(e)
                }
        
        except Exception as e:
            logger.error(
                "calculate_baseline_error",
                symbol=symbol,
                error=str(e)
            )
            return {
                "success": False,
                "error": str(e)
            }

