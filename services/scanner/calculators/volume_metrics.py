"""
Volume Metrics Calculator
Calcula métricas relacionadas con volumen: float rotation, volume %, dollar volume
"""

from typing import Optional
from dataclasses import dataclass


@dataclass
class VolumeMetrics:
    """Resultado de cálculos de métricas de volumen"""
    volume_today_pct: Optional[float] = None      # Volume hoy como % de avg_volume_10d
    volume_yesterday_pct: Optional[float] = None  # Volume ayer como % de avg_volume_10d
    float_rotation: Optional[float] = None        # Volume hoy como % del free float
    dollar_volume: Optional[float] = None         # price × avg_volume_10d (liquidez diaria)


class VolumeMetricsCalculator:
    """
    Calculador de métricas de volumen.
    
    Fórmulas:
    - volume_today_pct = (volume_today / avg_volume_10d) * 100
    - volume_yesterday_pct = (prev_volume / avg_volume_10d) * 100
    - float_rotation = (volume_today / free_float) * 100
    - dollar_volume = price × avg_volume_10d
    """
    
    @staticmethod
    def calculate(
        volume_today: Optional[int],
        prev_volume: Optional[int],
        avg_volume_10d: Optional[int],
        free_float: Optional[int],
        price: Optional[float]
    ) -> VolumeMetrics:
        """
        Calcula todas las métricas de volumen.
        
        Args:
            volume_today: Volumen de hoy
            prev_volume: Volumen del día anterior
            avg_volume_10d: Promedio de volumen de 10 días
            free_float: Free float (acciones disponibles para trading)
            price: Precio actual
            
        Returns:
            VolumeMetrics con todos los valores calculados
        """
        metrics = VolumeMetrics()
        
        # volume_today_pct: qué % del volumen promedio hemos hecho hoy
        if volume_today and avg_volume_10d and avg_volume_10d > 0:
            metrics.volume_today_pct = round((volume_today / avg_volume_10d) * 100, 1)
        
        # volume_yesterday_pct: qué % del volumen promedio hicimos ayer
        if prev_volume and avg_volume_10d and avg_volume_10d > 0:
            metrics.volume_yesterday_pct = round((prev_volume / avg_volume_10d) * 100, 1)
        
        # float_rotation: cuántas veces ha rotado el float hoy
        if volume_today and free_float and free_float > 0:
            metrics.float_rotation = round((volume_today / free_float) * 100, 2)
        
        # dollar_volume: liquidez diaria en dólares
        if price and avg_volume_10d and price > 0 and avg_volume_10d > 0:
            metrics.dollar_volume = price * avg_volume_10d
        
        return metrics
    
    @staticmethod
    def calculate_rvol_simple(
        volume_today: Optional[int],
        avg_volume_10d: Optional[int]
    ) -> Optional[float]:
        """
        Calcula RVOL simple (sin ajuste por tiempo).
        
        Para RVOL preciso por slot de tiempo, usar el servicio Analytics.
        
        Returns:
            RVOL como ratio (1.5 = 150% del volumen promedio)
        """
        if volume_today and avg_volume_10d and avg_volume_10d > 0:
            return volume_today / avg_volume_10d
        return None
