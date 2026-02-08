"""
Bar Builder Service — Real-time OHLC Bar Aggregation

Consumes per-second aggregates from Polygon WebSocket stream and builds
multi-timeframe OHLC bars in real-time.

Timeframes: 1min, 2min, 5min, 10min, 15min, 30min, 60min

When a bar closes, it's published to:
  - Redis stream: stream:bars:{timeframe}  (for event_detector consumption)
  - Redis hash: bars:{timeframe}:latest     (latest bar per symbol for lookups)

This service is the foundation for:
  - Opening Range Breakouts (ORB)
  - Timeframe highs/lows
  - Consolidation breakouts
  - Candlestick patterns
  - Intraday technical indicators (SMA/MACD/Stochastic per timeframe)
"""

import os
import asyncio
import json
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

import redis.asyncio as aioredis
import structlog

# ============================================================================
# Configuration
# ============================================================================

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
STREAM_AGGREGATES = os.getenv("STREAM_AGGREGATES", "stream:realtime:aggregates")
CONSUMER_GROUP = "bar_builder"
CONSUMER_NAME = f"bar_builder_{os.getpid()}"

# Timeframes in minutes
TIMEFRAMES = [1, 2, 5, 10, 15, 30, 60]

# Max bars to keep per symbol per timeframe (in Redis)
MAX_BARS_HISTORY = 200

# Stream max length per timeframe (auto-trim)
STREAM_MAXLEN = 10_000

# Logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(20),
)
logger = structlog.get_logger(__name__)


# ============================================================================
# Bar Data Structure
# ============================================================================

class Bar:
    """
    A single OHLCV bar being built in real-time.
    
    Once the bar period ends, it's "closed" and published.
    """
    __slots__ = (
        "symbol", "timeframe", "bar_start", "bar_end",
        "open", "high", "low", "close",
        "volume", "trades", "vwap_numerator", "vwap_denominator",
    )

    def __init__(self, symbol: str, timeframe: int, bar_start: int):
        self.symbol = symbol
        self.timeframe = timeframe
        self.bar_start = bar_start  # Unix ms
        self.bar_end = bar_start + (timeframe * 60 * 1000)  # Unix ms
        self.open = 0.0
        self.high = 0.0
        self.low = float("inf")
        self.close = 0.0
        self.volume = 0
        self.trades = 0
        self.vwap_numerator = 0.0
        self.vwap_denominator = 0

    def update(self, price_open: float, price_high: float, price_low: float,
               price_close: float, vol: int, num_trades: int, vwap: float):
        """Update bar with a new 1-second aggregate."""
        if self.open == 0.0:
            self.open = price_open

        if price_high > self.high:
            self.high = price_high

        if price_low < self.low:
            self.low = price_low

        self.close = price_close
        self.volume += vol
        self.trades += num_trades

        # Accumulate VWAP (volume-weighted)
        if vol > 0 and vwap > 0:
            self.vwap_numerator += vwap * vol
            self.vwap_denominator += vol

    @property
    def vwap(self) -> float:
        if self.vwap_denominator > 0:
            return self.vwap_numerator / self.vwap_denominator
        return self.close

    @property
    def range_pct(self) -> float:
        """Bar range as percentage of open."""
        if self.open > 0 and self.low < float("inf"):
            return ((self.high - self.low) / self.open) * 100
        return 0.0

    @property
    def body_pct(self) -> float:
        """Bar body as percentage of range (0-100)."""
        full_range = self.high - self.low
        if full_range > 0:
            return abs(self.close - self.open) / full_range * 100
        return 0.0

    @property
    def is_bullish(self) -> bool:
        return self.close >= self.open

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "bar_start": self.bar_start,
            "bar_end": self.bar_end,
            "open": round(self.open, 4),
            "high": round(self.high, 4),
            "low": round(self.low, 4) if self.low < float("inf") else round(self.open, 4),
            "close": round(self.close, 4),
            "volume": self.volume,
            "trades": self.trades,
            "vwap": round(self.vwap, 4),
            "range_pct": round(self.range_pct, 4),
            "body_pct": round(self.body_pct, 2),
            "bullish": self.is_bullish,
        }


