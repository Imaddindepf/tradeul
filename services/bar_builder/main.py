"""
Bar Builder Service — Real-time OHLC Bar Aggregation + Live Bar Store

Consumes per-second aggregates from Polygon WebSocket stream and builds
multi-timeframe OHLC bars in real-time.

Timeframes: 1min, 2min, 5min, 10min, 15min, 30min, 60min, 240min, 720min

When a bar closes, it's published to:
  - Redis stream: stream:bars:{timeframe}min  (for alert_engine consumption)
  - Redis hash:   bars:{timeframe}min:latest  (latest closed bar per symbol)

NEW (Live Bar Store):
  - Redis hash:   bars:{timeframe}min:current (currently-forming bar per symbol)
    Updated every PUBLISH_CURRENT_INTERVAL seconds. Consumed by api_gateway
    to stitch the live bar at the tail of REST aggregate responses, closing
    the gap between Polygon's REST aggs (which lag) and WebSocket realtime.

NEW (Hydration API):
  - HTTP POST /hydrate {"symbols": ["WNW", ...]}
    Hydrates the in-formation bar for a symbol by fetching Polygon's snapshot
    (`min` field) + today's 1-minute aggregates, then seeding `_current_bars`
    for all timeframes. Used when a new ticker is opened in the chart so the
    last bar is correct even before the first WebSocket A.* aggregate arrives.

This service is the foundation for:
  - Opening Range Breakouts (ORB)
  - Timeframe highs/lows
  - Consolidation breakouts
  - Candlestick patterns
  - Intraday technical indicators (SMA/MACD/Stochastic per timeframe)
  - Zero-gap live charts (TradingView parity)
"""

import os
import asyncio
import json
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

import httpx
import redis.asyncio as aioredis
import structlog
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# ============================================================================
# Configuration
# ============================================================================

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
STREAM_AGGREGATES = os.getenv("STREAM_AGGREGATES", "stream:realtime:aggregates")
CONSUMER_GROUP = "bar_builder"
CONSUMER_NAME = f"bar_builder_{os.getpid()}"

POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "")
HTTP_PORT = int(os.getenv("HTTP_PORT", "8050"))

# Timeframes in minutes. 240=4h, 720=12h cover the frontend's 4hour/12hour.
TIMEFRAMES = [1, 2, 5, 10, 15, 30, 60, 240, 720]

# Max bars to keep per symbol per timeframe (in Redis)
MAX_BARS_HISTORY = 200

# Stream max length per timeframe (auto-trim)
STREAM_MAXLEN = 10_000

# How often to flush in-formation bars to Redis (seconds).
# Lower = more freshness, more Redis writes. 1s is the sweet spot.
PUBLISH_CURRENT_INTERVAL = float(os.getenv("PUBLISH_CURRENT_INTERVAL", "1.0"))

# TTL for current-bar hash entries. Long enough to survive a brief
# bar_builder restart, short enough to garbage-collect inactive tickers.
CURRENT_BAR_TTL = 600  # 10 min

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

    def seed_current_bar(
        self,
        symbol: str,
        timeframe: int,
        bar_start_ms: int,
        o: float,
        h: float,
        l: float,
        c: float,
        v: int,
    ) -> None:
        """
        Seed (or overwrite) the in-formation bar for a symbol/timeframe.

        Used by the hydrator to populate `_current_bars` from Polygon REST
        data before the WebSocket A.* stream catches up. WebSocket updates
        merge on top of this seed.
        """
        bar = Bar(symbol, timeframe, bar_start_ms)
        bar.open = o
        bar.high = h
        bar.low = l
        bar.close = c
        bar.volume = v
        # We don't know trade count / vwap from REST aggs, leave defaults.
        self._current_bars[timeframe][symbol] = bar


# ============================================================================
# Hydrator — populates in-formation bars from Polygon REST
# ============================================================================

