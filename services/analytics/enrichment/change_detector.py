"""
Change Detector - Detects which tickers changed between enrichment cycles.

Uses byte-level comparison of orjson-serialized ticker data to avoid
writing unchanged data to Redis.

Architecture:
    - Keeps previous cycle's serialized bytes in memory (Dict[str, bytes])
    - Each cycle: serialize current ticker -> compare with previous bytes
    - Only tickers with different bytes are marked as "changed"
    - Memory footprint: ~11K tickers x ~600 bytes = ~6.6MB (acceptable)

Metrics tracked:
    - Serialization throughput (bytes/cycle, bytes/second)
    - Write throughput (bytes actually sent to Redis)
    - Change rate (% of tickers that changed per cycle)
"""

import time
import orjson
from typing import Dict, Tuple
from shared.utils.logger import get_logger

logger = get_logger(__name__)


class ChangeDetector:
    """
    Detects changed tickers between consecutive enrichment cycles
    using byte-level comparison of serialized data.
    """

    def __init__(self):
        self._prev_bytes: Dict[str, bytes] = {}

        # Counters
        self._cycle_count: int = 0
        self._total_compared: int = 0
        self._total_changed: int = 0

        # Throughput tracking
        self._total_serialized_bytes: int = 0
        self._total_written_bytes: int = 0
        self._last_cycle_serialized_bytes: int = 0
        self._last_cycle_written_bytes: int = 0
        self._last_cycle_changed: int = 0
        self._last_cycle_total: int = 0
        self._last_cycle_duration_ms: float = 0.0

    def detect_changes(
        self,
        enriched_tickers: Dict[str, dict]
    ) -> Tuple[Dict[str, str], int, int]:
        """
        Compare current enriched tickers against previous cycle.

        Returns:
            Tuple of (changed_dict, total_count, changed_count)
        """
        t0 = time.monotonic()
        changed: Dict[str, str] = {}
        total = len(enriched_tickers)
        cycle_serialized = 0
        cycle_written = 0

        for symbol, ticker_data in enriched_tickers.items():
            current_bytes = orjson.dumps(ticker_data, option=orjson.OPT_SERIALIZE_NUMPY)
            cycle_serialized += len(current_bytes)

            prev_bytes = self._prev_bytes.get(symbol)

            if current_bytes != prev_bytes:
                decoded = current_bytes.decode("utf-8")
                changed[symbol] = decoded
                cycle_written += len(current_bytes)
                self._prev_bytes[symbol] = current_bytes

        # Track removed tickers
        removed_symbols = set(self._prev_bytes.keys()) - set(enriched_tickers.keys())
        for sym in removed_symbols:
            del self._prev_bytes[sym]

        elapsed_ms = (time.monotonic() - t0) * 1000

        # Update stats
        self._cycle_count += 1
        self._total_compared += total
        self._total_changed += len(changed)
        self._total_serialized_bytes += cycle_serialized
        self._total_written_bytes += cycle_written
        self._last_cycle_serialized_bytes = cycle_serialized
        self._last_cycle_written_bytes = cycle_written
        self._last_cycle_changed = len(changed)
        self._last_cycle_total = total
        self._last_cycle_duration_ms = elapsed_ms

        return changed, total, len(changed)

    def force_full_write(
        self,
        enriched_tickers: Dict[str, dict]
    ) -> Dict[str, str]:
        """
        Force write all tickers (used for first cycle or reset).
        Also updates the internal cache.
        """
        result: Dict[str, str] = {}
        cycle_bytes = 0

        for symbol, ticker_data in enriched_tickers.items():
            serialized = orjson.dumps(ticker_data, option=orjson.OPT_SERIALIZE_NUMPY)
            result[symbol] = serialized.decode("utf-8")
            self._prev_bytes[symbol] = serialized
            cycle_bytes += len(serialized)

        self._cycle_count += 1
        self._total_compared += len(enriched_tickers)
        self._total_changed += len(enriched_tickers)
        self._total_serialized_bytes += cycle_bytes
        self._total_written_bytes += cycle_bytes
        self._last_cycle_serialized_bytes = cycle_bytes
        self._last_cycle_written_bytes = cycle_bytes
        self._last_cycle_changed = len(enriched_tickers)
        self._last_cycle_total = len(enriched_tickers)

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
        """Get comprehensive statistics for monitoring."""
        avg_change_rate = (
            (self._total_changed / self._total_compared * 100)
            if self._total_compared > 0 else 0
        )

        # Throughput estimates (assuming ~2 cycles/second)
        cycles_per_sec = 2.0
        serialized_mb_s = (
            self._last_cycle_serialized_bytes * cycles_per_sec / (1024 * 1024)
        )
        written_mb_s = (
            self._last_cycle_written_bytes * cycles_per_sec / (1024 * 1024)
        )

        avg_ticker_bytes = (
            self._last_cycle_serialized_bytes / self._last_cycle_total
            if self._last_cycle_total > 0 else 0
        )

        return {
            "cycles": self._cycle_count,
            "cache_size": len(self._prev_bytes),
            "cache_memory_mb": round(
                sum(len(v) for v in self._prev_bytes.values()) / (1024 * 1024), 2
            ),
            "last_cycle": {
                "total": self._last_cycle_total,
                "changed": self._last_cycle_changed,
                "change_pct": round(
                    self._last_cycle_changed / self._last_cycle_total * 100, 1
                ) if self._last_cycle_total > 0 else 0,
                "serialized_mb": round(
                    self._last_cycle_serialized_bytes / (1024 * 1024), 2
                ),
                "written_mb": round(
                    self._last_cycle_written_bytes / (1024 * 1024), 2
                ),
                "saved_mb": round(
                    (self._last_cycle_serialized_bytes - self._last_cycle_written_bytes)
                    / (1024 * 1024), 2
                ),
                "duration_ms": round(self._last_cycle_duration_ms, 1),
                "avg_ticker_bytes": round(avg_ticker_bytes),
            },
            "throughput": {
                "serialization_mb_s": round(serialized_mb_s, 2),
                "write_mb_s": round(written_mb_s, 2),
                "reduction_pct": round(
                    (1 - written_mb_s / serialized_mb_s) * 100, 1
                ) if serialized_mb_s > 0 else 0,
            },
            "cumulative": {
                "total_compared": self._total_compared,
                "total_changed": self._total_changed,
                "avg_change_rate_pct": round(avg_change_rate, 1),
                "total_serialized_gb": round(
                    self._total_serialized_bytes / (1024 * 1024 * 1024), 3
                ),
                "total_written_gb": round(
                    self._total_written_bytes / (1024 * 1024 * 1024), 3
                ),
            },
        }