# ============================================================================
# Bar Aggregator
# ============================================================================

class BarAggregator:
    """
    Aggregates 1-second data into multi-timeframe OHLC bars.
    
    For each symbol and timeframe, maintains the current "building" bar.
    When the current time passes the bar_end, the bar is closed and emitted.
    """

    def __init__(self):
        # Current building bars: {timeframe: {symbol: Bar}}
        self._current_bars: Dict[int, Dict[str, Bar]] = {
            tf: {} for tf in TIMEFRAMES
        }
        # Statistics
        self.bars_closed = 0
        self.updates_processed = 0

    def get_bar_start(self, timestamp_ms: int, timeframe_min: int) -> int:
        """Calculate the bar start time for a given timestamp and timeframe."""
        tf_ms = timeframe_min * 60 * 1000
        return (timestamp_ms // tf_ms) * tf_ms

    def process_aggregate(self, data: Dict) -> List[Dict]:
        """
        Process a 1-second aggregate and return any completed bars.
        
        Args:
            data: Aggregate data with fields: sym, o, h, l, c, v, n, a, s, e
            
        Returns:
            List of completed bar dicts (may be empty)
        """
        self.updates_processed += 1

        symbol = data.get("sym") or data.get("symbol", "")
        if not symbol:
            return []

        # Parse aggregate fields
        try:
            price_open = float(data.get("o", 0) or data.get("open", 0))
            price_high = float(data.get("h", 0) or data.get("high", 0))
            price_low = float(data.get("l", 0) or data.get("low", 0))
            price_close = float(data.get("c", 0) or data.get("close", 0))
            volume = int(data.get("v", 0) or data.get("vol", 0) or 0)
            trades = int(data.get("n", 0) or data.get("trades", 0) or 0)
            vwap = float(data.get("a", 0) or data.get("vwap", 0) or 0)
            timestamp_ms = int(data.get("s", 0) or data.get("timestamp_start", 0) or 0)
        except (ValueError, TypeError):
            return []

        if price_close <= 0 or timestamp_ms <= 0:
            return []

        completed_bars = []

        for tf in TIMEFRAMES:
            bar_start = self.get_bar_start(timestamp_ms, tf)
            current = self._current_bars[tf].get(symbol)

            # Check if we need a new bar
            if current is None or current.bar_start != bar_start:
                # Close the old bar if it exists and has data
                if current is not None and current.open > 0:
                    completed_bars.append(current.to_dict())
                    self.bars_closed += 1

                # Start new bar
                current = Bar(symbol, tf, bar_start)
                self._current_bars[tf][symbol] = current

            # Update current bar
            current.update(price_open, price_high, price_low, price_close,
                          volume, trades, vwap)

        return completed_bars

    def flush_all(self) -> List[Dict]:
        """Close all current bars (called at end of day). Returns completed bars."""
        completed = []
        for tf in TIMEFRAMES:
            for symbol, bar in self._current_bars[tf].items():
                if bar.open > 0:
                    completed.append(bar.to_dict())
            self._current_bars[tf].clear()
        self.bars_closed += len(completed)
        return completed

    def get_stats(self) -> Dict:
        symbols_by_tf = {
            tf: len(bars) for tf, bars in self._current_bars.items()
        }
        return {
            "updates_processed": self.updates_processed,
            "bars_closed": self.bars_closed,
            "active_bars_by_timeframe": symbols_by_tf,
        }


# ============================================================================
# Bar Builder Service
# ============================================================================

class BarBuilderService:
    """Main service orchestrator."""

    def __init__(self):
        self.redis: Optional[aioredis.Redis] = None
        self.aggregator = BarAggregator()
        self.running = False
        self._publish_buffer: List[Dict] = []
        self._flush_interval = 0.5  # Flush publish buffer every 500ms

    async def start(self):
        """Start the bar builder service."""
        logger.info("Starting Bar Builder Service...")

        # Connect to Redis
        self.redis = aioredis.from_url(REDIS_URL, decode_responses=True)
        await self.redis.ping()
        logger.info("Redis connected", url=REDIS_URL)

        # Ensure consumer group exists
        try:
            await self.redis.xgroup_create(
                STREAM_AGGREGATES, CONSUMER_GROUP, id="$", mkstream=True
            )
            logger.info(f"Created consumer group '{CONSUMER_GROUP}'")
        except aioredis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise
            logger.debug(f"Consumer group '{CONSUMER_GROUP}' already exists")

        self.running = True

        # Start processing tasks
        tasks = [
            asyncio.create_task(self._consume_aggregates()),
            asyncio.create_task(self._publish_loop()),
            asyncio.create_task(self._stats_loop()),
        ]

        logger.info(
            "Bar Builder ready",
            timeframes=TIMEFRAMES,
            stream=STREAM_AGGREGATES,
        )

        await asyncio.gather(*tasks)

    async def stop(self):
        """Stop gracefully."""
        self.running = False
        # Flush remaining bars
        completed = self.aggregator.flush_all()
        if completed:
            await self._publish_bars(completed)
        if self.redis:
            await self.redis.close()
        logger.info("Bar Builder stopped")

    # ========================================================================
    # Stream Consumer
    # ========================================================================

    async def _consume_aggregates(self):
        """Consume per-second aggregates from Redis stream."""
        batch_size = 100
        block_ms = 500

        while self.running:
            try:
                results = await self.redis.xreadgroup(
                    CONSUMER_GROUP, CONSUMER_NAME,
                    {STREAM_AGGREGATES: ">"},
                    count=batch_size,
                    block=block_ms,
                )

                if not results:
                    continue

                for stream_name, messages in results:
                    for msg_id, data in messages:
                        completed = self.aggregator.process_aggregate(data)
                        if completed:
                            self._publish_buffer.extend(completed)

                        # ACK the message
                        await self.redis.xack(STREAM_AGGREGATES, CONSUMER_GROUP, msg_id)

            except aioredis.ConnectionError:
                logger.error("Redis connection lost, reconnecting...")
                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"Error in aggregate consumer: {e}")
                await asyncio.sleep(1)

    # ========================================================================
    # Bar Publishing
    # ========================================================================

    async def _publish_loop(self):
        """Periodically flush the publish buffer to Redis streams."""
        while self.running:
            await asyncio.sleep(self._flush_interval)

            if not self._publish_buffer:
                continue

            # Swap buffer atomically
            bars_to_publish = self._publish_buffer
            self._publish_buffer = []

            await self._publish_bars(bars_to_publish)

    async def _publish_bars(self, bars: List[Dict]):
        """Publish completed bars to Redis streams and hashes."""
        if not bars:
            return

        pipe = self.redis.pipeline()

        for bar in bars:
            tf = bar["timeframe"]
            symbol = bar["symbol"]

            # 1. Publish to stream for event consumption
            stream_key = f"stream:bars:{tf}min"
            pipe.xadd(
                stream_key,
                bar,
                maxlen=STREAM_MAXLEN,
                approximate=True,
            )

            # 2. Store latest bar in hash for lookups
            hash_key = f"bars:{tf}min:latest"
            pipe.hset(hash_key, symbol, json.dumps(bar))

        try:
            await pipe.execute()
            logger.debug(f"Published {len(bars)} completed bars")
        except Exception as e:
            logger.error(f"Error publishing bars: {e}")

    # ========================================================================
    # Stats
    # ========================================================================

    async def _stats_loop(self):
        """Log stats periodically."""
        while self.running:
            await asyncio.sleep(60)
            stats = self.aggregator.get_stats()
            logger.info(
                "bar_builder_stats",
                updates=stats["updates_processed"],
                bars_closed=stats["bars_closed"],
                active_bars=stats["active_bars_by_timeframe"],
            )


# ============================================================================
# Main Entry Point
# ============================================================================

async def main():
    service = BarBuilderService()
    try:
        await service.start()
    except KeyboardInterrupt:
        await service.stop()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        await service.stop()
        raise


if __name__ == "__main__":
    asyncio.run(main())
