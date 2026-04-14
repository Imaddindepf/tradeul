"""
Enriched Data Extractor
Extrae datos del snapshot enriquecido que viene del servicio Analytics
"""

from typing import Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class EnrichedData:
    """Datos extraídos del snapshot enriquecido"""
    # ATR
    atr: Optional[float] = None
    atr_percent: Optional[float] = None
    
    # Intraday high/low (incluye pre/post market)
    intraday_high: Optional[float] = None
    intraday_low: Optional[float] = None
    
    # Volume windows (volumen en los últimos N minutos)
    vol_1min: Optional[int] = None
    vol_5min: Optional[int] = None
    vol_10min: Optional[int] = None
    vol_15min: Optional[int] = None
    vol_30min: Optional[int] = None
    
    # Price change windows (cambio % en los últimos N minutos)
    chg_1min: Optional[float] = None
    chg_5min: Optional[float] = None
    chg_10min: Optional[float] = None
    chg_15min: Optional[float] = None
    chg_30min: Optional[float] = None
    
    # Volume window % (Tradeul style, vs avg_volume_10d)
    vol_1min_pct: Optional[float] = None
    vol_5min_pct: Optional[float] = None
    vol_10min_pct: Optional[float] = None
    vol_15min_pct: Optional[float] = None
    vol_30min_pct: Optional[float] = None
    
    # Price range windows (Tradeul: Range2..Range120)
    range_2min: Optional[float] = None
    range_5min: Optional[float] = None
    range_15min: Optional[float] = None
    range_30min: Optional[float] = None
    range_60min: Optional[float] = None
    range_120min: Optional[float] = None
    range_2min_pct: Optional[float] = None
    range_5min_pct: Optional[float] = None
    range_15min_pct: Optional[float] = None
    range_30min_pct: Optional[float] = None
    range_60min_pct: Optional[float] = None
    range_120min_pct: Optional[float] = None
    
    # Trades anomaly detection
    trades_today: Optional[int] = None
    avg_trades_5d: Optional[float] = None
    trades_z_score: Optional[float] = None
    is_trade_anomaly: bool = False
    
    # RVOL
    rvol: Optional[float] = None
    rvol_slot: Optional[float] = None
    
    # VWAP
    vwap: Optional[float] = None
    
    # Pre/Post market metrics
    premarket_change_percent: Optional[float] = None
    postmarket_change_percent: Optional[float] = None
    postmarket_volume: Optional[int] = None


_RANGE_KEYS = (
    'range_2min', 'range_5min', 'range_15min',
    'range_30min', 'range_60min', 'range_120min',
    'range_2min_pct', 'range_5min_pct', 'range_15min_pct',
    'range_30min_pct', 'range_60min_pct', 'range_120min_pct',
)


class EnrichedDataExtractor:
    """
    Extrae datos del diccionario de datos enriquecidos (atr_data).
    
    El servicio Analytics enriquece los snapshots con métricas calculadas
    que se pasan al scanner como un diccionario.
    """
    
    @staticmethod
    def extract(atr_data: Optional[Dict[str, Any]]) -> EnrichedData:
        data = EnrichedData()
        
        if not atr_data:
            return data
        
        # ATR
        data.atr = atr_data.get('atr')
        data.atr_percent = atr_data.get('atr_percent')
        
        # Intraday high/low
        data.intraday_high = atr_data.get('intraday_high')
        data.intraday_low = atr_data.get('intraday_low')
        
        # Volume windows
        data.vol_1min = atr_data.get('vol_1min')
        data.vol_5min = atr_data.get('vol_5min')
        data.vol_10min = atr_data.get('vol_10min')
        data.vol_15min = atr_data.get('vol_15min')
        data.vol_30min = atr_data.get('vol_30min')
        
        # Price change windows
        data.chg_1min = atr_data.get('chg_1min')
        data.chg_5min = atr_data.get('chg_5min')
        data.chg_10min = atr_data.get('chg_10min')
        data.chg_15min = atr_data.get('chg_15min')
        data.chg_30min = atr_data.get('chg_30min')
        
        # Volume window %
        data.vol_1min_pct = atr_data.get('vol_1min_pct')
        data.vol_5min_pct = atr_data.get('vol_5min_pct')
        data.vol_10min_pct = atr_data.get('vol_10min_pct')
        data.vol_15min_pct = atr_data.get('vol_15min_pct')
        data.vol_30min_pct = atr_data.get('vol_30min_pct')
        
        # Price range windows ($) and (% of ATR)
        for k in _RANGE_KEYS:
            setattr(data, k, atr_data.get(k))
        
        # Trades anomaly
        data.trades_today = atr_data.get('trades_today')
        data.avg_trades_5d = atr_data.get('avg_trades_5d')
        data.trades_z_score = atr_data.get('trades_z_score')
        data.is_trade_anomaly = atr_data.get('is_trade_anomaly', False)
        
        # RVOL
        data.rvol = atr_data.get('rvol')
        data.rvol_slot = atr_data.get('rvol_slot')
        
        # VWAP
        data.vwap = atr_data.get('vwap')
        
        # Pre/Post market
        data.premarket_change_percent = atr_data.get('premarket_change_percent')
        data.postmarket_change_percent = atr_data.get('postmarket_change_percent')
        data.postmarket_volume = atr_data.get('postmarket_volume')
        
        return data
    
    @staticmethod
    def get_safe(atr_data: Optional[Dict[str, Any]], key: str, default: Any = None) -> Any:
        """Helper para obtener un valor de forma segura."""
        if atr_data:
            return atr_data.get(key, default)
        return default
