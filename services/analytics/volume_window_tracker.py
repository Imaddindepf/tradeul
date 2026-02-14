"""
Volume Window Tracker - Ultra Optimized Implementation (PER-SECOND PRECISION)

High-performance volume window tracking for real-time market data.
Uses numpy-based circular buffers with symbol pooling for maximum efficiency.

PRECISION: 1 dato por SEGUNDO (no por minuto)
- Recibe aggregates cada segundo del WebSocket
- Almacena volumen acumulado por segundo
- vol_1min = volumen de los últimos 60 segundos EXACTOS

Features:
- O(1) updates and queries
- Memory: ~275 MB for 10000 symbols × 1800 seconds
- Cache-friendly contiguous memory layout
- Thread-safe for asyncio
- Automatic cleanup (circular buffer)

Provides:
- vol_1min: Volume in last 60 seconds
- vol_5min: Volume in last 300 seconds
- vol_10min: Volume in last 600 seconds
- vol_15min: Volume in last 900 seconds
- vol_30min: Volume in last 1800 seconds

Author: Tradeul Team
"""

import numpy as np
from typing import Dict, Optional, Tuple, NamedTuple
from datetime import datetime
from dataclasses import dataclass
import structlog

logger = structlog.get_logger(__name__)


# Type alias for clarity
Timestamp = int  # Unix timestamp in seconds


class VolumeWindowResult(NamedTuple):
    """Result of volume window query"""
    vol_1min: Optional[int]
    vol_5min: Optional[int]
    vol_10min: Optional[int]
    vol_15min: Optional[int]
    vol_30min: Optional[int]


@dataclass(frozen=True)
class TrackerConfig:
    """Configuration for VolumeWindowTracker"""
    max_symbols: int = 10000      # Maximum symbols to track
    window_size: int = 1801       # Seconds of history (1801 to support 30 min = 1800 sec lookback)
    min_data_points: int = 2      # Minimum points needed for calculation


