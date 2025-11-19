"""
RVOL Calculator - Cálculo Preciso de Relative Volume

Este módulo implementa el cálculo de RVOL siguiendo la lógica
de PineScript, usando slots temporales y promedios históricos.
"""

import asyncio
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
import structlog
from zoneinfo import ZoneInfo
import httpx
import re

from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from slot_manager import SlotManager, VolumeSlotCache

logger = structlog.get_logger(__name__)


class RVOLCalculator:
    """
    Calculador de RVOL (Relative Volume) por slots
    
    Implementa la lógica de PineScript:
    - Divide el día en slots de N minutos
    - Calcula volumen acumulado por slot
    - Compara con promedio histórico del mismo slot
    - Maneja datos faltantes (busca slots anteriores)
    """
    
    def __init__(
        self,
        redis_client: RedisClient,
        timescale_client: TimescaleClient,
        slot_size_minutes: int = 5,
        lookback_days: int = 5,
        include_extended_hours: bool = True
    ):
        """
        Inicializa el calculador de RVOL
        
        Args:
            redis_client: Cliente de Redis para caché
            timescale_client: Cliente de TimescaleDB para histórico
            slot_size_minutes: Tamaño del slot en minutos (default 5)
            lookback_days: Días históricos a considerar (default 5)
            include_extended_hours: Si incluir pre/post market (default True)
        """
        self.redis = redis_client
        self.db = timescale_client
        self.lookback_days = lookback_days
        
        # Inicializar gestor de slots (con soporte de extended hours)
        self.slot_manager = SlotManager(
            slot_size_minutes=slot_size_minutes,
            include_extended_hours=include_extended_hours
        )
        
        # Caché de volúmenes del día actual
        self.volume_cache = VolumeSlotCache()
        
        # Caché de promedios históricos en Redis (OPTIMIZADO CON HASHES)
        # Hash Key: "rvol:hist:avg:{symbol}:{days}" → {slot: avg_volume, ...}
        # Ejemplo: "rvol:hist:avg:AAPL:5" → {"0": "12345", "1": "23456", ...}
        self.hist_cache_prefix = "rvol:hist:avg"
        self.hist_cache_ttl = 28800  # 8 horas (suficiente para día de trading)
        
        # 🚀 FIX MEMORY LEAK: HTTP Client global reutilizable
        # Evita crear/destruir 500 clients por ciclo
        self.http_client = httpx.AsyncClient(
            timeout=8.0,
            limits=httpx.Limits(
                max_connections=20,  # Máximo 20 conexiones concurrentes
                max_keepalive_connections=5  # Mantener 5 conexiones abiertas
            )
        )
        
        # Patrón para detectar preferred stocks (BACPM → BACpM)
        # Fix del documento FIX_PREFERRED_STOCKS.md
        self.preferred_stock_pattern = re.compile(r'^[A-Z]{3,}P[A-Z]$')
        
        logger.info(
            "rvol_calculator_initialized",
            slot_size_minutes=slot_size_minutes,
            lookback_days=lookback_days,
            include_extended_hours=include_extended_hours,
            total_slots=self.slot_manager.total_slots,
            premarket_slots=self.slot_manager.premarket_slots,
            market_slots=self.slot_manager.market_slots,
            postmarket_slots=self.slot_manager.postmarket_slots,
            http_client_limits="max_connections=20, keepalive=5"
        )
    
    async def update_volume_for_symbol(
        self,
        symbol: str,
        volume_accumulated: int,
        timestamp: Optional[datetime] = None,
        vwap: float = 0.0
    ):
        """
        Actualiza el volumen acumulado para un símbolo
        
        IMPORTANTE: volume_accumulated debe venir de Polygon:
        - De Snapshots: usar snapshot.min.av (minute bar accumulated volume)
        - De WebSocket: usar agg.av (today's accumulated volume)
        
        Polygon proporciona el volumen YA ACUMULADO desde el inicio del día.
        NO calcular o sumar manualmente.
        
        Args:
            symbol: Ticker symbol
            volume_accumulated: Volumen acumulado del día (de Polygon min.av/av)
            timestamp: Timestamp actual (default: ahora)
            vwap: Volume Weighted Average Price (opcional, de Polygon)
        """
        if timestamp is None:
            timestamp = datetime.now(ZoneInfo("America/New_York"))
        
        # Obtener slot actual
        current_slot = self.slot_manager.get_current_slot(timestamp)
        
        if current_slot < 0:
            logger.debug(
                "outside_trading_hours_skip",
                symbol=symbol,
                timestamp=timestamp.isoformat()
            )
            return
        
        # Guardar volumen acumulado de Polygon en el slot actual
        self.volume_cache.update_volume(
            symbol=symbol,
            slot_number=current_slot,
            volume_accumulated=volume_accumulated,  # De Polygon: min.av o av
            vwap=vwap
        )
        
        logger.debug(
            "volume_updated_for_slot",
            symbol=symbol,
            slot=current_slot,
            volume=volume_accumulated
        )
    
    async def calculate_rvol(
        self,
        symbol: str,
        timestamp: Optional[datetime] = None
    ) -> Optional[float]:
        """
        Calcula el RVOL para un símbolo en el momento actual
        
        Implementa la lógica de PineScript:
        RVOL = volume_accumulated_today / avg_volume_historical
        
        Args:
            symbol: Ticker symbol
            timestamp: Timestamp actual (default: ahora)
        
        Returns:
            RVOL calculado o None si no hay datos suficientes
        """
        if timestamp is None:
            timestamp = datetime.now(ZoneInfo("America/New_York"))
        
        # Obtener slot actual
        current_slot = self.slot_manager.get_current_slot(timestamp)
        
        if current_slot < 0:
            return None
        
        # 1. Obtener volumen acumulado de hoy
        volume_today = self.volume_cache.get_volume(symbol, current_slot)
        
        if volume_today == 0:
            logger.debug(
                "no_volume_data_today",
                symbol=symbol,
                slot=current_slot
            )
            return None
        
        # 2. Obtener promedio histórico del mismo slot
        historical_avg = await self._get_historical_average_volume(
            symbol=symbol,
            slot_number=current_slot,
            target_date=timestamp.date()
        )
        
        if historical_avg == 0 or historical_avg is None:
            logger.debug(
                "no_historical_data",
                symbol=symbol,
                slot=current_slot
            )
            return None
        
        # 3. Calcular RVOL
        rvol = volume_today / historical_avg
        
        logger.debug(
            "rvol_calculated",
            symbol=symbol,
            slot=current_slot,
            volume_today=volume_today,
            historical_avg=historical_avg,
            rvol=round(rvol, 2)
        )
        
        return rvol
    
    async def calculate_rvol_direct(
        self,
        symbol: str,
        volume_today: int,
        timestamp: Optional[datetime] = None
    ) -> Optional[float]:
        """
        Calcula RVOL directamente con volumen dado (sin usar caché)
        
        Usado cuando tenemos el volumen del mensaje directamente.
        
        Args:
            symbol: Ticker symbol
            volume_today: Volumen acumulado hoy
            timestamp: Timestamp actual
        
        Returns:
            RVOL calculado o None
        """
        if timestamp is None:
            timestamp = datetime.now(ZoneInfo("America/New_York"))
        
        logger.debug(f"calculate_rvol_direct_called", symbol=symbol, volume_today=volume_today)
        
        if volume_today == 0:
            logger.debug(f"volume_today_is_zero", symbol=symbol)
            return None
        
        # Obtener slot actual
        current_slot = self.slot_manager.get_current_slot(timestamp)
        
        if current_slot < 0:
            return None
        
        try:
            # Obtener promedio histórico con timeout
            historical_avg = await asyncio.wait_for(
                self._get_historical_average_volume(
                    symbol=symbol,
                    slot_number=current_slot,
                    target_date=timestamp.date()
                ),
                timeout=2.0  # 2 segundos máximo
            )
            
            if historical_avg == 0 or historical_avg is None:
                return None
            
            # Calcular RVOL
            rvol = volume_today / historical_avg
            
            return rvol
        
        except asyncio.TimeoutError:
            logger.warning(f"timeout_calculating_rvol", symbol=symbol, slot=current_slot)
            return None
        except Exception as e:
            logger.error(f"error_calculating_rvol_direct", symbol=symbol, error=str(e))
            return None
    
    async def calculate_rvol_batch(
        self,
        symbols: List[str],
        timestamp: Optional[datetime] = None
    ) -> Dict[str, float]:
        """
        Calcula RVOL para múltiples símbolos en batch
        
        Args:
            symbols: Lista de ticker symbols
            timestamp: Timestamp actual (default: ahora)
        
        Returns:
            Dict {symbol: rvol}
        """
        results = {}
        
        for symbol in symbols:
            rvol = await self.calculate_rvol(symbol, timestamp)
            if rvol is not None:
                results[symbol] = rvol
        
        logger.info(
            "rvol_batch_calculated",
            symbols_count=len(symbols),
            results_count=len(results)
        )
        
        return results
    
    async def _get_historical_average_volume(
        self,
        symbol: str,
        slot_number: int,
        target_date: date
    ) -> Optional[float]:
        """
        Obtiene el promedio histórico de volumen acumulado para un slot.
        - Lee de Redis HASH primero (rvol:hist:avg:{SYMBOL}:{DAYS} -> field {slot})
        - En miss, llama al bulk de Historical para precalentar todos los slots del símbolo
          y vuelve a leer el slot concreto desde Redis.
        """
        sym = symbol.upper()
        days = self.lookback_days
        
        # 🛡️ FILTRO: Saltar preferred stocks (no tienen datos históricos consistentes)
        # Patrón: BACPM, WFCPC, PSAPO (3+ letras base + P + letra)
        if self.preferred_stock_pattern.match(sym):
            return None
        
        # 1) Redis HASH first (optimizado)
        hash_key = f"{self.hist_cache_prefix}:{sym}:{days}"
        try:
            cached_avg = await self.redis.hget(hash_key, str(slot_number))
            if cached_avg is not None:
                try:
                    return float(cached_avg)
                except (TypeError, ValueError):
                    return None
        except Exception:
            # Si falla hget, continuar con bulk
            pass

        # 2) Miss -> pedir bulk a Historical usando client global reutilizable
        try:
            historical_host = "http://historical:8004"
            url_bulk = f"{historical_host}/api/rvol/hist-avg/bulk"
            params = {"symbol": sym, "days": days, "max_slot": 250}
            
            # 🚀 FIX: Usar client global (NO crear nuevo cada vez)
            resp = await self.http_client.get(url_bulk, params=params)
            if resp.status_code not in (200, 201):
                return None
        except Exception:
            # Si falla el bulk, no insistimos
            return None

        # 3) Reintentar lectura del slot desde Redis HASH
        try:
            cached_avg = await self.redis.hget(hash_key, str(slot_number))
            if cached_avg is not None:
                try:
                    return float(cached_avg)
                except (TypeError, ValueError):
                    return None
        except Exception:
            pass
        
        return None
    
    async def _get_volume_for_slot(
        self,
        symbol: str,
        date: date,
        slot_number: int
    ) -> int:
        """
        Obtiene el volumen ACUMULADO hasta un slot específico desde TimescaleDB
        
        Según PineScript, necesitamos volumen acumulado desde inicio del día
        hasta ese slot, NO solo el volumen del slot.
        
        Args:
            symbol: Ticker symbol
            date: Fecha
            slot_number: Número del slot
        
        Returns:
            Volumen acumulado desde inicio del día hasta ese slot
        """
        # CRÍTICO: Los datos en volume_slots son volumen POR SLOT (5 min)
        # Necesitamos SUMAR todos los slots desde 0 hasta slot_number
        query = """
            SELECT COALESCE(SUM(volume_accumulated), 0) as total_volume
            FROM volume_slots
            WHERE symbol = $1 
              AND date = $2 
              AND slot_number <= $3
        """
        
        try:
            result = await self.db.fetchrow(query, symbol, date, slot_number)
            volume = int(result['total_volume']) if result else 0
            
            # DEBUG: Log para verificar cálculo
            if symbol in ['AAPL', 'RDDT', 'TSLA'] and volume > 0:
                logger.info(
                    "volume_for_slot_calculated",
                    symbol=symbol,
                    date=str(date),
                    slot=slot_number,
                    volume_accumulated=volume
                )
            
            return volume
        except Exception as e:
            logger.error(
                "error_fetching_slot_volume",
                symbol=symbol,
                date=str(date),
                slot=slot_number,
                error=str(e)
            )
            return 0
    
    async def _find_nearest_previous_slot(
        self,
        symbol: str,
        date: date,
        max_slot: int
    ) -> int:
        """
        Busca el slot anterior más cercano con datos
        
        Implementa la lógica de PineScript cuando faltan datos:
        "if svol == 0: for y = x * 2880 + ctime to x * 2880: ..."
        
        Args:
            symbol: Ticker symbol
            date: Fecha
            max_slot: Slot máximo a buscar
        
        Returns:
            Volumen del slot anterior más cercano (0 si no se encuentra)
        """
        query = """
            SELECT volume_accumulated
            FROM volume_slots
            WHERE symbol = $1 
              AND date = $2 
              AND slot_number <= $3
            ORDER BY slot_number DESC
            LIMIT 1
        """
        
        try:
            result = await self.db.fetchrow(query, symbol, date, max_slot)
            return result['volume_accumulated'] if result else 0
        except Exception as e:
            logger.error(
                "error_finding_previous_slot",
                symbol=symbol,
                date=str(date),
                max_slot=max_slot,
                error=str(e)
            )
            return 0
    
    async def reset_for_new_day(self):
        """
        Resetea el caché EN MEMORIA para un nuevo día de trading
        
        NOTA: NO limpia Redis. Los promedios históricos (rvol:hist:avg:*)
        son gestionados por data_maintenance service, no por analytics.
        Analytics solo CONSUME esos datos, no los gestiona.
        """
        self.volume_cache.reset()
        
        # ELIMINADO: Analytics NO debe limpiar promedios históricos de Redis
        # Eso es responsabilidad de data_maintenance service
        # pattern = f"{self.hist_cache_prefix}:*"
        # await self.redis.delete_pattern(pattern)
        
        logger.info("rvol_calculator_reset_for_new_day")
    
    async def close(self):
        """
        Cierra recursos al apagar el servicio
        """
        if hasattr(self, 'http_client'):
            await self.http_client.aclose()
            logger.info("http_client_closed")
    
    def get_cache_stats(self) -> Dict:
        """Obtiene estadísticas del caché"""
        return {
            "volume_cache": self.volume_cache.get_cache_stats(),
            "slot_manager": {
                "slot_size_minutes": self.slot_manager.slot_size_minutes,
                "total_slots": self.slot_manager.total_slots
            },
            "lookback_days": self.lookback_days
        }


