"""
IndicatorRegistry - Manages all registered indicators.

Provides a single point to:
- Register new indicators
- Apply all indicators to a ticker during enrichment
- Reset all indicators for new trading day
- Get stats from all indicators

Usage:
    registry = IndicatorRegistry()
    registry.register(RVOLIndicator(rvol_calculator))
    registry.register(VolumeWindowIndicator(volume_tracker))
    # ...
    
    # During enrichment:
    for symbol, ticker_data in tickers.items():
        context = {'now': now, 'volume': volume, 'price': price, ...}
        registry.apply_all(symbol, ticker_data, context)
    
    # On new day:
    registry.reset_all()
"""

from typing import List, Dict, Any, Optional
from .base import BaseIndicator
from shared.utils.logger import get_logger

logger = get_logger(__name__)


class IndicatorRegistry:
    """
    Central registry for all analytical indicators.
    
    Indicators are applied in registration order during enrichment.
    """
    
    def __init__(self):
        self._indicators: List[BaseIndicator] = []
        self._by_name: Dict[str, BaseIndicator] = {}
    
    def register(self, indicator: BaseIndicator) -> None:
        """
        Register an indicator.
        
        Args:
            indicator: Instance implementing BaseIndicator
            
        Raises:
            ValueError: If an indicator with the same name is already registered
        """
        if indicator.name in self._by_name:
            raise ValueError(f"Indicator '{indicator.name}' already registered")
        
        self._indicators.append(indicator)
        self._by_name[indicator.name] = indicator
        
        logger.info(
            "indicator_registered",
            name=indicator.name,
            requires_stream=indicator.requires_stream,
            total_registered=len(self._indicators)
        )
    
    def apply_all(self, symbol: str, ticker_data: dict, context: Dict[str, Any]) -> None:
        """
        Apply all registered indicators to a ticker (in-place).
        
        Args:
            symbol: Ticker symbol
            ticker_data: Mutable dict to enrich
            context: Shared context dict
        """
        for indicator in self._indicators:
            try:
                indicator.apply(symbol, ticker_data, context)
            except Exception as e:
                logger.error(
                    "indicator_apply_error",
                    indicator=indicator.name,
                    symbol=symbol,
                    error=str(e)
                )
    
    def reset_all(self) -> None:
        """Reset all indicators for new trading day."""
        for indicator in self._indicators:
            try:
                indicator.reset()
                logger.info("indicator_reset", name=indicator.name)
            except Exception as e:
                logger.error(
                    "indicator_reset_error",
                    indicator=indicator.name,
                    error=str(e)
                )
    
    def get(self, name: str) -> Optional[BaseIndicator]:
        """Get indicator by name."""
        return self._by_name.get(name)
    
    def get_all_stats(self) -> Dict[str, Any]:
        """Get stats from all indicators."""
        stats = {}
        for indicator in self._indicators:
            indicator_stats = indicator.get_stats()
            if indicator_stats:
                stats[indicator.name] = indicator_stats
        return stats
    
    @property
    def count(self) -> int:
        return len(self._indicators)
    
    @property
    def names(self) -> List[str]:
        return [i.name for i in self._indicators]
