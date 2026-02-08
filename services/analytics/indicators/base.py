"""
BaseIndicator - Abstract interface for all analytical indicators.

Every indicator implements this interface so they can be registered
in the IndicatorRegistry and applied uniformly during enrichment.

Two categories of indicators:
1. Snapshot-based: calculated from REST snapshot data (full market coverage)
2. Stream-based: fed by WebSocket stream consumers (subscribed tickers only)

For stream-based indicators, the consumer feeds the tracker,
and the enrichment pipeline reads from the tracker during apply().
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any


class BaseIndicator(ABC):
    """
    Abstract base class for all indicators.
    
    Subclasses must implement:
    - name: unique identifier
    - apply(): add indicator fields to ticker data
    - reset(): clear state for new trading day
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name for this indicator (e.g., 'rvol', 'vol_windows', 'rsi_14')."""
        ...
    
    @property
    def requires_stream(self) -> bool:
        """
        Whether this indicator requires a stream consumer.
        If True, a corresponding consumer must be registered.
        Default: False (snapshot-based).
        """
        return False
    
    @abstractmethod
    def apply(self, symbol: str, ticker_data: dict, context: Dict[str, Any]) -> None:
        """
        Apply indicator calculations to ticker_data (in-place mutation).
        
        Args:
            symbol: Ticker symbol
            ticker_data: Mutable dict of ticker data (will be written to Redis Hash)
            context: Shared context with prices, volumes, etc.
                - 'now': datetime in ET
                - 'volume': accumulated volume
                - 'price': current price
                - 'day_data': day bar dict
                - 'min_data': minute bar dict
                - Additional context from other indicators
        """
        ...
    
    @abstractmethod
    def reset(self) -> None:
        """Reset state for new trading day."""
        ...
    
    def get_stats(self) -> Optional[dict]:
        """Optional: return monitoring stats."""
        return None
