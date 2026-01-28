"""
Price Metrics Calculator
Calcula métricas relacionadas con precio: gaps, cambios, distancias
"""

from typing import Optional, NamedTuple
from dataclasses import dataclass


@dataclass
class PriceMetrics:
    """Resultado de cálculos de métricas de precio"""
    # Cambios
    change_percent: Optional[float] = None      # (price - prev_close) / prev_close
    gap_percent: Optional[float] = None          # Gap % como TradeIdeas
    change_from_open: Optional[float] = None     # (price - open) / open
    
    # Distancia desde máximos/mínimos
    price_from_high: Optional[float] = None      # % desde máximo del día
    price_from_low: Optional[float] = None       # % desde mínimo del día
    price_from_intraday_high: Optional[float] = None  # % desde máximo intraday (incluye pre/post)
    price_from_intraday_low: Optional[float] = None   # % desde mínimo intraday


class PriceMetricsCalculator:
    """
    Calculador de métricas de precio.
    
    Fórmulas:
    - change_percent = (price - prev_close) / prev_close * 100
    - gap_percent = (open - prev_close) / prev_close * 100 [o change_percent en pre-market]
    - change_from_open = (price - open) / open * 100
    - price_from_high = (price - high) / high * 100
    - price_from_low = (price - low) / low * 100
    """
    
    @staticmethod
    def calculate(
        price: Optional[float],
        open_price: Optional[float],
        high: Optional[float],
        low: Optional[float],
        prev_close: Optional[float],
        intraday_high: Optional[float] = None,
        intraday_low: Optional[float] = None
    ) -> PriceMetrics:
        """
        Calcula todas las métricas de precio.
        
        Args:
            price: Precio actual
            open_price: Precio de apertura (day.o)
            high: Máximo del día (day.h)
            low: Mínimo del día (day.l)
            prev_close: Cierre del día anterior (prevDay.c)
            intraday_high: Máximo intraday incluyendo pre/post market
            intraday_low: Mínimo intraday incluyendo pre/post market
            
        Returns:
            PriceMetrics con todos los valores calculados
        """
        metrics = PriceMetrics()
        
        if not price or price <= 0:
            return metrics
        
        # change_percent: cambio total desde cierre anterior
        if prev_close and prev_close > 0:
            metrics.change_percent = ((price - prev_close) / prev_close) * 100
            
            # gap_percent: Como TradeIdeas
            # - Si hay open: GAP REAL = (open - prev_close) / prev_close
            # - Si no hay open (pre-market): GAP ESPERADO = change_percent
            if open_price and open_price > 0:
                metrics.gap_percent = ((open_price - prev_close) / prev_close) * 100
            else:
                # Pre-market: usar precio actual como "expected open"
                metrics.gap_percent = metrics.change_percent
        
        # change_from_open: cambio desde la apertura
        if open_price and open_price > 0:
            metrics.change_from_open = ((price - open_price) / open_price) * 100
        
        # price_from_high: distancia desde máximo del día
        if high and high > 0:
            metrics.price_from_high = ((price - high) / high) * 100
        
        # price_from_low: distancia desde mínimo del día
        if low and low > 0:
            metrics.price_from_low = ((price - low) / low) * 100
        
        # price_from_intraday_high: distancia desde máximo intraday
        if intraday_high and intraday_high > 0:
            metrics.price_from_intraday_high = ((price - intraday_high) / intraday_high) * 100
        
        # price_from_intraday_low: distancia desde mínimo intraday
        if intraday_low and intraday_low > 0:
            metrics.price_from_intraday_low = ((price - intraday_low) / intraday_low) * 100
        
        return metrics
    
    @staticmethod
    def calculate_price_vs_vwap(price: Optional[float], vwap: Optional[float]) -> Optional[float]:
        """
        Calcula la distancia del precio respecto al VWAP.
        
        Returns:
            % de distancia desde VWAP (positivo = sobre VWAP)
        """
        if price and vwap and vwap > 0:
            return ((price - vwap) / vwap) * 100
        return None
