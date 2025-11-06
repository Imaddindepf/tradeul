"""
Intraday High/Low Tracker

Mantiene el máximo y mínimo intradiario para cada ticker,
incluyendo pre-market, market hours y post-market.

Características:
- Tracking en memoria (cero latencia)
- Recuperación desde Polygon API al reiniciar
- Fallback a day.h/day.l si falla la recuperación
- Reseteo automático cada día
"""

import structlog
from datetime import datetime, date, time
from typing import Dict, List, Optional, Tuple
import httpx
import os

logger = structlog.get_logger(__name__)


class IntradayTracker:
    """
    Rastrea high/low intradiario para cada ticker
    """
    
    def __init__(self, polygon_api_key: str):
        """
        Inicializa el tracker
        
        Args:
            polygon_api_key: API key de Polygon para recuperación
        """
        self.polygon_api_key = polygon_api_key
        self.cache: Dict[str, Dict] = {}  # {symbol: {high, low, date}}
        self.current_date = date.today()
        
        logger.info("intraday_tracker_initialized")
    
    def update(self, symbol: str, price: float) -> Dict:
        """
        Actualiza high/low para un símbolo
        
        Args:
            symbol: Ticker symbol
            price: Precio actual
            
        Returns:
            Dict con high/low actualizado
        """
        if not price or price <= 0:
            return self.cache.get(symbol, {})
        
        today = date.today()
        
        # Resetear cache si es un nuevo día
        if today != self.current_date:
            logger.info("new_trading_day", old_date=self.current_date, new_date=today)
            self.cache.clear()
            self.current_date = today
        
        # Inicializar o actualizar
        if symbol not in self.cache:
            self.cache[symbol] = {
                "high": price,
                "low": price,
                "date": today.isoformat(),
                "updated": datetime.now().isoformat()
            }
        else:
            data = self.cache[symbol]
            
            # Actualizar high
            if price > data["high"]:
                data["high"] = price
                data["high_time"] = datetime.now().strftime("%H:%M:%S")
            
            # Actualizar low
            if price < data["low"]:
                data["low"] = price
                data["low_time"] = datetime.now().strftime("%H:%M:%S")
            
            data["updated"] = datetime.now().isoformat()
        
        return self.cache[symbol]
    
    def get(self, symbol: str) -> Optional[Dict]:
        """
        Obtiene high/low para un símbolo
        
        Args:
            symbol: Ticker symbol
            
        Returns:
            Dict con high/low o None si no existe
        """
        return self.cache.get(symbol)
    
    def get_batch(self, symbols: List[str]) -> Dict[str, Dict]:
        """
        Obtiene high/low para múltiples símbolos
        
        Args:
            symbols: Lista de ticker symbols
            
        Returns:
            Dict {symbol: {high, low}}
        """
        return {
            symbol: self.cache[symbol]
            for symbol in symbols
            if symbol in self.cache
        }
    
    async def _recover_single_symbol(
        self,
        symbol: str,
        from_ts: int,
        to_ts: int,
        today: date
    ) -> Optional[Dict]:
        """
        Recupera high/low para UN SOLO símbolo
        Usado por recover_from_polygon para procesamiento paralelo
        
        Args:
            symbol: Ticker symbol
            from_ts: Unix timestamp (ms) inicio
            to_ts: Unix timestamp (ms) fin
            today: Fecha actual
            
        Returns:
            Dict con high/low o None si falla
        """
        try:
            url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/minute/{from_ts}/{to_ts}"
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, params={
                    "apiKey": self.polygon_api_key,
                    "adjusted": "true",
                    "sort": "asc"
                })
                
                if resp.status_code != 200:
                    logger.warning(
                        "polygon_recovery_failed",
                        symbol=symbol,
                        status=resp.status_code
                    )
                    return None
                
                data = resp.json()
                results = data.get("results", [])
                
                if not results:
                    logger.debug("no_intraday_data", symbol=symbol)
                    return None
                
                # Extraer TODOS los highs y lows
                highs = [bar["h"] for bar in results if "h" in bar and bar["h"]]
                lows = [bar["l"] for bar in results if "l" in bar and bar["l"]]
                
                if not highs or not lows:
                    return None
                
                intraday_high = max(highs)
                intraday_low = min(lows)
                
                # Encontrar cuándo ocurrió el máximo
                max_bar = max(results, key=lambda x: x.get("h", 0))
                max_time = datetime.fromtimestamp(max_bar["t"] / 1000)
                
                # Encontrar cuándo ocurrió el mínimo
                min_bar = min(results, key=lambda x: x.get("l", float('inf')))
                min_time = datetime.fromtimestamp(min_bar["t"] / 1000)
                
                return {
                    "high": intraday_high,
                    "low": intraday_low,
                    "high_time": max_time.strftime("%H:%M:%S"),
                    "low_time": min_time.strftime("%H:%M:%S"),
                    "date": today.isoformat(),
                    "recovered": True,
                    "bars_count": len(results)
                }
        
        except Exception as e:
            logger.error("recovery_error", symbol=symbol, error=str(e))
            return None
    
    async def recover_from_polygon(
        self,
        symbols: List[str],
        max_symbols: int = 100,
        batch_size: int = 10
    ) -> Dict[str, Dict]:
        """
        Recupera high/low intradiario desde Polygon API EN PARALELO
        Usado al reiniciar el servicio durante el día de trading
        
        Args:
            symbols: Lista de símbolos a recuperar
            max_symbols: Máximo de símbolos a recuperar (rate limit)
            batch_size: Número de símbolos a procesar en paralelo por batch
            
        Returns:
            Dict {symbol: {high, low, recovered: True}}
        """
        today = date.today()
        
        # Solo recuperar si estamos en día de trading
        if today.weekday() >= 5:  # Sábado o Domingo
            logger.info("weekend_no_recovery_needed")
            return {}
        
        # Desde las 4 AM de hoy hasta ahora
        start_time = datetime.combine(today, time(4, 0))
        end_time = datetime.now()
        
        # Si es antes de las 4 AM, no hay nada que recuperar
        if end_time < start_time:
            logger.info("before_premarket_no_recovery_needed")
            return {}
        
        # Formato para Polygon API (Unix milliseconds)
        from_ts = int(start_time.timestamp() * 1000)
        to_ts = int(end_time.timestamp() * 1000)
        
        # Limitar símbolos para no saturar API
        symbols_to_recover = symbols[:max_symbols]
        
        logger.info(
            "starting_polygon_recovery_parallel",
            total_symbols=len(symbols),
            recovering=len(symbols_to_recover),
            batch_size=batch_size,
            from_time=start_time.strftime("%H:%M"),
            to_time=end_time.strftime("%H:%M")
        )
        
        recovered = {}
        failed = 0
        
        # Procesar en batches paralelos
        import asyncio
        
        for i in range(0, len(symbols_to_recover), batch_size):
            batch = symbols_to_recover[i:i+batch_size]
            
            logger.debug(
                "processing_batch",
                batch_num=i//batch_size + 1,
                batch_size=len(batch)
            )
            
            # Crear tareas para el batch
            tasks = [
                self._recover_single_symbol(symbol, from_ts, to_ts, today)
                for symbol in batch
            ]
            
            # Ejecutar batch EN PARALELO
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Procesar resultados
            for symbol, result in zip(batch, results):
                if isinstance(result, Exception):
                    logger.error("recovery_exception", symbol=symbol, error=str(result))
                    failed += 1
                elif result is not None:
                    recovered[symbol] = result
                    # Cargar en cache
                    self.cache[symbol] = result
                    logger.debug(
                        "intraday_recovered",
                        symbol=symbol,
                        high=result["high"],
                        low=result["low"],
                        bars=result["bars_count"]
                    )
                else:
                    failed += 1
        
        logger.info(
            "polygon_recovery_complete",
            recovered_count=len(recovered),
            failed_count=failed,
            total_attempted=len(symbols_to_recover),
            success_rate=f"{len(recovered)/len(symbols_to_recover)*100:.1f}%"
        )
        
        return recovered
    
    async def recover_active_symbols(
        self,
        active_symbols: List[str],
        max_symbols: int = 100
    ) -> int:
        """
        Recupera datos para símbolos activos al iniciar el servicio
        
        Args:
            active_symbols: Lista de símbolos activos (con volumen hoy)
            max_symbols: Máximo de símbolos a recuperar
            
        Returns:
            Número de símbolos recuperados
        """
        if not active_symbols:
            logger.info("no_active_symbols_to_recover")
            return 0
        
        try:
            recovered = await self.recover_from_polygon(
                symbols=active_symbols,
                max_symbols=max_symbols
            )
            return len(recovered)
        except Exception as e:
            logger.error("recovery_failed", error=str(e))
            return 0
    
    def get_stats(self) -> Dict:
        """
        Obtiene estadísticas del tracker
        
        Returns:
            Dict con estadísticas
        """
        return {
            "cached_symbols": len(self.cache),
            "current_date": self.current_date.isoformat(),
            "memory_kb": len(str(self.cache)) / 1024
        }

