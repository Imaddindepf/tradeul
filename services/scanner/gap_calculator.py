"""
Gap Calculator
Calcula diferentes tipos de gaps según la sesión de mercado
"""

from typing import Optional, List
from datetime import datetime

import sys
sys.path.append('/app')

from shared.models.polygon import PolygonSnapshot
from shared.models.scanner import ScannerTicker
from shared.enums.market_session import MarketSession
from shared.utils.logger import get_logger
from shared.config.settings import settings

logger = get_logger(__name__)


class GapCalculator:
    """
    Calculadora profesional de gaps
    
    Tipos de gaps:
    1. GAP_FROM_PREV_CLOSE: Desde cierre anterior (baseline)
    2. GAP_PREMARKET: Cambio durante pre-market (4 AM - 9:30 AM)
    3. GAP_AT_OPEN: Gap exacto en la apertura (9:30 AM)
    4. GAP_FROM_OPEN: Desde precio de apertura (durante market hours)
    5. GAP_INTRADAY: Cambio total intraday
    6. GAP_POSTMARKET: Cambio durante post-market (4 PM - 8 PM)
    """
    
    @staticmethod
    def calculate_all_gaps(
        ticker: ScannerTicker,
        snapshot: PolygonSnapshot
    ) -> dict:
        """
        Calcula TODOS los gaps relevantes para un ticker
        
        Returns:
            Dict con todos los gaps calculados
        """
        gaps = {}
        
        # Precios de referencia
        prev_close = snapshot.prevDay.c if snapshot.prevDay else None
        day_open = snapshot.day.o if snapshot.day else None
        current_price = ticker.price
        
        # GAP FROM PREVIOUS CLOSE (principal)
        if prev_close and prev_close > 0:
            gaps['gap_from_prev_close'] = ((current_price - prev_close) / prev_close) * 100
            gaps['gap_from_prev_close_dollars'] = current_price - prev_close
        else:
            gaps['gap_from_prev_close'] = None
            gaps['gap_from_prev_close_dollars'] = None
        
        # GAP FROM OPEN (durante market hours)
        if day_open and day_open > 0:
            gaps['gap_from_open'] = ((current_price - day_open) / day_open) * 100
            gaps['gap_from_open_dollars'] = current_price - day_open
        else:
            gaps['gap_from_open'] = None
            gaps['gap_from_open_dollars'] = None
        
        # CLASIFICACIÓN POR SESIÓN
        session = ticker.session
        
        if session == MarketSession.PRE_MARKET:
            # Gap pre-market = gap desde cierre anterior
            gaps['gap_premarket'] = gaps['gap_from_prev_close']
            gaps['gap_at_open'] = None
            gaps['gap_postmarket'] = None
            
        elif session == MarketSession.MARKET_OPEN:
            # Ya pasó la apertura
            # gap_at_open sería el que hubo a las 9:30 AM (necesitaríamos guardarlo)
            gaps['gap_premarket'] = None  # Ya pasó
            gaps['gap_at_open'] = None    # Necesita tracking en apertura
            gaps['gap_postmarket'] = None
            
        elif session == MarketSession.POST_MARKET:
            # Gap post-market = cambio desde cierre del día (4 PM)
            market_close_price = snapshot.day.c if snapshot.day else None
            if market_close_price and market_close_price > 0:
                gaps['gap_postmarket'] = ((current_price - market_close_price) / market_close_price) * 100
            else:
                gaps['gap_postmarket'] = None
            
            gaps['gap_premarket'] = None
            gaps['gap_at_open'] = None
        
        else:  # CLOSED
            gaps['gap_premarket'] = None
            gaps['gap_at_open'] = None
            gaps['gap_postmarket'] = None
        
        # ABSOLUTE GAP (valor absoluto para ranking)
        gaps['gap_abs'] = abs(gaps['gap_from_prev_close']) if gaps['gap_from_prev_close'] else 0
        
        # DIRECTION
        if gaps['gap_from_prev_close']:
            if gaps['gap_from_prev_close'] > 0:
                gaps['gap_direction'] = 'UP'
            elif gaps['gap_from_prev_close'] < 0:
                gaps['gap_direction'] = 'DOWN'
            else:
                gaps['gap_direction'] = 'FLAT'
        else:
            gaps['gap_direction'] = 'UNKNOWN'
        
        return gaps
    
    @staticmethod
    def classify_gap_size(gap_percent: Optional[float]) -> str:
        """
        Clasifica el tamaño del gap
        
        Returns:
            'SMALL', 'MEDIUM', 'LARGE', 'EXTREME'
        """
        if gap_percent is None:
            return 'UNKNOWN'
        
        abs_gap = abs(gap_percent)
        
        if abs_gap < 2:
            return 'SMALL'
        elif abs_gap < 5:
            return 'MEDIUM'
        elif abs_gap < 10:
            return 'LARGE'
        else:
            return 'EXTREME'
    
    @staticmethod
    def is_gap_up(gap_percent: Optional[float], threshold: float = 2.0) -> bool:
        """
        Determina si es gap up significativo
        
        Args:
            gap_percent: % de gap
            threshold: Umbral mínimo (default 2%)
        """
        return gap_percent is not None and gap_percent >= threshold
    
    @staticmethod
    def is_gap_down(gap_percent: Optional[float], threshold: float = -2.0) -> bool:
        """
        Determina si es gap down significativo
        """
        return gap_percent is not None and gap_percent <= threshold
    
    @staticmethod
    def calculate_gap_metrics(ticker: ScannerTicker) -> dict:
        """
        Calcula métricas adicionales de gap para análisis
        
        Returns:
            Dict con métricas avanzadas
        """
        metrics = {}
        
        # Distancia desde high/low
        if ticker.price and ticker.high and ticker.low:
            if ticker.high > 0:
                metrics['distance_from_high'] = ((ticker.price - ticker.high) / ticker.high) * 100
            
            if ticker.low > 0:
                metrics['distance_from_low'] = ((ticker.price - ticker.low) / ticker.low) * 100
            
            # Range del día
            if ticker.high > ticker.low:
                day_range = ticker.high - ticker.low
                position_in_range = (ticker.price - ticker.low) / day_range
                metrics['position_in_range'] = position_in_range * 100  # 0-100%
        
        # Gap fill probability (simple heuristic)
        # Si el precio está volviendo hacia prev_close
        if ticker.prev_close and ticker.open:
            if ticker.open > ticker.prev_close:  # Gap up
                if ticker.price < ticker.open:  # Precio cayendo
                    metrics['gap_fill_progress'] = ((ticker.open - ticker.price) / (ticker.open - ticker.prev_close)) * 100
                else:
                    metrics['gap_fill_progress'] = 0
            elif ticker.open < ticker.prev_close:  # Gap down
                if ticker.price > ticker.open:  # Precio subiendo
                    metrics['gap_fill_progress'] = ((ticker.price - ticker.open) / (ticker.prev_close - ticker.open)) * 100
                else:
                    metrics['gap_fill_progress'] = 0
            else:
                metrics['gap_fill_progress'] = 0
        
        return metrics


