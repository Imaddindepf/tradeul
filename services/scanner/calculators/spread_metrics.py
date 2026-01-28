"""
Spread Metrics Calculator
Calcula métricas de spread y liquidez: bid/ask, spread, distancia NBBO
"""

from typing import Optional
from dataclasses import dataclass


@dataclass
class SpreadMetrics:
    """Resultado de cálculos de métricas de spread"""
    bid: Optional[float] = None
    ask: Optional[float] = None
    bid_size: Optional[int] = None          # En shares (no lots)
    ask_size: Optional[int] = None          # En shares (no lots)
    spread: Optional[float] = None           # En centavos
    spread_percent: Optional[float] = None   # Como % del mid price
    bid_ask_ratio: Optional[float] = None    # bid_size / ask_size
    distance_from_nbbo: Optional[float] = None  # % de distancia del precio al NBBO


class SpreadMetricsCalculator:
    """
    Calculador de métricas de spread y liquidez.
    
    Fórmulas:
    - spread = (ask - bid) * 100 [en centavos]
    - spread_percent = (ask - bid) / mid_price * 100
    - bid_ask_ratio = bid_size / ask_size
    - distance_from_nbbo = distancia del precio al rango bid-ask
    """
    
    @staticmethod
    def calculate(
        price: Optional[float],
        bid: Optional[float],
        ask: Optional[float],
        bid_size_lots: Optional[int],
        ask_size_lots: Optional[int]
    ) -> SpreadMetrics:
        """
        Calcula todas las métricas de spread.
        
        Args:
            price: Precio actual
            bid: Mejor bid
            ask: Mejor ask
            bid_size_lots: Tamaño del bid en lotes (multiply by 100 for shares)
            ask_size_lots: Tamaño del ask en lotes (multiply by 100 for shares)
            
        Returns:
            SpreadMetrics con todos los valores calculados
        """
        metrics = SpreadMetrics()
        
        metrics.bid = bid
        metrics.ask = ask
        
        # Convertir lots a shares
        if bid_size_lots:
            metrics.bid_size = bid_size_lots * 100
        if ask_size_lots:
            metrics.ask_size = ask_size_lots * 100
        
        # Spread calculations
        if bid and ask and bid > 0 and ask > 0:
            # spread en centavos
            metrics.spread = (ask - bid) * 100
            
            # spread_percent respecto al mid price
            mid_price = (bid + ask) / 2
            metrics.spread_percent = ((ask - bid) / mid_price) * 100
        
        # bid_ask_ratio
        if metrics.bid_size and metrics.ask_size and metrics.ask_size > 0:
            metrics.bid_ask_ratio = metrics.bid_size / metrics.ask_size
        
        # distance_from_nbbo
        if price and bid and ask and bid > 0 and ask > 0:
            if price >= bid and price <= ask:
                # Precio está dentro del spread
                metrics.distance_from_nbbo = 0.0
            elif price < bid:
                # Precio está por debajo del bid
                metrics.distance_from_nbbo = ((bid - price) / bid) * 100
            else:
                # Precio está por encima del ask
                metrics.distance_from_nbbo = ((price - ask) / ask) * 100
        
        return metrics
