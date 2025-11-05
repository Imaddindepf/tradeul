"""
Slot Manager - Gestión de Slots Temporales

Este módulo maneja la división del día de trading en slots de tiempo
y gestiona el volumen acumulado por slot.
"""

from datetime import datetime, time, timedelta
from typing import Dict, Optional, Tuple
import structlog
from zoneinfo import ZoneInfo

from shared.enums.market_session import MarketSession

logger = structlog.get_logger(__name__)


class SlotManager:
    """
    Gestor de slots temporales para cálculo de RVOL
    
    Divide el día de trading COMPLETO en slots de N minutos (default 5),
    incluyendo PRE-MARKET, MARKET HOURS y POST-MARKET.
    
    Horarios estándar (ET):
    - Pre-market: 4:00 AM - 9:30 AM (330 min = 66 slots)
    - Market hours: 9:30 AM - 4:00 PM (390 min = 78 slots)
    - Post-market: 4:00 PM - 8:00 PM (240 min = 48 slots)
    - TOTAL: 4:00 AM - 8:00 PM (960 min = 192 slots de 5 min)
    """
    
    def __init__(
        self,
        slot_size_minutes: int = 5,
        premarket_open: time = time(4, 0),
        market_open: time = time(9, 30),
        market_close: time = time(16, 0),
        postmarket_close: time = time(20, 0),
        timezone: str = "America/New_York",
        include_extended_hours: bool = True
    ):
        """
        Inicializa el gestor de slots
        
        Args:
            slot_size_minutes: Tamaño del slot en minutos (default 5)
            premarket_open: Hora de inicio del pre-market (default 4:00 AM)
            market_open: Hora de apertura del mercado (default 9:30 AM)
            market_close: Hora de cierre del mercado (default 4:00 PM)
            postmarket_close: Hora de cierre del post-market (default 8:00 PM)
            timezone: Zona horaria del mercado (default ET)
            include_extended_hours: Si incluir pre/post market (default True)
        """
        self.slot_size_minutes = slot_size_minutes
        self.premarket_open = premarket_open
        self.market_open = market_open
        self.market_close = market_close
        self.postmarket_close = postmarket_close
        self.timezone = ZoneInfo(timezone)
        self.include_extended_hours = include_extended_hours
        
        # Calcular slots por sesión
        if include_extended_hours:
            # Día completo: pre-market + market + post-market
            self.day_start = premarket_open
            self.day_end = postmarket_close
        else:
            # Solo horario regular
            self.day_start = market_open
            self.day_end = market_close
        
        # Calcular minutos y slots totales
        total_minutes = self._calculate_total_minutes()
        self.total_slots = total_minutes // slot_size_minutes
        
        # Calcular slots por sesión para referencias
        premarket_minutes = self._time_diff_minutes(premarket_open, market_open)
        market_minutes = self._time_diff_minutes(market_open, market_close)
        postmarket_minutes = self._time_diff_minutes(market_close, postmarket_close)
        
        self.premarket_slots = premarket_minutes // slot_size_minutes
        self.market_slots = market_minutes // slot_size_minutes
        self.postmarket_slots = postmarket_minutes // slot_size_minutes
        
        logger.info(
            "slot_manager_initialized",
            slot_size_minutes=slot_size_minutes,
            include_extended_hours=include_extended_hours,
            premarket_slots=self.premarket_slots,
            market_slots=self.market_slots,
            postmarket_slots=self.postmarket_slots,
            total_slots=self.total_slots,
            day_start=str(self.day_start),
            day_end=str(self.day_end)
        )
    
    def _time_diff_minutes(self, start: time, end: time) -> int:
        """
        Calcula la diferencia en minutos entre dos horas
        
        Args:
            start: Hora de inicio
            end: Hora de fin
        
        Returns:
            Diferencia en minutos
        """
        start_minutes = start.hour * 60 + start.minute
        end_minutes = end.hour * 60 + end.minute
        return end_minutes - start_minutes
    
    def _calculate_total_minutes(self) -> int:
        """
        Calcula los minutos totales del día de trading
        (pre-market + market + post-market si está habilitado)
        """
        return self._time_diff_minutes(self.day_start, self.day_end)
    
    def get_current_slot(
        self, 
        now: Optional[datetime] = None,
        daylight_saving_adjust: int = 0
    ) -> int:
        """
        Obtiene el slot actual basado en la hora
        
        Incluye pre-market y post-market si está habilitado.
        
        Args:
            now: Timestamp actual (default: ahora)
            daylight_saving_adjust: Ajuste por DST (+1 o -1)
        
        Returns:
            Número de slot (0 a total_slots-1)
            -1 si está fuera del horario de trading
            
        Ejemplo con extended hours:
            - 4:00 AM (pre-market inicio) → slot 0
            - 9:30 AM (market open) → slot 66
            - 4:00 PM (market close) → slot 144
            - 8:00 PM (post-market close) → slot 192 (fuera de rango)
        """
        if now is None:
            now = datetime.now(self.timezone)
        
        # Ajustar por DST si es necesario
        if daylight_saving_adjust != 0:
            now = now + timedelta(hours=daylight_saving_adjust)
        
        current_hour = now.hour
        current_minute = now.minute
        
        # Calcular minutos desde medianoche
        current_minutes = current_hour * 60 + current_minute
        day_start_minutes = self.day_start.hour * 60 + self.day_start.minute
        day_end_minutes = self.day_end.hour * 60 + self.day_end.minute
        
        # Verificar si está dentro del horario de trading (incluyendo extended hours)
        if current_minutes < day_start_minutes:
            logger.debug(
                "before_trading_hours",
                current_time=now.strftime("%H:%M"),
                day_start=str(self.day_start)
            )
            return -1
        
        if current_minutes >= day_end_minutes:
            logger.debug(
                "after_trading_hours",
                current_time=now.strftime("%H:%M"),
                day_end=str(self.day_end)
            )
            return -1
        
        # Calcular slot (minutos desde inicio del día / tamaño del slot)
        minutes_from_start = current_minutes - day_start_minutes
        slot_number = minutes_from_start // self.slot_size_minutes
        
        return slot_number
    
    def get_slot_time(self, slot_number: int) -> time:
        """
        Obtiene la hora de un slot específico
        
        Args:
            slot_number: Número del slot
        
        Returns:
            Hora del slot
        """
        if slot_number < 0 or slot_number >= self.total_slots:
            raise ValueError(f"Slot {slot_number} fuera de rango [0, {self.total_slots-1}]")
        
        day_start_minutes = self.day_start.hour * 60 + self.day_start.minute
        slot_minutes = day_start_minutes + (slot_number * self.slot_size_minutes)
        
        slot_hour = slot_minutes // 60
        slot_minute = slot_minutes % 60
        
        return time(slot_hour, slot_minute)
    
    def get_slot_session(self, slot_number: int) -> MarketSession:
        """
        Determina la sesión de mercado para un slot dado
        
        Args:
            slot_number: Número del slot
        
        Returns:
            MarketSession (PRE_MARKET, MARKET_OPEN, POST_MARKET)
        """
        if slot_number < 0 or slot_number >= self.total_slots:
            return MarketSession.CLOSED
        
        # Calcular en qué sesión está el slot
        if slot_number < self.premarket_slots:
            return MarketSession.PRE_MARKET
        elif slot_number < (self.premarket_slots + self.market_slots):
            return MarketSession.MARKET_OPEN
        else:
            return MarketSession.POST_MARKET
    
    def is_new_slot(self, previous_slot: int, current_slot: int) -> bool:
        """
        Verifica si hemos cambiado de slot
        
        Args:
            previous_slot: Slot anterior
            current_slot: Slot actual
        
        Returns:
            True si es un nuevo slot
        """
        return current_slot != previous_slot and current_slot >= 0
    
    def get_extended_slot_index(
        self,
        slot_number: int,
        days_ago: int
    ) -> int:
        """
        Calcula el índice extendido para almacenamiento en array
        
        Siguiendo la lógica de PineScript, usamos arrays de:
        24 * 60 * 2 * (period + 1) para manejar slots de 48 horas
        
        Args:
            slot_number: Slot del día (0-77)
            days_ago: Días atrás (0 = hoy, 1 = ayer, etc.)
        
        Returns:
            Índice en el array extendido
        """
        # Conversión a minutos (slots de 5 min → minutos)
        minutes_per_day = 24 * 60
        slot_in_minutes = slot_number * self.slot_size_minutes
        
        # Índice = (días_atrás * minutos_por_día) + minuto_del_slot
        extended_index = (days_ago * minutes_per_day) + slot_in_minutes
        
        return extended_index
    
    def format_slot_info(self, slot_number: int) -> Dict:
        """
        Formatea información del slot para logging/debugging
        
        Args:
            slot_number: Número del slot
        
        Returns:
            Dict con información del slot
        """
        if slot_number < 0:
            return {
                "slot_number": slot_number,
                "status": "outside_trading_hours",
                "session": "CLOSED",
                "time": None,
                "total_slots": self.total_slots
            }
        
        slot_time = self.get_slot_time(slot_number)
        session = self.get_slot_session(slot_number)
        
        return {
            "slot_number": slot_number,
            "status": "active",
            "session": session.value,
            "time": slot_time.strftime("%H:%M"),
            "total_slots": self.total_slots,
            "premarket_slots": self.premarket_slots,
            "market_slots": self.market_slots,
            "postmarket_slots": self.postmarket_slots
        }


