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

# El TTL es SOLO una red de recogida de basura, no el mecanismo de frescura:
# la frescura la da el recálculo de cada día de trading. Con TTL de 24 h y un
# camino "cached" que no lo renovaba, las claves morían a mitad de la
# madrugada y el mercado abría sin ATR: días completos en blanco (22 y 29 de
# julio de 2026, medidos en el lake de eventos). El margen cubre un fin de
# semana largo sin mantenimiento.
ATR_TTL_SECONDS = 5 * 24 * 3600

# Fecha de referencia ya calculada. Permite reejecutar el mismo día sin
# recalcular y fuerza el recálculo en cuanto cambia el día de trading.
ATR_DATE_KEY = "atr:calc_date"


def _as_text(value) -> Optional[str]:
    """Normaliza lo que devuelve RedisClient.get a str (puede venir en bytes)."""
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode(errors="ignore")
    return str(value)


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

        # 2. ¿Hay que recalcular?
        #    La decisión NO puede depender de la fecha que pase cada llamador:
        #    el orquestador pasa el último día de trading y el refresco de
        #    baselines pasa hoy, y ambos producen el MISMO ATR (a las 3 AM la
        #    sesión de hoy aún no existe). Normalizamos a la última sesión con
        #    datos <= reference_date: así las dos pasadas de la madrugada no
        #    recalculan dos veces lo mismo.
        effective_date = await self._effective_data_date(reference_date)
        last_calc = _as_text(await self.redis.get(ATR_DATE_KEY))
        recompute = last_calc != effective_date.isoformat()

        logger.info(
            "atr_recompute_decision",
            reference_date=str(reference_date),
            effective_date=str(effective_date),
            last_calc_date=last_calc,
            recompute=recompute
        )

        # 3. Calcular ATR para cada símbolo
        calculated = 0
        cached = 0
        failed = 0

        # Procesar en batches
        batch_size = 200
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i + batch_size]

            tasks = [
                self._calculate_symbol_atr(sym, reference_date, recompute)
                for sym in batch
            ]
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
        
        # 4. Verificar resultado
        total_valid = calculated + cached
        success = total_valid >= MIN_ATR_SUCCESS

        # 5. Sellar la sesión calculada. Con el mismo TTL que los valores: si
        #    la marca desaparece, la próxima ejecución recalcula todo.
        if success:
            await self.redis.set(
                ATR_DATE_KEY, effective_date.isoformat(), ttl=ATR_TTL_SECONDS
            )

        logger.info(
            "atr_calculator_completed",
            calculated=calculated,
            cached=cached,
            failed=failed,
            total_valid=total_valid,
            recomputed=recompute,
            success=success
        )

        return {
            "success": success,
            "calculated": calculated,
            "cached": cached,
            "failed": failed,
            "total_valid": total_valid,
            "recomputed": recompute
        }
    
    async def _effective_data_date(self, reference_date: date) -> date:
        """Última sesión con datos <= reference_date (la que determina el ATR)."""
        try:
            rows = await self.db.fetch(
                """
                SELECT MAX(trading_date) AS d
                FROM market_data_daily
                WHERE trading_date <= $1
                """,
                reference_date
            )
            if rows and rows[0]["d"]:
                return rows[0]["d"]
        except Exception as e:
            logger.warning("effective_data_date_failed", error=str(e))
        return reference_date

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
        reference_date: date,
        recompute: bool = True
    ) -> Optional[str]:
        """
        Calcular ATR para un símbolo

        Returns:
            - "cached" si ya existe en cache (con el TTL renovado)
            - "calculated" si se calculó nuevo
            - None si falló
        """
        try:
            cache_key = f"atr:{symbol}"

            if not recompute:
                # Reejecución del mismo día de referencia. No recalculamos,
                # pero SÍ renovamos el TTL: devolver "cached" sin renovarlo
                # era la causa de los días enteros sin ATR.
                if await self.redis.exists(cache_key):
                    await self.redis.expire(cache_key, ATR_TTL_SECONDS)
                    return "cached"
                # Si no está en caché, se calcula igualmente (autocuración).

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
            
            # Guardar en Redis. El valor es un número plano a propósito:
            # shared/utils/atr_calculator._get_batch_from_cache lo lee con
            # float() por el camino de claves individuales.
            await self.redis.set(cache_key, str(round(atr, 4)), ttl=ATR_TTL_SECONDS)

            return "calculated"
            
        except Exception as e:
            logger.debug(f"ATR calculation failed for {symbol}: {e}")
            return None

