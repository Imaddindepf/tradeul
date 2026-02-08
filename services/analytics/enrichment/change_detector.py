"""
Change Detector - Detects which tickers changed between enrichment cycles.

Uses byte-level comparison of orjson-serialized ticker data to avoid
writing unchanged data to Redis. This reduces serialization from ~24MB/s to ~5MB/s.

Architecture:
    - Keeps previous cycle's serialized bytes in memory (Dict[str, bytes])
    - Each cycle: serialize current ticker → compare with previous bytes
    - Only tickers with different bytes are marked as "changed"
    - Memory footprint: ~11K tickers × ~600 bytes = ~6.6MB (acceptable)
"""

import orjson
from typing import Dict, Tuple, Optional
from shared.utils.logger import get_logger

logger = get_logger(__name__)


class ChangeDetector:
    """
    Detects changed tickers between consecutive enrichment cycles
    using byte-level comparison of serialized data.
    """
    
    def __init__(self):
        # Previous cycle's serialized bytes: symbol → orjson bytes
        self._prev_bytes: Dict[str, bytes] = {}
        self._cycle_count: int = 0
        self._total_compared: int = 0
        self._total_changed: int = 0
    
    def detect_changes(
        self,
        enriched_tickers: Dict[str, dict]
    ) -> Tuple[Dict[str, str], int, int]:
        """
        Compare current enriched tickers against previous cycle.
        
        Args:
            enriched_tickers: Dict of {symbol: ticker_data_dict}
            
        Returns:
            Tuple of:
                - changed: Dict[str, str] mapping symbol → serialized JSON string (for HSET)
                - total_count: Total tickers compared
                - changed_count: Number of tickers that actually changed
        """
        changed: Dict[str, str] = {}
        total = len(enriched_tickers)
        
        for symbol, ticker_data in enriched_tickers.items():
            current_bytes = orjson.dumps(ticker_data)
            prev_bytes = self._prev_bytes.get(symbol)
            
            if current_bytes != prev_bytes:
                # Ticker changed - include in HSET
                changed[symbol] = current_bytes.decode("utf-8")
                self._prev_bytes[symbol] = current_bytes
        
        # Track removed tickers (were in previous but not in current)
        removed_symbols = set(self._prev_bytes.keys()) - set(enriched_tickers.keys())
        if removed_symbols:
            for sym in removed_symbols:
                del self._prev_bytes[sym]
        
        # Update stats
        self._cycle_count += 1
        self._total_compared += total
        self._total_changed += len(changed)
        
        return changed, total, len(changed)
    
    def force_full_write(
        self,
        enriched_tickers: Dict[str, dict]
    ) -> Dict[str, str]:
        """
        Force write all tickers (used for first cycle or reset).
        Also updates the internal cache.
        
        Args:
            enriched_tickers: Dict of {symbol: ticker_data_dict}
            
        Returns:
            Dict[str, str] mapping symbol → serialized JSON string
        """
        result: Dict[str, str] = {}
        
        for symbol, ticker_data in enriched_tickers.items():
            serialized = orjson.dumps(ticker_data)
            result[symbol] = serialized.decode("utf-8")
            self._prev_bytes[symbol] = serialized
        
        self._cycle_count += 1
        self._total_compared += len(enriched_tickers)
        self._total_changed += len(enriched_tickers)
        
        return result
    
    @property
    def is_first_cycle(self) -> bool:
        """Returns True if no previous data exists (first cycle after startup)."""
        return len(self._prev_bytes) == 0
    
    def clear(self) -> None:
        """Clear all cached data (used on new trading day)."""
        count = len(self._prev_bytes)
        self._prev_bytes.clear()
        logger.info("change_detector_cleared", prev_cache_size=count)
    
    def get_stats(self) -> dict:
        """Get statistics for monitoring."""
        avg_change_rate = (
            (self._total_changed / self._total_compared * 100)
            if self._total_compared > 0 else 0
        )
        return {
            "cycles": self._cycle_count,
            "cache_size": len(self._prev_bytes),
            "cache_memory_estimate_mb": round(
                sum(len(v) for v in self._prev_bytes.values()) / (1024 * 1024), 2
            ),
            "total_compared": self._total_compared,
            "total_changed": self._total_changed,
            "avg_change_rate_pct": round(avg_change_rate, 1),
        }
