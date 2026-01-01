"""
Technical Indicators Module

All indicators are implemented as SQL expressions for DuckDB.
This allows us to calculate indicators for thousands of tickers in milliseconds.
"""

from .base import IndicatorDefinition, IndicatorGroup, IndicatorRegistry
from .price import PriceIndicators
from .volume import VolumeIndicators
from .momentum import MomentumIndicators
from .trend import TrendIndicators
from .volatility import VolatilityIndicators
from .comparative import ComparativeIndicators
from .fundamentals import FundamentalIndicators

# Register all indicators
def register_all_indicators():
    """Register all available indicators"""
    registry = IndicatorRegistry()
    
    # Price & Returns
    registry.register_group(PriceIndicators())
    
    # Volume
    registry.register_group(VolumeIndicators())
    
    # Momentum
    registry.register_group(MomentumIndicators())
    
    # Trend
    registry.register_group(TrendIndicators())
    
    # Volatility
    registry.register_group(VolatilityIndicators())
    
    # Comparative (Beta, Correlation)
    registry.register_group(ComparativeIndicators())
    
    # Fundamentals (Market Cap, Float)
    registry.register_group(FundamentalIndicators())
    
    return registry


__all__ = [
    "IndicatorDefinition",
    "IndicatorGroup",
    "IndicatorRegistry", 
    "register_all_indicators",
    "PriceIndicators",
    "VolumeIndicators",
    "MomentumIndicators",
    "TrendIndicators",
    "VolatilityIndicators",
    "ComparativeIndicators",
    "FundamentalIndicators",
]

