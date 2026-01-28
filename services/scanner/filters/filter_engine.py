"""
Filter Engine
Sistema declarativo de filtros para ScannerTicker

En lugar de 200 líneas de if/else repetitivos, define filtros como datos
y aplica la lógica de forma genérica.
"""

from typing import Optional, List, Any
from datetime import datetime

import sys
sys.path.append('/app')

from shared.models.scanner import ScannerTicker, FilterConfig, FilterParameters
from shared.enums.market_session import MarketSession
from shared.utils.logger import get_logger

logger = get_logger(__name__)


# Definición de filtros: (param_min_name, param_max_name, ticker_field_name)
# Si el valor es None, no se aplica ese lado del filtro
FILTER_DEFINITIONS = [
    # RVOL
    ('min_rvol', 'max_rvol', 'rvol'),
    
    # Price
    ('min_price', 'max_price', 'price'),
    
    # Spread (in cents)
    ('min_spread', 'max_spread', 'spread'),
    
    # Bid/Ask sizes
    ('min_bid_size', 'max_bid_size', 'bid_size'),
    ('min_ask_size', 'max_ask_size', 'ask_size'),
    
    # Distance from NBBO
    ('min_distance_from_nbbo', 'max_distance_from_nbbo', 'distance_from_nbbo'),
    
    # Volume
    ('min_volume', None, 'volume_today'),
    ('min_minute_volume', None, 'minute_volume'),
    
    # Average Daily Volume (5D, 10D, 3M)
    ('min_avg_volume_5d', 'max_avg_volume_5d', 'avg_volume_5d'),
    ('min_avg_volume_10d', 'max_avg_volume_10d', 'avg_volume_10d'),
    ('min_avg_volume_3m', 'max_avg_volume_3m', 'avg_volume_3m'),
    
    # Dollar Volume
    ('min_dollar_volume', 'max_dollar_volume', 'dollar_volume'),
    
    # Volume Today/Yesterday %
    ('min_volume_today_pct', 'max_volume_today_pct', 'volume_today_pct'),
    ('min_volume_yesterday_pct', 'max_volume_yesterday_pct', 'volume_yesterday_pct'),
    
    # Change percent
    ('min_change_percent', 'max_change_percent', 'change_percent'),
    
    # Market cap
    ('min_market_cap', 'max_market_cap', 'market_cap'),
    
    # Float
    ('min_float', 'max_float', 'free_float'),
]


def _check_min_max(
    ticker_value: Optional[Any],
    min_value: Optional[Any],
    max_value: Optional[Any],
    allow_none_ticker: bool = False
) -> bool:
    """
    Verifica si ticker_value está dentro del rango [min_value, max_value].
    
    Args:
        ticker_value: Valor del ticker
        min_value: Valor mínimo permitido (None = sin límite)
        max_value: Valor máximo permitido (None = sin límite)
        allow_none_ticker: Si True, ticker_value=None pasa el filtro
        
    Returns:
        True si pasa el filtro, False si no
    """
    # Si no hay restricciones, pasa
    if min_value is None and max_value is None:
        return True
    
    # Si el ticker no tiene valor
    if ticker_value is None:
        return allow_none_ticker
    
    # Verificar mínimo
    if min_value is not None and ticker_value < min_value:
        return False
    
    # Verificar máximo
    if max_value is not None and ticker_value > max_value:
        return False
    
    return True


def apply_filter(
    ticker: ScannerTicker,
    params: FilterParameters,
    current_session: Optional[MarketSession] = None
) -> bool:
    """
    Aplica todos los filtros de params a un ticker.
    
    Args:
        ticker: El ticker a filtrar
        params: Parámetros del filtro
        current_session: Sesión actual del mercado (para filtros de post-market)
        
    Returns:
        True si pasa TODOS los filtros, False si falla alguno
    """
    try:
        # 1. Aplicar filtros numéricos definidos declarativamente
        for min_param, max_param, ticker_field in FILTER_DEFINITIONS:
            min_val = getattr(params, min_param, None) if min_param else None
            max_val = getattr(params, max_param, None) if max_param else None
            ticker_val = getattr(ticker, ticker_field, None)
            
            # Caso especial: RVOL puede ser None en pre-market temprano
            allow_none = (ticker_field == 'rvol')
            
            if not _check_min_max(ticker_val, min_val, max_val, allow_none_ticker=allow_none):
                return False
        
        # 2. Filtro de frescura de datos (requiere lógica especial)
        if params.max_data_age_seconds is not None:
            if ticker.last_trade_timestamp is not None:
                current_time_ns = datetime.now().timestamp() * 1_000_000_000
                age_ns = current_time_ns - ticker.last_trade_timestamp
                age_seconds = age_ns / 1_000_000_000
                if age_seconds > params.max_data_age_seconds:
                    return False
            else:
                # Sin timestamp = rechazar
                return False
        
        # 3. Filtros de listas (sectors, industries, exchanges)
        if params.sectors and ticker.sector not in params.sectors:
            return False
        
        if params.industries and ticker.industry not in params.industries:
            return False
        
        if params.exchanges and ticker.exchange not in params.exchanges:
            return False
        
        # 4. Filtros de Post-Market (solo aplican durante POST_MARKET)
        if current_session == MarketSession.POST_MARKET:
            if not _check_min_max(
                ticker.postmarket_change_percent,
                params.min_postmarket_change_percent,
                params.max_postmarket_change_percent
            ):
                return False
            
            if not _check_min_max(
                ticker.postmarket_volume,
                params.min_postmarket_volume,
                params.max_postmarket_volume
            ):
                return False
        
        return True
    
    except Exception as e:
        logger.error("Error applying filter", error=str(e))
        return False


class FilterEngine:
    """
    Motor de filtros para el Scanner.
    
    Uso:
        engine = FilterEngine(current_session)
        if engine.passes_filter(ticker, filter_config):
            # ticker pasa el filtro
    """
    
    def __init__(self, current_session: Optional[MarketSession] = None):
        self.current_session = current_session
    
    def set_session(self, session: MarketSession) -> None:
        """Actualiza la sesión actual."""
        self.current_session = session
    
    def passes_filter(self, ticker: ScannerTicker, filter_config: FilterConfig) -> bool:
        """
        Verifica si un ticker pasa un filtro específico.
        
        Args:
            ticker: El ticker a verificar
            filter_config: Configuración del filtro
            
        Returns:
            True si pasa, False si no
        """
        if not filter_config.enabled:
            return True
        
        if not filter_config.applies_to_session(self.current_session):
            return True
        
        return apply_filter(ticker, filter_config.parameters, self.current_session)
    
    def passes_all_filters(
        self,
        ticker: ScannerTicker,
        filters: List[FilterConfig]
    ) -> bool:
        """
        Verifica si un ticker pasa TODOS los filtros.
        
        Args:
            ticker: El ticker a verificar
            filters: Lista de configuraciones de filtros
            
        Returns:
            True si pasa todos, False si falla alguno
        """
        for filter_config in filters:
            if not self.passes_filter(ticker, filter_config):
                return False
        return True
