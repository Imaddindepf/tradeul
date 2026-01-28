"""
Metrics Builder
Orquestador que usa todos los calculadores para construir métricas de un ticker
"""

from typing import Optional, Dict, Any
from dataclasses import dataclass

from .price_metrics import PriceMetricsCalculator, PriceMetrics
from .volume_metrics import VolumeMetricsCalculator, VolumeMetrics
from .spread_metrics import SpreadMetricsCalculator, SpreadMetrics
from .enriched_extractor import EnrichedDataExtractor, EnrichedData


@dataclass
class AllMetrics:
    """Todas las métricas calculadas para un ticker"""
    price: PriceMetrics
    volume: VolumeMetrics
    spread: SpreadMetrics
    enriched: EnrichedData
    
    # VWAP-related
    price_vs_vwap: Optional[float] = None


class MetricsBuilder:
    """
    Builder que construye todas las métricas de un ticker.
    
    Uso:
        builder = MetricsBuilder()
        metrics = builder.build(
            price=10.50,
            open_price=10.00,
            high=10.75,
            low=9.80,
            prev_close=9.50,
            volume_today=1000000,
            ...
        )
    """
    
    def __init__(self):
        self.price_calc = PriceMetricsCalculator()
        self.volume_calc = VolumeMetricsCalculator()
        self.spread_calc = SpreadMetricsCalculator()
        self.enriched_extractor = EnrichedDataExtractor()
    
    def build(
        self,
        # Precio
        price: Optional[float],
        open_price: Optional[float],
        high: Optional[float],
        low: Optional[float],
        prev_close: Optional[float],
        # Volumen
        volume_today: Optional[int],
        prev_volume: Optional[int],
        avg_volume_10d: Optional[int],
        free_float: Optional[int],
        # Quote
        bid: Optional[float] = None,
        ask: Optional[float] = None,
        bid_size_lots: Optional[int] = None,
        ask_size_lots: Optional[int] = None,
        # Enriched data (from Analytics)
        atr_data: Optional[Dict[str, Any]] = None
    ) -> AllMetrics:
        """
        Construye todas las métricas para un ticker.
        
        Args:
            price: Precio actual
            open_price: Precio de apertura (day.o)
            high: Máximo del día (day.h)
            low: Mínimo del día (day.l)
            prev_close: Cierre del día anterior (prevDay.c)
            volume_today: Volumen de hoy
            prev_volume: Volumen del día anterior
            avg_volume_10d: Promedio de volumen de 10 días
            free_float: Free float
            bid: Mejor bid
            ask: Mejor ask
            bid_size_lots: Tamaño del bid en lotes
            ask_size_lots: Tamaño del ask en lotes
            atr_data: Datos enriquecidos de Analytics
            
        Returns:
            AllMetrics con todas las métricas calculadas
        """
        # Extraer datos enriquecidos primero (contiene intraday_high/low)
        enriched = self.enriched_extractor.extract(atr_data)
        
        # Calcular métricas de precio
        price_metrics = self.price_calc.calculate(
            price=price,
            open_price=open_price,
            high=high,
            low=low,
            prev_close=prev_close,
            intraday_high=enriched.intraday_high,
            intraday_low=enriched.intraday_low
        )
        
        # Calcular métricas de volumen
        volume_metrics = self.volume_calc.calculate(
            volume_today=volume_today,
            prev_volume=prev_volume,
            avg_volume_10d=avg_volume_10d,
            free_float=free_float,
            price=price
        )
        
        # Calcular métricas de spread
        spread_metrics = self.spread_calc.calculate(
            price=price,
            bid=bid,
            ask=ask,
            bid_size_lots=bid_size_lots,
            ask_size_lots=ask_size_lots
        )
        
        # Calcular price vs VWAP
        price_vs_vwap = self.price_calc.calculate_price_vs_vwap(price, enriched.vwap)
        
        return AllMetrics(
            price=price_metrics,
            volume=volume_metrics,
            spread=spread_metrics,
            enriched=enriched,
            price_vs_vwap=price_vs_vwap
        )


# Singleton para uso global
_metrics_builder: Optional[MetricsBuilder] = None


def get_metrics_builder() -> MetricsBuilder:
    """Obtiene la instancia singleton del MetricsBuilder."""
    global _metrics_builder
    if _metrics_builder is None:
        _metrics_builder = MetricsBuilder()
    return _metrics_builder