class VolumeWindowTracker:
    """
    Ultra-optimized volume window tracker using numpy circular buffers.
    
    Architecture:
    - Single contiguous numpy arrays for all symbols (cache-friendly)
    - Symbol → index mapping for O(1) lookup
    - Circular buffer with head pointer (no memory allocation on update)
    - Minute-granularity timestamps for precise window calculations
    
    Memory Layout:
    ┌─────────────────────────────────────────────────────────────┐
    │  timestamps[symbol_idx, minute_idx] = unix_timestamp        │
    │  volumes[symbol_idx, minute_idx] = accumulated_volume       │
    │  heads[symbol_idx] = current head position                  │
    │  counts[symbol_idx] = valid data points count               │
    └─────────────────────────────────────────────────────────────┘
    
    Example:
        tracker = VolumeWindowTracker()
        tracker.update("AAPL", volume=1500000, timestamp=now)
        result = tracker.get_all_windows("AAPL")
        # result.vol_5min = volume traded in last 5 minutes
    """
    
    __slots__ = (
        'config', 'symbol_index', 'next_index',
        'timestamps', 'volumes', 'heads', 'counts',
        '_last_update_second'
    )
    
    def __init__(self, config: Optional[TrackerConfig] = None):
        """
        Initialize the volume window tracker.
        
        Args:
            config: Optional configuration. Uses defaults if not provided.
        """
        self.config = config or TrackerConfig()
        
        # Symbol → array index mapping
        self.symbol_index: Dict[str, int] = {}
        self.next_index: int = 0
        
        # Pre-allocated numpy arrays (contiguous memory)
        # Using int64 for timestamps (unix seconds) and volumes
        self.timestamps = np.zeros(
            (self.config.max_symbols, self.config.window_size),
            dtype=np.int64
        )
        self.volumes = np.zeros(
            (self.config.max_symbols, self.config.window_size),
            dtype=np.int64
        )
        
        # Head pointers and counts (int32 sufficient)
        self.heads = np.zeros(self.config.max_symbols, dtype=np.int32)
        self.counts = np.zeros(self.config.max_symbols, dtype=np.int32)
        
        # Track last update minute per symbol to avoid duplicate updates
        self._last_update_second = np.zeros(self.config.max_symbols, dtype=np.int64)
        
        # Calculate memory usage
        memory_bytes = (
            self.timestamps.nbytes + 
            self.volumes.nbytes + 
            self.heads.nbytes + 
            self.counts.nbytes +
            self._last_update_second.nbytes
        )
        
        logger.info(
            "volume_window_tracker_initialized",
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
            # In production, could implement LRU eviction here
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
        volume_accumulated: int,
        timestamp: Optional[int] = None
    ) -> bool:
        """
        Update volume for a symbol.
        
        Only stores one data point per minute. If called multiple times
        within the same minute, updates the existing value.
        
        Args:
            symbol: Ticker symbol
            volume_accumulated: Today's accumulated volume (from Polygon av)
            timestamp: Unix timestamp in seconds (default: now)
            
        Returns:
            True if new minute recorded, False if same minute updated
        """
        if timestamp is None:
            timestamp = int(datetime.now().timestamp())
        
        # Use exact second (no rounding) for per-second precision
        second_ts = timestamp
        
        try:
            idx = self._get_or_create_index(symbol)
        except RuntimeError:
            return False
        
        # Check if this is the same second as last update
        if self._last_update_second[idx] == second_ts:
            # Same second - update in place (no head advance)
            head = self.heads[idx]
            self.volumes[idx, head] = volume_accumulated
            return False
        
        # New second - advance head
        self._last_update_second[idx] = second_ts
        
        # Move head forward (circular)
        new_head = (self.heads[idx] + 1) % self.config.window_size
        self.heads[idx] = new_head
        
        # Store data
        self.timestamps[idx, new_head] = second_ts
        self.volumes[idx, new_head] = volume_accumulated
        
        # Increment count (up to window_size)
        if self.counts[idx] < self.config.window_size:
            self.counts[idx] += 1
        
        return True
    
    def get_volume_window(
        self,
        symbol: str,
        minutes: int,
        current_timestamp: Optional[int] = None
    ) -> Optional[int]:
        """
        Get volume traded in the last N minutes.
        
        Uses the tracker's latest timestamp as reference (not datetime.now()).
        Calculates: current_accumulated_volume - volume_N_minutes_ago
        
        IMPORTANTE: Valida que el dato encontrado este realmente dentro de la
        ventana de tiempo esperada. En After Hours con bajo volumen, puede haber
        gaps largos entre datos que darian resultados incorrectos.
        
        Args:
            symbol: Ticker symbol
            minutes: Window size (1, 5, 10, 15, 30)
            current_timestamp: Ignored - uses tracker's latest timestamp
            
        Returns:
            Volume traded in window, or None if insufficient data or data gap too large
        """
        if symbol not in self.symbol_index:
            return None
        
        idx = self.symbol_index[symbol]
        count = self.counts[idx]
        
        if count < self.config.min_data_points:
            return None
        
        head = self.heads[idx]
        
        # Get current (most recent) volume and timestamp
        vol_now = self.volumes[idx, head]
        ts_now = self.timestamps[idx, head]  # This is our reference point
        
        # Target is N minutes before ts_now (our latest data point)
        window_seconds = minutes * 60
        target_timestamp = ts_now - window_seconds
        
        # Tolerancia maxima: ventana + 15 segundos (para cubrir delays de red/procesamiento)
        # NO usamos 2x porque eso daría números inflados
        max_acceptable_gap = window_seconds + 15
        
        # Search backwards for timestamp closest to target
        vol_past = None
        ts_past_found = None
        
        for i in range(1, count):
            # Circular index going backwards
            past_idx = (head - i) % self.config.window_size
            ts_past = self.timestamps[idx, past_idx]
            
            if ts_past <= target_timestamp:
                vol_past = self.volumes[idx, past_idx]
                ts_past_found = ts_past
                break
        
        if vol_past is None or ts_past_found is None:
            # Not enough history
            return None
        
        # VALIDACION: Verificar que el gap no sea demasiado grande
        # Si el dato encontrado es de hace mas de 2x la ventana, el calculo no es valido
        actual_gap = ts_now - ts_past_found
        if actual_gap > max_acceptable_gap:
            # Gap demasiado grande - datos no son confiables para esta ventana
            return None
        
        # Volume in window = current - past
        window_vol = vol_now - vol_past
        
        # Sanity check (volume should be non-negative)
        # Convert numpy.int64 to native Python int for JSON serialization
        return int(max(0, window_vol))
    
    def get_all_windows(
        self,
        symbol: str,
        current_timestamp: Optional[int] = None
    ) -> VolumeWindowResult:
        """
        Get all volume windows for a symbol in one call.
        
        Uses the MOST RECENT timestamp in the tracker as reference point,
        not datetime.now(). This ensures consistency regardless of processing delays.
        
        IMPORTANTE: Valida que cada dato encontrado este realmente dentro de una
        ventana razonable (2x el tiempo de la ventana). En After Hours con bajo
        volumen, puede haber gaps largos que darian resultados incorrectos.
        
        Args:
            symbol: Ticker symbol
            current_timestamp: Ignored - uses tracker's latest timestamp
            
        Returns:
            VolumeWindowResult with vol_1min, vol_5min, vol_10min, vol_15min, vol_30min
        """
        if symbol not in self.symbol_index:
            return VolumeWindowResult(None, None, None, None, None)
        
        idx = self.symbol_index[symbol]
        count = self.counts[idx]
        
        if count < self.config.min_data_points:
            return VolumeWindowResult(None, None, None, None, None)
        
        head = self.heads[idx]
        vol_now = self.volumes[idx, head]
        ts_now = self.timestamps[idx, head]  # This is our reference point
        
        # Use ts_now (latest data point) as reference, not datetime.now()
        # This makes calculations independent of processing delays
        
        # Window sizes in seconds and their max acceptable gaps
        # Tolerancia: ventana + 15 segundos (para cubrir delays de red/procesamiento)
        # NO usamos 2x porque eso daría números inflados
        windows_config = {
            1: (60, 75),       # 1 min window, max 1:15 gap (15s tolerancia)
            5: (300, 315),     # 5 min window, max 5:15 gap (15s tolerancia)
            10: (600, 615),    # 10 min window, max 10:15 gap (15s tolerancia)
            15: (900, 915),    # 15 min window, max 15:15 gap (15s tolerancia)
            30: (1800, 1815),  # 30 min window, max 30:15 gap (15s tolerancia)
        }
        
        # Target timestamps for each window
        targets = {mins: ts_now - window_secs for mins, (window_secs, _) in windows_config.items()}
        
        # Single pass through history to find all targets
        results = {1: None, 5: None, 10: None, 15: None, 30: None}
        found_targets = set()
        
        for i in range(1, count):
            past_idx = (head - i) % self.config.window_size
            ts_past = self.timestamps[idx, past_idx]
            vol_past = self.volumes[idx, past_idx]
            
            # Check each target we haven't found yet
            for mins, target_ts in targets.items():
                if mins not in found_targets and ts_past <= target_ts:
                    # VALIDACION: Verificar que el gap no sea demasiado grande
                    actual_gap = ts_now - ts_past
                    _, max_gap = windows_config[mins]
                    
                    if actual_gap <= max_gap:
                        # Gap aceptable - calcular volumen
                        results[mins] = int(max(0, vol_now - vol_past))
                    # else: Gap demasiado grande, dejar como None
                    
                    found_targets.add(mins)
            
            # Early exit if all found
            if len(found_targets) == 5:
                break
        
        return VolumeWindowResult(
            vol_1min=results[1],
            vol_5min=results[5],
            vol_10min=results[10],
            vol_15min=results[15],
            vol_30min=results[30]
        )
    
    def get_stats(self) -> Dict:
        """
        Get tracker statistics for monitoring.
        
        Returns:
            Dict with symbols_tracked, memory_usage, etc.
        """
        memory_bytes = (
            self.timestamps.nbytes + 
            self.volumes.nbytes + 
            self.heads.nbytes + 
            self.counts.nbytes +
            self._last_update_second.nbytes
        )
        
        active_symbols = sum(1 for c in self.counts if c > 0)
        
        return {
            "symbols_registered": len(self.symbol_index),
            "symbols_active": active_symbols,
            "max_symbols": self.config.max_symbols,
            "window_size_minutes": self.config.window_size,
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
        self.volumes[idx, :] = 0
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
        self.volumes.fill(0)
        self.heads.fill(0)
        self.counts.fill(0)
        self._last_update_second.fill(0)
        
        # Keep symbol_index mapping (symbols don't change)
        # Just reset their data
        
        logger.info("volume_window_tracker_cleared", symbols=count)
        
        return count


# Singleton instance for global access (optional pattern)
_tracker_instance: Optional[VolumeWindowTracker] = None


def get_tracker() -> VolumeWindowTracker:
    """Get or create the global tracker instance."""
    global _tracker_instance
    if _tracker_instance is None:
        _tracker_instance = VolumeWindowTracker()
    return _tracker_instance