class HighsLowsTracker:
    """
    Rastrea máximos y mínimos CONTINUOS durante el día
    
    Identifica tickers que están ACTIVAMENTE haciendo nuevos máximos/mínimos,
    no solo tickers que están "cerca" de sus máximos.
    
    Criterios para "nuevo máximo":
    - Precio actual > máximo anterior registrado
    - Timestamp del último máximo < 5 minutos (configurable)
    - Frecuencia de máximos: ej. 3+ máximos en últimos 15 minutos
    """
    
    def __init__(self, max_age_seconds: int = 300):
        """
        Args:
            max_age_seconds: Tiempo máximo desde último máximo para considerarlo "activo" (default: 5 min)
        """
        # Storage: {symbol: {high, high_timestamp, high_count, low, low_timestamp, low_count, history}}
        self.tracking = {}
        self.max_age_seconds = max_age_seconds
    
    def update_ticker(
        self,
        symbol: str,
        price: float,
        timestamp: datetime,
        intraday_high: Optional[float] = None,
        intraday_low: Optional[float] = None
    ):
        """
        Actualiza tracking de máximos/mínimos para un ticker
        
        Args:
            symbol: Símbolo del ticker
            price: Precio actual
            timestamp: Timestamp actual
            intraday_high: Máximo intraday (incluye pre/post)
            intraday_low: Mínimo intraday (incluye pre/post)
        """
        if symbol not in self.tracking:
            # Inicializar con intraday_high/low existentes (persisten en Redis/DB)
            # Si no están disponibles, usar el precio actual
            # IMPORTANTE: Si viene de intraday_high (máximo antiguo), usar timestamp antiguo
            # para que is_making_new_highs() no piense que acaba de hacer un máximo
            old_timestamp = timestamp - timedelta(hours=2)  # Timestamp antiguo
            
            self.tracking[symbol] = {
                'high': intraday_high if intraday_high is not None else price,
                'high_timestamp': old_timestamp if intraday_high is not None else timestamp,
                'high_count_15min': 0,  # Cuántos máximos en últimos 15 min
                'low': intraday_low if intraday_low is not None else price,
                'low_timestamp': old_timestamp if intraday_low is not None else timestamp,
                'low_count_15min': 0,
                'history': []  # [(timestamp, 'high'/'low'), ...]
            }
        
        data = self.tracking[symbol]
        
        # NUEVO MÁXIMO: precio actual > máximo anterior
        if price > data['high']:
            data['high'] = price
            data['high_timestamp'] = timestamp
            data['history'].append((timestamp, 'high'))
            
            # Contar máximos en últimos 15 minutos
            recent_highs = [
                h for h in data['history']
                if h[1] == 'high' and (timestamp - h[0]).total_seconds() <= 900
            ]
            data['high_count_15min'] = len(recent_highs)
            
            logger.debug(
                f"🔥 NEW HIGH: {symbol}",
                price=price,
                high_count=data['high_count_15min']
            )
        
        # NUEVO MÍNIMO: precio actual < mínimo anterior
        if price < data['low']:
            data['low'] = price
            data['low_timestamp'] = timestamp
            data['history'].append((timestamp, 'low'))
            
            # Contar mínimos en últimos 15 minutos
            recent_lows = [
                h for h in data['history']
                if h[1] == 'low' and (timestamp - h[0]).total_seconds() <= 900
            ]
            data['low_count_15min'] = len(recent_lows)
            
            logger.debug(
                f"❄️ NEW LOW: {symbol}",
                price=price,
                low_count=data['low_count_15min']
            )
        
        # Limpiar historial antiguo (> 15 min)
        cutoff_time = timestamp
        data['history'] = [
            h for h in data['history']
            if (timestamp - h[0]).total_seconds() <= 900
        ]
    
    def is_making_new_highs(self, symbol: str, current_time: datetime) -> bool:
        """
        Verifica si un ticker está ACTIVAMENTE haciendo nuevos máximos
        
        Criterios:
        - Último máximo fue hace menos de max_age_seconds (5 min por defecto)
        - O ha hecho múltiples máximos (2+) en últimos 15 minutos
        
        Returns:
            True si está activamente haciendo máximos
        """
        if symbol not in self.tracking:
            return False
        
        data = self.tracking[symbol]
        
        # Tiempo desde último máximo
        time_since_high = (current_time - data['high_timestamp']).total_seconds()
        
        # Criterio 1: Máximo reciente (últimos 5 min)
        if time_since_high <= self.max_age_seconds:
            return True
        
        # Criterio 2: Múltiples máximos en últimos 15 min (momentum fuerte)
        if data['high_count_15min'] >= 2:
            return True
        
        return False
    
    def is_making_new_lows(self, symbol: str, current_time: datetime) -> bool:
        """
        Verifica si un ticker está ACTIVAMENTE haciendo nuevos mínimos
        
        Returns:
            True si está activamente haciendo mínimos
        """
        if symbol not in self.tracking:
            return False
        
        data = self.tracking[symbol]
        
        # Tiempo desde último mínimo
        time_since_low = (current_time - data['low_timestamp']).total_seconds()
        
        # Criterio 1: Mínimo reciente (últimos 5 min)
        if time_since_low <= self.max_age_seconds:
            return True
        
        # Criterio 2: Múltiples mínimos en últimos 15 min
        if data['low_count_15min'] >= 2:
            return True
        
        return False
    
    def get_stats(self, symbol: str) -> Optional[dict]:
        """
        Obtiene estadísticas de máximos/mínimos para un símbolo
        
        Returns:
            Dict con stats o None si no existe
        """
        return self.tracking.get(symbol)
    
    def clear_for_new_day(self):
        """
        Limpia tracking para un nuevo día de trading
        """
        self.tracking.clear()
        logger.info("highs_lows_tracker_cleared_for_new_day")


