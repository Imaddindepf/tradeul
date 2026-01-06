"""
Price Window Tracker - Ultra Optimized Implementation (PER-SECOND PRECISION)

High-performance price change tracking for real-time market data.
Uses numpy-based circular buffers with symbol pooling for maximum efficiency.
Mirrors VolumeWindowTracker architecture for consistency.

PRECISION: 1 dato por SEGUNDO (no por minuto)
- Recibe aggregates cada segundo del WebSocket
- Almacena precio por segundo
- chg_1min = cambio % de los últimos 60 segundos EXACTOS

Features:
- O(1) updates and queries
- Memory: ~275 MB for 10000 symbols × 1800 seconds (float64 for prices)
- Cache-friendly contiguous memory layout
- Thread-safe for asyncio
- Automatic cleanup (circular buffer)

Provides:
- chg_1min: Price change % in last 60 seconds
- chg_5min: Price change % in last 300 seconds
- chg_10min: Price change % in last 600 seconds
- chg_15min: Price change % in last 900 seconds
- chg_30min: Price change % in last 1800 seconds
- price_5min_ago: Price exactly 5 minutes ago (for MOMENTUM criteria)

Author: TradeUL Team
"""

import numpy as np
from typing import Dict, Optional, NamedTuple
from datetime import datetime
from dataclasses import dataclass
import structlog

logger = structlog.get_logger(__name__)


# Type alias for clarity
Timestamp = int  # Unix timestamp in seconds


class PriceChangeResult(NamedTuple):
    """Result of price change window query"""
    chg_1min: Optional[float]
    chg_5min: Optional[float]
    chg_10min: Optional[float]
    chg_15min: Optional[float]
    chg_30min: Optional[float]
    price_5min_ago: Optional[float]  # Raw price 5min ago for reference


@dataclass(frozen=True)
class PriceTrackerConfig:
    """Configuration for PriceWindowTracker"""
    max_symbols: int = 10000      # Maximum symbols to track
    window_size: int = 1801       # Seconds of history (1801 to support 30 min = 1800 sec lookback)
    min_data_points: int = 2      # Minimum points needed for calculation


