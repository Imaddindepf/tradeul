"""
ATR Calculator
==============

Calcula Average True Range (ATR) para todos los tickers activos.

El ATR se calcula como:
ATR = SMA(True Range, 14 días)

True Range = max(
    high - low,
    abs(high - prev_close),
    abs(low - prev_close)
)

Los resultados se almacenan en Redis para acceso rápido durante el día.
"""

import asyncio
from datetime import date
from typing import Dict, List, Optional
from decimal import Decimal

import sys
sys.path.append('/app')

from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import get_logger

logger = get_logger(__name__)

# Mínimo de ATRs para considerar exitoso
MIN_ATR_SUCCESS = 8000
ATR_PERIOD = 14


class ATRCalculatorTask:
    """
    Calculador de ATR para todos los tickers
    """
    
    def __init__(self, redis_client: RedisClient, timescale_client: TimescaleClient):
        self.redis = redis_client
        self.db = timescale_client
    
    async def calculate_all(self, reference_date: date) -> Dict:
        """
        Calcular ATR para todos los tickers activos
        
        Args:
            reference_date: Fecha de referencia (usa datos hasta esta fecha)
            
        Returns:
            Dict con resultado
        """
        logger.info("atr_calculator_starting", reference_date=str(reference_date))
        
        # 1. Obtener símbolos activos
        symbols = await self._get_active_symbols()
        
        if not symbols:
            return {
                "success": False,
                "error": "No active symbols found"
            }
        
        logger.info("atr_calculating_for_symbols", count=len(symbols))
        
        # 2. Calcular ATR para cada símbolo
        calculated = 0
        cached = 0
        failed = 0
        
        # Procesar en batches
        batch_size = 200
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i + batch_size]
            
            tasks = [self._calculate_symbol_atr(sym, reference_date) for sym in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, Exception):
                    failed += 1
                elif result is None:
                    failed += 1
                elif result == "cached":
                    cached += 1
                else:
                    calculated += 1
        
        # 3. Verificar resultado
        total_valid = calculated + cached
        success = total_valid >= MIN_ATR_SUCCESS
        
        logger.info(
            "atr_calculator_completed",
            calculated=calculated,
            cached=cached,
            failed=failed,
            total_valid=total_valid,
            success=success
        )
        
        return {
            "success": success,
            "calculated": calculated,
            "cached": cached,
            "failed": failed,
            "total_valid": total_valid
        }
    
    async def _get_active_symbols(self) -> List[str]:
        """Obtener símbolos activos con datos recientes"""
        query = """
            SELECT t.symbol
            FROM tickers_unified t
            WHERE t.is_actively_trading = true
            AND EXISTS (
                SELECT 1 FROM market_data_daily m 
                WHERE m.symbol = t.symbol 
                AND m.trading_date > CURRENT_DATE - INTERVAL '30 days'
            )
            ORDER BY t.symbol
        """
        rows = await self.db.fetch(query)
        return [row["symbol"] for row in rows]
    
    async def _calculate_symbol_atr(
        self,
        symbol: str,
        reference_date: date
    ) -> Optional[str]:
        """
        Calcular ATR para un símbolo
        
        Returns:
            - "cached" si ya existe en cache
            - "calculated" si se calculó nuevo
            - None si falló
        """
        try:
            # Verificar cache
            cache_key = f"atr:{symbol}"
            cached = await self.redis.get(cache_key)
            
            if cached:
                return "cached"
            
            # Obtener datos históricos
            query = """
                SELECT open, high, low, close
                FROM market_data_daily
                WHERE symbol = $1
                AND trading_date <= $2
                ORDER BY trading_date DESC
                LIMIT $3
            """
            
            rows = await self.db.fetch(query, symbol, reference_date, ATR_PERIOD + 1)
            
            if len(rows) < ATR_PERIOD:
                return None
            
            # Calcular True Range para cada día
            true_ranges = []
            
            for i in range(len(rows) - 1):
                current = rows[i]
                prev = rows[i + 1]
                
                high = float(current["high"])
                low = float(current["low"])
                prev_close = float(prev["close"])
                
                tr = max(
                    high - low,
                    abs(high - prev_close),
                    abs(low - prev_close)
                )
                
                true_ranges.append(tr)
            
            if len(true_ranges) < ATR_PERIOD:
                return None
            
            # ATR = SMA de True Ranges
            atr = sum(true_ranges[:ATR_PERIOD]) / ATR_PERIOD
            
            if atr <= 0:
                return None
            
            # Guardar en Redis (TTL 24 horas)
            await self.redis.set(cache_key, str(round(atr, 4)), ttl=86400)
            
            return "calculated"
            
        except Exception as e:
            logger.debug(f"ATR calculation failed for {symbol}: {e}")
            return None