class VolumeSlotCache:
    """
    Caché de volúmenes por slot en memoria
    
    IMPORTANTE: Almacena volumen YA ACUMULADO desde Polygon.
    
    Polygon proporciona volumen acumulado del día en:
    - Snapshots: snapshot.min.av (minute bar accumulated volume)
    - WebSocket: agg.av (today's accumulated volume)
    
    Este caché NO calcula volumen, solo lo organiza por slots
    para cálculo eficiente de RVOL.
    """
    
    def __init__(self):
        """Inicializa el caché de volúmenes"""
        # {symbol: {slot_number: volume_accumulated}}
        # volume_accumulated viene directo de Polygon (min.av o av)
        self.volumes: Dict[str, Dict[int, int]] = {}
        
        # Metadatos adicionales por slot (opcionales)
        self.trades: Dict[str, Dict[int, int]] = {}
        self.vwaps: Dict[str, Dict[int, float]] = {}
        
        self.last_reset = datetime.now()
        
        logger.info("volume_slot_cache_initialized")
    
    def update_volume(
        self,
        symbol: str,
        slot_number: int,
        volume_accumulated: int,
        trades_count: int = 0,
        vwap: float = 0.0
    ):
        """
        Actualiza el volumen acumulado para un slot
        
        El volumen debe venir de Polygon YA ACUMULADO:
        - snapshot.min.av (desde snapshots)
        - agg.av (desde WebSocket aggregates)
        
        Args:
            symbol: Ticker symbol
            slot_number: Número del slot
            volume_accumulated: Volumen acumulado del día (de Polygon min.av/av)
            trades_count: Número de trades (opcional)
            vwap: Volume Weighted Average Price (opcional, de Polygon)
        """
        if symbol not in self.volumes:
            self.volumes[symbol] = {}
            self.trades[symbol] = {}
            self.vwaps[symbol] = {}
        
        self.volumes[symbol][slot_number] = volume_accumulated
        self.trades[symbol][slot_number] = trades_count
        self.vwaps[symbol][slot_number] = vwap
    
    def get_volume(self, symbol: str, slot_number: int) -> int:
        """
        Obtiene el volumen acumulado para un slot
        
        Args:
            symbol: Ticker symbol
            slot_number: Número del slot
        
        Returns:
            Volumen acumulado (0 si no existe)
        """
        return self.volumes.get(symbol, {}).get(slot_number, 0)
    
    def get_all_slots(self, symbol: str) -> Dict[int, int]:
        """
        Obtiene todos los slots con datos para un símbolo
        
        Args:
            symbol: Ticker symbol
        
        Returns:
            Dict {slot_number: volume_accumulated}
        """
        return self.volumes.get(symbol, {})
    
    def reset(self):
        """Limpia el caché (al inicio de un nuevo día)"""
        self.volumes.clear()
        self.trades.clear()
        self.vwaps.clear()
        self.last_reset = datetime.now()
        
        logger.info("volume_slot_cache_reset", reset_time=self.last_reset.isoformat())
    
    def get_cache_stats(self) -> Dict:
        """Obtiene estadísticas del caché"""
        return {
            "symbols_count": len(self.volumes),
            "total_slots": sum(len(slots) for slots in self.volumes.values()),
            "last_reset": self.last_reset.isoformat(),
            "memory_size_kb": self._estimate_memory_size()
        }
    
    def _estimate_memory_size(self) -> float:
        """Estima el tamaño en memoria (KB)"""
        # Estimación rough: cada entrada ~50 bytes
        total_entries = sum(len(slots) for slots in self.volumes.values())
        return (total_entries * 50) / 1024