class PriceWindowTracker:
    """
    Ultra-optimized price window tracker using numpy circular buffers.
    
    Architecture:
    - Single contiguous numpy arrays for all symbols (cache-friendly)
    - Symbol → index mapping for O(1) lookup
    - Circular buffer with head pointer (no memory allocation on update)
    - Second-granularity timestamps for precise window calculations
    
    Memory Layout:
    ┌─────────────────────────────────────────────────────────────┐
    │  timestamps[symbol_idx, second_idx] = unix_timestamp        │
    │  prices[symbol_idx, second_idx] = price at that second      │
    │  heads[symbol_idx] = current head position                  │
    │  counts[symbol_idx] = valid data points count               │
    └─────────────────────────────────────────────────────────────┘
    
    Example:
        tracker = PriceWindowTracker()
        tracker.update("AAPL", price=185.50, timestamp=now)
        result = tracker.get_all_windows("AAPL")
        # result.chg_5min = price change % in last 5 minutes
    """
    
    __slots__ = (
        'config', 'symbol_index', 'next_index',
        'timestamps', 'prices', 'heads', 'counts',
        '_last_update_second'
    )
    
    def __init__(self, config: Optional[PriceTrackerConfig] = None):
        """
        Initialize the price window tracker.
        
        Args:
            config: Optional configuration. Uses defaults if not provided.
        """
        self.config = config or PriceTrackerConfig()
        
        # Symbol → array index mapping
        self.symbol_index: Dict[str, int] = {}
        self.next_index: int = 0
        
        # Pre-allocated numpy arrays (contiguous memory)
        # Using int64 for timestamps, float64 for prices (need decimals!)
        self.timestamps = np.zeros(
            (self.config.max_symbols, self.config.window_size),
            dtype=np.int64
        )
        self.prices = np.zeros(
            (self.config.max_symbols, self.config.window_size),
            dtype=np.float64  # float64 for price precision
        )
        
        # Head pointers and counts (int32 sufficient)
        self.heads = np.zeros(self.config.max_symbols, dtype=np.int32)
        self.counts = np.zeros(self.config.max_symbols, dtype=np.int32)
        
        # Track last update second per symbol to avoid duplicate updates
        self._last_update_second = np.zeros(self.config.max_symbols, dtype=np.int64)
        
        # Calculate memory usage
        memory_bytes = (
            self.timestamps.nbytes + 
            self.prices.nbytes + 
            self.heads.nbytes + 
            self.counts.nbytes +
            self._last_update_second.nbytes
        )
        
        logger.info(
            "price_window_tracker_initialized",
            max_symbols=self.config.max_symbols,
            window_size=self.config.window_size,
            memory_mb=round(memory_bytes / 1024 / 1024, 2)
        )
    
    def _get_or_create_index(self, symbol: str) -> int:
        """
        Get existing index or create new one for symbol.
        
        Args:
            symbol: Ticker symbol
            
        Returns:
            Index in the arrays
            
        Raises:
            RuntimeError: If max symbols exceeded
        """
        if symbol in self.symbol_index:
            return self.symbol_index[symbol]
        
        if self.next_index >= self.config.max_symbols:
            logger.warning(
                "max_symbols_reached",
                max=self.config.max_symbols,
                symbol=symbol
            )
            raise RuntimeError(f"Max symbols ({self.config.max_symbols}) exceeded")
        
        idx = self.next_index
        self.symbol_index[symbol] = idx
        self.next_index += 1
        
        return idx
    
    def update(
        self,
        symbol: str,
        price: float,
        timestamp: Optional[int] = None
    ) -> bool:
        """
        Update price for a symbol.
        
        Only stores one data point per second. If called multiple times
        within the same second, updates the existing value.
        
        Args:
            symbol: Ticker symbol
            price: Current price
            timestamp: Unix timestamp in seconds (default: now)
            
        Returns:
            True if new second recorded, False if same second updated
        """
        if timestamp is None:
            timestamp = int(datetime.now().timestamp())
        
        # Ignore invalid prices
        if price <= 0:
            return False
        
        second_ts = timestamp
        
        try:
            idx = self._get_or_create_index(symbol)
        except RuntimeError:
            return False
        
        # Check if this is the same second as last update
        if self._last_update_second[idx] == second_ts:
            # Same second - update in place (no head advance)
            head = self.heads[idx]
            self.prices[idx, head] = price
            return False
        
        # New second - advance head
        self._last_update_second[idx] = second_ts
        
        # Move head forward (circular)
        new_head = (self.heads[idx] + 1) % self.config.window_size
        self.heads[idx] = new_head
        
        # Store data
        self.timestamps[idx, new_head] = second_ts
        self.prices[idx, new_head] = price
        
        # Increment count (up to window_size)
        if self.counts[idx] < self.config.window_size:
            self.counts[idx] += 1
        
        return True
    
    def get_price_change(
        self,
        symbol: str,
        minutes: int,
        current_timestamp: Optional[int] = None
    ) -> Optional[float]:
        """
        Get price change % in the last N minutes.
        
        Uses the tracker's latest timestamp as reference (not datetime.now()).
        Calculates: ((price_now - price_N_min_ago) / price_N_min_ago) * 100
        
        Args:
            symbol: Ticker symbol
            minutes: Window size (1, 5, 10, 15, 30)
            current_timestamp: Ignored - uses tracker's latest timestamp
            
        Returns:
            Price change % in window, or None if insufficient data
        """
        if symbol not in self.symbol_index:
            return None
        
        idx = self.symbol_index[symbol]
        count = self.counts[idx]
        
        if count < self.config.min_data_points:
            return None
        
        head = self.heads[idx]
        
        # Get current (most recent) price and timestamp
        price_now = self.prices[idx, head]
        ts_now = self.timestamps[idx, head]  # This is our reference point
        
        # Target is N minutes before ts_now (our latest data point)
        target_timestamp = ts_now - (minutes * 60)
        
        # Search backwards for timestamp closest to target
        price_past = None
        
        for i in range(1, count):
            # Circular index going backwards
            past_idx = (head - i) % self.config.window_size
            ts_past = self.timestamps[idx, past_idx]
            
            if ts_past <= target_timestamp:
                price_past = self.prices[idx, past_idx]
                break
        
        if price_past is None or price_past <= 0:
            # Not enough history or invalid price
            return None
        
        # Price change % = ((now - past) / past) * 100
        change_pct = ((price_now - price_past) / price_past) * 100
        
        return round(change_pct, 4)
    
    def get_price_at_offset(
        self,
        symbol: str,
        minutes: int
    ) -> Optional[float]:
        """
        Get the price N minutes ago (raw price, not change %).
        
        Args:
            symbol: Ticker symbol
            minutes: Minutes back from latest timestamp
            
        Returns:
            Price at that time, or None if insufficient data
        """
        if symbol not in self.symbol_index:
            return None
        
        idx = self.symbol_index[symbol]
        count = self.counts[idx]
        
        if count < self.config.min_data_points:
            return None
        
        head = self.heads[idx]
        ts_now = self.timestamps[idx, head]
        target_timestamp = ts_now - (minutes * 60)
        
        for i in range(1, count):
            past_idx = (head - i) % self.config.window_size
            ts_past = self.timestamps[idx, past_idx]
            
            if ts_past <= target_timestamp:
                return float(self.prices[idx, past_idx])
        
        return None
    
    def get_all_windows(
        self,
        symbol: str,
        current_timestamp: Optional[int] = None
    ) -> PriceChangeResult:
        """
        Get all price change windows for a symbol in one call.
        
        Uses the MOST RECENT timestamp in the tracker as reference point,
        not datetime.now(). This ensures consistency regardless of processing delays.
        
        Args:
            symbol: Ticker symbol
            current_timestamp: Ignored - uses tracker's latest timestamp
            
        Returns:
            PriceChangeResult with chg_1min, chg_5min, chg_10min, chg_15min, chg_30min
        """
        if symbol not in self.symbol_index:
            return PriceChangeResult(None, None, None, None, None, None)
        
        idx = self.symbol_index[symbol]
        count = self.counts[idx]
        
        if count < self.config.min_data_points:
            return PriceChangeResult(None, None, None, None, None, None)
        
        head = self.heads[idx]
        price_now = self.prices[idx, head]
        ts_now = self.timestamps[idx, head]  # This is our reference point
        
        if price_now <= 0:
            return PriceChangeResult(None, None, None, None, None, None)
        
        # Target timestamps for each window (in seconds from ts_now)
        targets = {
            1: ts_now - 60,    # 1 min = 60 seconds before latest
            5: ts_now - 300,   # 5 min = 300 seconds before latest
            10: ts_now - 600,  # 10 min = 600 seconds before latest
            15: ts_now - 900,  # 15 min = 900 seconds before latest
            30: ts_now - 1800, # 30 min = 1800 seconds before latest
        }
        
        # Single pass through history to find all targets
        results = {1: None, 5: None, 10: None, 15: None, 30: None}
        prices_past = {1: None, 5: None, 10: None, 15: None, 30: None}
        found_targets = set()
        
        for i in range(1, count):
            past_idx = (head - i) % self.config.window_size
            ts_past = self.timestamps[idx, past_idx]
            price_past = self.prices[idx, past_idx]
            
            # Check each target we haven't found yet
            for mins, target_ts in targets.items():
                if mins not in found_targets and ts_past <= target_ts:
                    if price_past > 0:
                        change_pct = ((price_now - price_past) / price_past) * 100
                        results[mins] = round(change_pct, 4)
                        prices_past[mins] = float(price_past)
                    found_targets.add(mins)
            
            # Early exit if all found
            if len(found_targets) == 5:
                break
        
        return PriceChangeResult(
            chg_1min=results[1],
            chg_5min=results[5],
            chg_10min=results[10],
            chg_15min=results[15],
            chg_30min=results[30],
            price_5min_ago=prices_past[5]
        )
    
    def get_current_price(self, symbol: str) -> Optional[float]:
        """
        Get the most recent price for a symbol.
        
        Args:
            symbol: Ticker symbol
            
        Returns:
            Most recent price, or None if not tracked
        """
        if symbol not in self.symbol_index:
            return None
        
        idx = self.symbol_index[symbol]
        if self.counts[idx] == 0:
            return None
        
        head = self.heads[idx]
        return float(self.prices[idx, head])
    
    def get_stats(self) -> Dict:
        """
        Get tracker statistics for monitoring.
        
        Returns:
            Dict with symbols_tracked, memory_usage, etc.
        """
        memory_bytes = (
            self.timestamps.nbytes + 
            self.prices.nbytes + 
            self.heads.nbytes + 
            self.counts.nbytes +
            self._last_update_second.nbytes
        )
        
        active_symbols = sum(1 for c in self.counts if c > 0)
        
        return {
            "symbols_registered": len(self.symbol_index),
            "symbols_active": active_symbols,
            "max_symbols": self.config.max_symbols,
            "window_size_seconds": self.config.window_size,
            "memory_mb": round(memory_bytes / 1024 / 1024, 2),
            "utilization_pct": round(len(self.symbol_index) / self.config.max_symbols * 100, 1)
        }
    
    def clear_symbol(self, symbol: str) -> bool:
        """
        Clear data for a specific symbol.
        
        Args:
            symbol: Ticker symbol
            
        Returns:
            True if symbol existed and was cleared
        """
        if symbol not in self.symbol_index:
            return False
        
        idx = self.symbol_index[symbol]
        
        # Reset arrays for this symbol
        self.timestamps[idx, :] = 0
        self.prices[idx, :] = 0.0
        self.heads[idx] = 0
        self.counts[idx] = 0
        self._last_update_second[idx] = 0
        
        return True
    
    def clear_all(self) -> int:
        """
        Clear all data (for new trading day).
        
        Returns:
            Number of symbols cleared
        """
        count = len(self.symbol_index)
        
        # Reset all arrays
        self.timestamps.fill(0)
        self.prices.fill(0.0)
        self.heads.fill(0)
        self.counts.fill(0)
        self._last_update_second.fill(0)
        
        # Keep symbol_index mapping (symbols don't change)
        # Just reset their data
        
        logger.info("price_window_tracker_cleared", symbols=count)
        
        return count


# Singleton instance for global access (optional pattern)
_tracker_instance: Optional[PriceWindowTracker] = None


def get_price_tracker() -> PriceWindowTracker:
    """Get or create the global price tracker instance."""
    global _tracker_instance
    if _tracker_instance is None:
        _tracker_instance = PriceWindowTracker()
    return _tracker_instance