class Hydrator:
    """
    On-demand hydration of the in-formation bar for a symbol.

    Combines two Polygon REST sources:
      1. Snapshot (`min` field) — the 1-minute bar currently in formation,
         updated in near-realtime by Polygon's edge.
      2. Today's 1-minute aggregates — closed minute bars for today,
         used to roll-up higher timeframes (5m/15m/30m/1h/4h/12h).

    From these, we reconstruct the in-formation bar for every timeframe
    in TIMEFRAMES and seed the BarAggregator. Subsequent WebSocket A.*
    aggregates merge on top, achieving zero-gap continuity.
    """

    POLYGON_BASE = "https://api.polygon.io"

    def __init__(self, aggregator: "BarAggregator", api_key: str):
        self.aggregator = aggregator
        self.api_key = api_key
        self._client: Optional[httpx.AsyncClient] = None
        self._inflight: Dict[str, asyncio.Task] = {}
        self._cooldown: Dict[str, float] = {}
        self._cooldown_seconds = 30.0

    async def start(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=3.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )

    async def stop(self) -> None:
        for task in self._inflight.values():
            task.cancel()
        self._inflight.clear()
        if self._client:
            await self._client.aclose()

    async def hydrate_symbols(self, symbols: List[str]) -> Dict[str, str]:
        """
        Hydrate a list of symbols (idempotent + deduped + cooldown).

        Returns: dict mapping symbol -> status ("ok" | "skipped_cooldown" | "in_flight" | "error: ...")
        """
        if not self.api_key:
            return {s.upper(): "error: missing POLYGON_API_KEY" for s in symbols}

        results: Dict[str, str] = {}
        now = time.monotonic()

        for raw in symbols:
            symbol = raw.upper().strip()
            if not symbol:
                continue

            if symbol in self._inflight and not self._inflight[symbol].done():
                results[symbol] = "in_flight"
                continue

            last = self._cooldown.get(symbol)
            if last and (now - last) < self._cooldown_seconds:
                results[symbol] = "skipped_cooldown"
                continue

            task = asyncio.create_task(self._hydrate_one(symbol))
            self._inflight[symbol] = task

        # Wait for all kicked-off tasks (but with a per-task wrapper to capture errors)
        pending = [(s, t) for s, t in self._inflight.items() if s in [r.upper() for r in symbols] and not t.done()]
        for symbol, task in pending:
            try:
                await task
                results[symbol] = "ok"
                self._cooldown[symbol] = time.monotonic()
            except Exception as e:
                results[symbol] = f"error: {type(e).__name__}: {e}"
            finally:
                self._inflight.pop(symbol, None)

        return results

    async def _hydrate_one(self, symbol: str) -> None:
        """Fetch Polygon snapshot + today's 1min aggs and seed current bars."""
        if not self._client:
            raise RuntimeError("Hydrator not started")

        # Run both REST calls in parallel.
        snap_task = asyncio.create_task(self._fetch_snapshot(symbol))
        aggs_task = asyncio.create_task(self._fetch_today_minute_aggs(symbol))

        snap_min, today_minutes = await asyncio.gather(snap_task, aggs_task, return_exceptions=True)

        # Normalize: extract the "min" dict from snapshot if successful
        snapshot_min: Optional[Dict] = None
        if isinstance(snap_min, dict):
            snapshot_min = snap_min

        if isinstance(today_minutes, Exception):
            today_minutes = []
        today_minutes_list: List[Dict] = today_minutes or []  # type: ignore[assignment]

        # Decide the authoritative 1-minute bars for today:
        # - Closed minutes come from /aggs (most recent first; we want chronological).
        # - The currently-forming minute (if available) comes from snapshot.min.
        #
        # We merge them so `today_minutes_list` is the complete picture of today.
        merged_minutes = self._merge_aggs_and_snapshot(today_minutes_list, snapshot_min)

        if not merged_minutes:
            logger.info("hydrate_no_data", symbol=symbol)
            return

        # Seed each timeframe by rolling up today's 1-minute bars into the
        # current in-formation bucket.
        for tf in TIMEFRAMES:
            current = self._rollup_to_current_bar(merged_minutes, tf)
            if current is None:
                continue
            self.aggregator.seed_current_bar(
                symbol=symbol,
                timeframe=tf,
                bar_start_ms=current["bar_start"],
                o=current["open"],
                h=current["high"],
                l=current["low"],
                c=current["close"],
                v=current["volume"],
            )

        logger.info(
            "hydrate_ok",
            symbol=symbol,
            minutes=len(merged_minutes),
            snapshot=snapshot_min is not None,
        )

    async def _fetch_snapshot(self, symbol: str) -> Optional[Dict]:
        """
        GET /v2/snapshot/locale/us/markets/stocks/tickers/{symbol}

        Returns the `min` field (OHLCV of currently-forming minute) or None.
        """
        url = f"{self.POLYGON_BASE}/v2/snapshot/locale/us/markets/stocks/tickers/{symbol}"
        try:
            resp = await self._client.get(url, params={"apiKey": self.api_key})
            if resp.status_code != 200:
                return None
            data = resp.json()
            ticker = data.get("ticker") or {}
            mn = ticker.get("min") or {}
            # Polygon's snapshot `min` schema: { av, t (ms), n, o, h, l, c, v, vw }
            if not mn or mn.get("t") in (None, 0):
                return None
            return {
                "t": int(mn["t"]),  # ms
                "o": float(mn.get("o") or 0),
                "h": float(mn.get("h") or 0),
                "l": float(mn.get("l") or 0),
                "c": float(mn.get("c") or 0),
                "v": int(mn.get("v") or 0),
            }
        except Exception as e:
            logger.warning("snapshot_fetch_failed", symbol=symbol, error=str(e))
            return None

    async def _fetch_today_minute_aggs(self, symbol: str) -> List[Dict]:
        """
        GET /v2/aggs/ticker/{symbol}/range/1/minute/{today}/{today}

        Returns today's 1-minute bars in chronological order. Polygon's
        aggregates lag the in-formation minute, hence the snapshot merge.
        """
        # Use America/New_York for the "today" definition.
        # We use the same calendar day in ET via a UTC offset approximation.
        # Worst case we hit a 404 for today=before-market; the merge still works.
        today_et = (datetime.utcnow().date()).isoformat()
        url = f"{self.POLYGON_BASE}/v2/aggs/ticker/{symbol}/range/1/minute/{today_et}/{today_et}"
        try:
            resp = await self._client.get(
                url,
                params={
                    "apiKey": self.api_key,
                    "adjusted": "true",
                    "sort": "asc",
                    "limit": 50000,
                },
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            results = data.get("results") or []
            return [
                {
                    "t": int(r["t"]),
                    "o": float(r["o"]),
                    "h": float(r["h"]),
                    "l": float(r["l"]),
                    "c": float(r["c"]),
                    "v": int(r.get("v") or 0),
                }
                for r in results
                if r.get("t") is not None
            ]
        except Exception as e:
            logger.warning("minute_aggs_fetch_failed", symbol=symbol, error=str(e))
            return []

    @staticmethod
    def _merge_aggs_and_snapshot(
        aggs: List[Dict], snapshot_min: Optional[Dict]
    ) -> List[Dict]:
        """
        Merge today's 1-min aggregates with snapshot.min.

        - If snapshot.min.t > last agg.t: append it (the in-formation minute).
        - If snapshot.min.t == last agg.t: replace (snapshot is fresher).
        - Otherwise: aggs only.
        """
        if not snapshot_min:
            return aggs
        if not aggs:
            return [snapshot_min]

        last_t = aggs[-1]["t"]
        snap_t = snapshot_min["t"]
        if snap_t > last_t:
            return aggs + [snapshot_min]
        if snap_t == last_t:
            return aggs[:-1] + [snapshot_min]
        return aggs

    @staticmethod
    def _rollup_to_current_bar(
        minute_bars: List[Dict], timeframe_min: int
    ) -> Optional[Dict]:
        """
        Given a chronological list of 1-minute bars for today, compute the
        OHLCV of the currently-forming bar of `timeframe_min` minutes.

        We bucket each 1-minute bar by floor(t / tf_ms) and aggregate the
        last (most recent) bucket only.
        """
        if not minute_bars:
            return None
        tf_ms = timeframe_min * 60 * 1000
        last_t = minute_bars[-1]["t"]
        current_bucket_start = (last_t // tf_ms) * tf_ms

        in_bucket = [b for b in minute_bars if b["t"] >= current_bucket_start]
        if not in_bucket:
            return None

        return {
            "bar_start": current_bucket_start,
            "open": in_bucket[0]["o"],
            "high": max(b["h"] for b in in_bucket),
            "low": min(b["l"] for b in in_bucket),
            "close": in_bucket[-1]["c"],
            "volume": sum(b["v"] for b in in_bucket),
        }


# ============================================================================
# Bar Builder Service
# ============================================================================

class BarBuilderService:
    """Main service orchestrator."""

    def __init__(self):
        self.redis: Optional[aioredis.Redis] = None
        self.aggregator = BarAggregator()
        self.hydrator = Hydrator(self.aggregator, POLYGON_API_KEY)
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

        await self.hydrator.start()

        self.running = True

        # Start processing tasks
        tasks = [
            asyncio.create_task(self._consume_aggregates()),
            asyncio.create_task(self._publish_loop()),
            asyncio.create_task(self._publish_current_loop()),
            asyncio.create_task(self._stats_loop()),
        ]

        logger.info(
            "Bar Builder ready",
            timeframes=TIMEFRAMES,
            stream=STREAM_AGGREGATES,
            publish_current_interval=PUBLISH_CURRENT_INTERVAL,
        )

        await asyncio.gather(*tasks)

    async def stop(self):
        """Stop gracefully."""
        self.running = False
        # Flush remaining bars
        completed = self.aggregator.flush_all()
        if completed:
            await self._publish_bars(completed)
        await self.hydrator.stop()
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

            # 3. Once a bar closes, the corresponding entry in :current is
            #    stale (the new in-formation bar will overwrite it on the
            #    next aggregate). Remove it so consumers don't see a closed
            #    bar masquerading as "current".
            current_hash = f"bars:{tf}min:current"
            pipe.hdel(current_hash, symbol)

        try:
            await pipe.execute()
            logger.debug(f"Published {len(bars)} completed bars")
        except Exception as e:
            logger.error(f"Error publishing bars: {e}")

    # ========================================================================
    # Live Bar Store — publish in-formation bars on a fixed cadence.
    # This is the heart of the zero-gap chart: api_gateway reads from these
    # hashes to stitch the live bar onto Polygon REST aggs responses.
    # ========================================================================

    async def _publish_current_loop(self):
        """Flush all in-formation bars to bars:{tf}min:current every N seconds."""
        # Use round() to avoid sleeping for sub-millisecond drift on slow hosts.
        interval = max(0.25, PUBLISH_CURRENT_INTERVAL)
        while self.running:
            await asyncio.sleep(interval)
            try:
                await self._publish_current_bars()
            except Exception as e:
                logger.error(f"Error publishing current bars: {e}")

    async def _publish_current_bars(self):
        """Snapshot all in-formation bars and write them to Redis hashes."""
        # Snapshot first to keep the critical section tiny.
        snapshot: List[tuple[int, str, Dict]] = []
        for tf, bars_for_tf in self.aggregator._current_bars.items():
            for symbol, bar in bars_for_tf.items():
                if bar.open <= 0:
                    continue
                snapshot.append((tf, symbol, bar.to_dict()))

        if not snapshot:
            return

        pipe = self.redis.pipeline()
        touched_keys: set[str] = set()
        for tf, symbol, payload in snapshot:
            key = f"bars:{tf}min:current"
            pipe.hset(key, symbol, json.dumps(payload))
            touched_keys.add(key)
        # Refresh TTL so inactive symbols eventually get evicted by Redis.
        for key in touched_keys:
            pipe.expire(key, CURRENT_BAR_TTL)

        await pipe.execute()

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
# HTTP API — for hydration and health checks
# ============================================================================

class HydrateRequest(BaseModel):
    symbols: List[str]


def build_app(service: "BarBuilderService") -> FastAPI:
    app = FastAPI(title="bar_builder", version="1.0.0")

    @app.get("/health")
    async def health():
        stats = service.aggregator.get_stats()
        return {
            "status": "healthy" if service.running else "starting",
            "redis_connected": service.redis is not None,
            "timeframes": TIMEFRAMES,
            **stats,
        }

    @app.post("/hydrate")
    async def hydrate(req: HydrateRequest):
        """
        Hydrate in-formation bars for one or more symbols from Polygon REST.

        Called by api_gateway when a chart request lands and bars:{tf}:current
        has no entry for the symbol (i.e. fresh ticker the WS hasn't seen yet).

        Body: {"symbols": ["WNW", "AAPL"]}
        """
        if not req.symbols:
            raise HTTPException(400, "No symbols provided")
        if len(req.symbols) > 50:
            raise HTTPException(400, "Max 50 symbols per request")
        results = await service.hydrator.hydrate_symbols(req.symbols)
        # Flush the freshly-seeded bars so api_gateway sees them on its next read.
        try:
            await service._publish_current_bars()
        except Exception as e:
            logger.warning("post_hydrate_flush_failed", error=str(e))
        return {"results": results}

    return app


# ============================================================================
# Main Entry Point
# ============================================================================

async def main():
    service = BarBuilderService()
    app = build_app(service)

    # Run uvicorn server in parallel to the asyncio bar pipeline.
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=HTTP_PORT,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)

    try:
        await asyncio.gather(
            service.start(),
            server.serve(),
        )
    except KeyboardInterrupt:
        await service.stop()
        server.should_exit = True
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        await service.stop()
        raise


if __name__ == "__main__":
    asyncio.run(main())