class GapTracker:
    """
    Rastrea gaps durante todo el día
    
    Guarda el gap en diferentes momentos clave:
    - Gap en pre-market (4 AM)
    - Gap en apertura (9:30 AM)
    - Gap en cierre (4 PM)
    - Gap en post-market (8 PM)
    """
    
    def __init__(self):
        # Storage: {symbol: {premarket_gap, open_gap, close_gap, postmarket_gap}}
        self.gap_tracking = {}
    
    def track_gap(
        self,
        symbol: str,
        session: MarketSession,
        gap_percent: float,
        timestamp: datetime
    ):
        """
        Rastrea gap en diferentes sesiones
        """
        if symbol not in self.gap_tracking:
            self.gap_tracking[symbol] = {
                'premarket_gap': None,
                'open_gap': None,
                'high_gap': None,
                'current_gap': gap_percent,
                'last_update': timestamp
            }
        
        tracking = self.gap_tracking[symbol]
        
        # Actualizar según sesión
        if session == MarketSession.PRE_MARKET:
            # Guardar el gap máximo de pre-market
            if tracking['premarket_gap'] is None or abs(gap_percent) > abs(tracking['premarket_gap']):
                tracking['premarket_gap'] = gap_percent
        
        elif session == MarketSession.MARKET_OPEN:
            # Si es la primera vez en MARKET_OPEN, es el gap at open
            if tracking['open_gap'] is None:
                tracking['open_gap'] = gap_percent
            
            # Guardar el gap máximo del día
            if tracking['high_gap'] is None or abs(gap_percent) > abs(tracking['high_gap']):
                tracking['high_gap'] = gap_percent
        
        # Siempre actualizar current
        tracking['current_gap'] = gap_percent
        tracking['last_update'] = timestamp
    
    def get_gap_summary(self, symbol: str) -> Optional[dict]:
        """
        Obtiene resumen de gaps del día para un símbolo
        """
        return self.gap_tracking.get(symbol)
    
    def get_top_gappers(
        self,
        session: Optional[MarketSession] = None,
        limit: int = settings.default_gappers_limit,
        direction: str = 'both'  # 'up', 'down', 'both'
    ) -> List[tuple]:
        """
        Obtiene top gappers
        
        Args:
            session: Filtrar por sesión (PRE_MARKET, MARKET_OPEN, etc.)
            limit: Top N resultados (por defecto: settings.default_gappers_limit)
            direction: 'up', 'down', o 'both'
        
        Returns:
            Lista de (symbol, gap_data) ordenada por gap absoluto
        """
        # Validar límite máximo
        limit = min(limit, settings.max_category_limit)
        results = []
        
        for symbol, data in self.gap_tracking.items():
            gap = data['current_gap']
            
            # Filtrar por dirección
            if direction == 'up' and gap < 0:
                continue
            if direction == 'down' and gap > 0:
                continue
            
            results.append((symbol, data))
        
        # Ordenar por gap absoluto (mayor gap primero)
        results.sort(key=lambda x: abs(x[1]['current_gap']), reverse=True)
        
        return results[:limit]
    
    def clear_for_new_day(self):
        """
        Limpia tracking para un nuevo día de trading
        """
        self.gap_tracking.clear()
        logger.info("gap_tracker_cleared_for_new_day")

