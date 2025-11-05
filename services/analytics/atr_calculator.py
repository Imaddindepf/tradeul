"""
ATR Calculator - Average True Range

Calcula la volatilidad usando True Range de los últimos N períodos.
ATR es un indicador de volatilidad que mide el rango promedio de movimiento del precio.

Fórmula:
- True Range (TR) = max(high - low, abs(high - prev_close), abs(low - prev_close))
- ATR = EMA(TR, period) o SMA(TR, period) para el primer cálculo

Uso:
- Volatilidad: ATR alto = alta volatilidad
- Stop Loss: 2x ATR es común
- Position Sizing: ajustar tamaño según ATR
"""

import asyncio
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
import structlog
from zoneinfo import ZoneInfo

from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient

logger = structlog.get_logger(__name__)


class ATRCalculator:
    """
    Calculador de ATR (Average True Range)
    
    Calcula la volatilidad promedio usando True Range de los últimos N días.
    Soporta cálculo batch para múltiples símbolos y caché en Redis.
    """
    
    def __init__(
        self,
        redis_client: Optional[RedisClient] = None,
        timescale_client: Optional[TimescaleClient] = None,
        period: int = 14,
        use_ema: bool = True
    ):
        """
        Inicializa el calculador de ATR
        
        Args:
            redis_client: Cliente de Redis para caché (opcional)
            timescale_client: Cliente de TimescaleDB para histórico
            period: Número de períodos para el ATR (default 14)
            use_ema: Si usar EMA en vez de SMA (default True, más preciso)
        """
        self.redis = redis_client
        self.db = timescale_client
        self.period = period
        self.use_ema = use_ema
        
        # Caché de ATR en Redis
        # Key: "atr:daily:{symbol}" → {"atr": 2.45, "atr_percent": 3.2, "updated": "2025-11-05"}
        self.cache_prefix = "atr:daily"
        self.cache_ttl = 86400  # 24 horas
        
        logger.info(
            "atr_calculator_initialized",
            period=period,
            use_ema=use_ema,
            cache_enabled=redis_client is not None
        )
    
    def calculate_true_range(
        self,
        high: float,
        low: float,
        prev_close: Optional[float]
    ) -> float:
        """
        Calcula True Range para un período
        
        TR = max(high - low, abs(high - prev_close), abs(low - prev_close))
        
        Si no hay prev_close (primer día), TR = high - low
        """
        if prev_close is None:
            return high - low
        
        return max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close)
        )
    
    def calculate_atr_from_bars(
        self,
        bars: List[Dict],
        current_price: Optional[float] = None
    ) -> Optional[Dict[str, float]]:
        """
        Calcula ATR desde una lista de barras OHLC
        
        Args:
            bars: Lista de dicts con keys: high, low, close (ordenados por fecha)
            current_price: Precio actual para calcular atr_percent
        
        Returns:
            Dict con atr, atr_percent o None si no hay suficientes datos
        """
        if len(bars) < self.period:
            logger.warning(
                "insufficient_bars_for_atr",
                bars_count=len(bars),
                required=self.period
            )
            return None
        
        # Calcular True Range para cada barra
        true_ranges = []
        prev_close = None
        
        for bar in bars:
            tr = self.calculate_true_range(
                high=bar['high'],
                low=bar['low'],
                prev_close=prev_close
            )
            true_ranges.append(tr)
            prev_close = bar['close']
        
        # Calcular ATR
        if self.use_ema:
            # EMA del True Range
            atr = self._calculate_ema(true_ranges, self.period)
        else:
            # SMA del True Range (más simple)
            atr = sum(true_ranges[-self.period:]) / self.period
        
        # Calcular ATR como % del precio
        atr_percent = None
        if current_price and current_price > 0:
            atr_percent = (atr / current_price) * 100
        elif prev_close and prev_close > 0:
            atr_percent = (atr / prev_close) * 100
        
        return {
            "atr": round(atr, 4),
            "atr_percent": round(atr_percent, 2) if atr_percent else None
        }
    
    def _calculate_ema(self, values: List[float], period: int) -> float:
        """
        Calcula EMA (Exponential Moving Average)
        
        EMA = (value * multiplier) + (previous_ema * (1 - multiplier))
        multiplier = 2 / (period + 1)
        """
        if len(values) < period:
            return sum(values) / len(values)
        
        # Primer EMA es SMA
        ema = sum(values[:period]) / period
        multiplier = 2 / (period + 1)
        
        # Aplicar EMA al resto de valores
        for value in values[period:]:
            ema = (value * multiplier) + (ema * (1 - multiplier))
        
        return ema
    
    async def calculate_atr(
        self,
        symbol: str,
        current_price: Optional[float] = None,
        trading_date: Optional[date] = None
    ) -> Optional[Dict[str, float]]:
        """
        Calcula ATR para un símbolo individual
        
        Args:
            symbol: Símbolo del ticker
            current_price: Precio actual para calcular atr_percent
            trading_date: Fecha de trading (default: hoy)
        
        Returns:
            Dict con atr, atr_percent o None si no hay datos
        """
        if trading_date is None:
            trading_date = date.today()
        
        # Intentar obtener de caché primero
        if self.redis:
            cached = await self._get_from_cache(symbol)
            if cached:
                # Actualizar atr_percent con precio actual si se provee
                if current_price and current_price > 0:
                    cached['atr_percent'] = round((cached['atr'] / current_price) * 100, 2)
                return cached
        
        # Calcular desde TimescaleDB
        if not self.db:
            logger.error("no_timescale_client", symbol=symbol)
            return None
        
        # Obtener últimos N+1 días (necesitamos prev_close del día anterior)
        lookback_days = self.period + 5  # +5 días extra por si hay gaps
        start_date = trading_date - timedelta(days=lookback_days * 2)  # x2 para weekends
        
        query = """
            SELECT 
                trading_date,
                high,
                low,
                close
            FROM market_data_daily
            WHERE symbol = $1
                AND trading_date >= $2
                AND trading_date <= $3
            ORDER BY trading_date ASC
            LIMIT $4
        """
        
        try:
            rows = await self.db.fetch(
                query,
                symbol,
                start_date,
                trading_date,
                self.period + 10
            )
            
            if len(rows) < self.period:
                logger.warning(
                    "insufficient_historical_data",
                    symbol=symbol,
                    rows=len(rows),
                    required=self.period
                )
                return None
            
            # Convertir a formato de barras
            bars = [
                {
                    'high': float(row['high']),
                    'low': float(row['low']),
                    'close': float(row['close'])
                }
                for row in rows
            ]
            
            # Calcular ATR
            result = self.calculate_atr_from_bars(bars, current_price)
            
            # Guardar en caché
            if result and self.redis:
                await self._save_to_cache(symbol, result)
            
            return result
            
        except Exception as e:
            logger.error(
                "atr_calculation_error",
                symbol=symbol,
                error=str(e)
            )
            return None
    
    async def calculate_atr_batch(
        self,
        symbols: List[str],
        current_prices: Optional[Dict[str, float]] = None,
        trading_date: Optional[date] = None
    ) -> Dict[str, Optional[Dict[str, float]]]:
        """
        Calcula ATR para múltiples símbolos en batch
        
        Args:
            symbols: Lista de símbolos
            current_prices: Dict de precios actuales {symbol: price}
            trading_date: Fecha de trading (default: hoy)
        
        Returns:
            Dict {symbol: {atr, atr_percent}} o {symbol: None} si no hay datos
        """
        if not symbols:
            return {}
        
        results = {}
        
        # Intentar obtener de caché primero (batch)
        if self.redis:
            cached_results = await self._get_batch_from_cache(symbols)
            
            # Actualizar atr_percent con precios actuales
            if current_prices:
                for symbol, data in cached_results.items():
                    if data and symbol in current_prices:
                        price = current_prices[symbol]
                        if price and price > 0:
                            data['atr_percent'] = round((data['atr'] / price) * 100, 2)
            
            results.update(cached_results)
        
        # Símbolos que no están en caché
        missing_symbols = [s for s in symbols if s not in results]
        
        if missing_symbols and self.db:
            # Calcular en paralelo para símbolos faltantes
            tasks = [
                self.calculate_atr(
                    symbol,
                    current_prices.get(symbol) if current_prices else None,
                    trading_date
                )
                for symbol in missing_symbols
            ]
            
            calculated = await asyncio.gather(*tasks, return_exceptions=True)
            
            for symbol, result in zip(missing_symbols, calculated):
                if isinstance(result, Exception):
                    logger.error("atr_batch_error", symbol=symbol, error=str(result))
                    results[symbol] = None
                else:
                    results[symbol] = result
        
        return results
    
    async def _get_from_cache(self, symbol: str) -> Optional[Dict[str, float]]:
        """Obtiene ATR de caché de Redis"""
        if not self.redis:
            return None
        
        key = f"{self.cache_prefix}:{symbol}"
        try:
            data = await self.redis.get(key)
            if data:
                return {
                    'atr': float(data.get('atr', 0)),
                    'atr_percent': float(data.get('atr_percent', 0)) if data.get('atr_percent') else None
                }
        except Exception as e:
            logger.error("cache_read_error", symbol=symbol, error=str(e))
        
        return None
    
    async def _get_batch_from_cache(
        self,
        symbols: List[str]
    ) -> Dict[str, Optional[Dict[str, float]]]:
        """Obtiene ATR de múltiples símbolos de caché (batch)"""
        if not self.redis or not symbols:
            return {}
        
        keys = [f"{self.cache_prefix}:{symbol}" for symbol in symbols]
        
        try:
            values = await self.redis.mget(keys)
            results = {}
            
            for symbol, data in zip(symbols, values):
                if data:
                    results[symbol] = {
                        'atr': float(data.get('atr', 0)),
                        'atr_percent': float(data.get('atr_percent', 0)) if data.get('atr_percent') else None
                    }
            
            return results
            
        except Exception as e:
            logger.error("cache_batch_read_error", error=str(e))
            return {}
    
    async def _save_to_cache(self, symbol: str, data: Dict[str, float]):
        """Guarda ATR en caché de Redis"""
        if not self.redis:
            return
        
        key = f"{self.cache_prefix}:{symbol}"
        try:
            await self.redis.setex(
                key,
                self.cache_ttl,
                {
                    'atr': data['atr'],
                    'atr_percent': data['atr_percent'],
                    'updated': date.today().isoformat()
                }
            )
        except Exception as e:
            logger.error("cache_write_error", symbol=symbol, error=str(e))

