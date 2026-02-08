"""
Event Detector Service - Main entry point.

Consumes real-time aggregate streams and detects market events using
a plugin-based architecture. Each detector plugin handles a category
of events (price, volume, VWAP, momentum, pullbacks, gaps).

ARQUITECTURA EVENT-DRIVEN:
- Se suscribe a DAY_CHANGED del EventBus (market_session es la fuente de verdad)
- NO detecta días nuevos por sí mismo
- Verifica festivos antes de resetear cachés
- Usa timezone America/New_York (ET) en todo

Data flow:
  stream:realtime:aggregates → Build TickerState → Run all detectors → stream:events:market
  stream:halt:events → Process halt/resume → stream:events:market
"""

import asyncio
import json
import logging
import signal
from datetime import datetime, date
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

import redis.asyncio as aioredis

from shared.config.settings import settings
from shared.utils.redis_client import RedisClient
from shared.events import EventBus, EventType as BusEventType, Event

from models import EventRecord, EventType, TickerState, TickerStateCache
from detectors import ALL_DETECTOR_CLASSES, PriceEventsDetector
from store import EventStore

# Timezone
ET = ZoneInfo("America/New_York")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("event-detector")

# ============================================================================
# GLOBAL STATE (same pattern as scanner/analytics)
# ============================================================================

redis_client: Optional[RedisClient] = None
event_bus: Optional[EventBus] = None
engine: Optional["EventEngine"] = None

is_holiday_mode: bool = False
current_trading_date: Optional[date] = None

STREAM_EVENTS = "stream:events:market"


# ============================================================================
# MARKET STATUS (same as scanner/analytics)
# ============================================================================

async def check_initial_market_status() -> None:
    """
    Lee el estado del mercado UNA VEZ al iniciar.
    Determina si es día festivo para evitar resetear cachés.
    """
    global is_holiday_mode, current_trading_date

    try:
        status_data = await redis_client.get(f"{settings.key_prefix_market}:session:status")

        if status_data:
            is_holiday = status_data.get('is_holiday', False)
            is_trading_day = status_data.get('is_trading_day', True)
            trading_date_str = status_data.get('trading_date')

            is_holiday_mode = is_holiday or not is_trading_day

            if trading_date_str:
                current_trading_date = date.fromisoformat(trading_date_str)

            logger.info(
                f"📅 Market status: holiday={is_holiday}, trading_day={is_trading_day}, "
                f"holiday_mode={is_holiday_mode}, date={trading_date_str}"
            )

            if is_holiday_mode:
                logger.warning("🚨 HOLIDAY_MODE_ACTIVE - Event Detector will reduce activity")
        else:
            logger.warning("Market status not found in Redis")
            is_holiday_mode = False

    except Exception as e:
        logger.error(f"Error checking market status: {e}")
        is_holiday_mode = False


# ============================================================================
# EVENT BUS HANDLERS (same pattern as scanner/analytics)
# ============================================================================

async def handle_day_changed(event: Event) -> None:
    """
    Handler para el evento DAY_CHANGED.
    Se ejecuta cuando market_session detecta un nuevo día de trading.

    IMPORTANTE: Solo resetea cachés si NO es día festivo.
    """
    global is_holiday_mode, current_trading_date

    new_date_str = event.data.get('new_date')
    logger.info(f"📆 DAY_CHANGED event received: {new_date_str}")

    # Re-verificar estado del mercado
    await check_initial_market_status()

    # Solo resetear si NO es festivo
    if not is_holiday_mode:
        logger.info("🔄 Resetting event detector caches for new trading day")

        if engine:
            await engine.reset_for_new_day()

        logger.info("✅ Daily reset complete")
    else:
        logger.info(f"⏭️ Skipping cache reset - holiday mode active (date={new_date_str})")


async def handle_session_changed(event: Event) -> None:
    """Handler para SESSION_CHANGED - log informativo."""
    from_session = event.data.get('from_session', '?')
    to_session = event.data.get('to_session', '?')
    logger.info(f"📊 Session changed: {from_session} → {to_session}")


# ============================================================================
# EVENT ENGINE
# ============================================================================

class EventEngine:
    """
    Main event detection engine.

    Loads all detector plugins and runs them against every aggregate tick.
    Uses RedisClient (shared wrapper) for all Redis operations.
    """

    def __init__(self, redis: RedisClient):
        self.redis = redis
        # Raw async redis client for stream operations (xread, xadd, etc.)
        self.raw_redis: Optional[aioredis.Redis] = None
        self.running = False

        # State cache for tracking previous values
        self.state_cache = TickerStateCache(max_age_seconds=3600)

        # Event store for recent events (in-memory)
        self.event_store = EventStore(max_age_seconds=3600)

        # Enriched data cache (from Analytics service)
        self._enriched_cache: Dict[str, Dict] = {}

        # Daily indicators cache (from Screener service via Redis)
        self._screener_cache: Dict[str, Dict] = {}

        # Initialize all detector plugins
        self.detectors = [cls() for cls in ALL_DETECTOR_CLASSES]

        # Keep reference to price detector for tracked extremes management
        self.price_detector: Optional[PriceEventsDetector] = None
        for d in self.detectors:
            if isinstance(d, PriceEventsDetector):
                self.price_detector = d
                break

        detector_names = [d.__class__.__name__ for d in self.detectors]
        logger.info(f"Loaded {len(self.detectors)} detector plugins: {detector_names}")

    # ========================================================================
    # LIFECYCLE
    # ========================================================================

    async def start(self):
        """Start the event detection engine."""
        logger.info("Starting Event Detector Engine...")

        # Get raw redis client for stream operations
        self.raw_redis = self.redis.client
        self.running = True

        # Load enriched data and initialize detectors
        await self._refresh_enriched_cache()
        logger.info(f"Loaded enriched cache: {len(self._enriched_cache)} tickers")

        # Load daily indicators from screener
        await self._refresh_screener_cache()
        logger.info(f"Loaded screener cache: {len(self._screener_cache)} tickers")

        if self.price_detector:
            await self._initialize_tracked_extremes()

        # Start consumer tasks
        tasks = [
            asyncio.create_task(self._consume_aggregates_loop()),
            asyncio.create_task(self._consume_halts_loop()),
            asyncio.create_task(self._enriched_refresh_loop()),
            asyncio.create_task(self._screener_refresh_loop()),
            asyncio.create_task(self._cleanup_loop()),
        ]

        await asyncio.gather(*tasks)

    async def stop(self):
        """Stop the engine gracefully."""
        logger.info("Stopping Event Detector Engine...")
        self.running = False

    async def reset_for_new_day(self):
        """
        Full reset for a new trading day.

        Called by DAY_CHANGED event handler (from EventBus).
        Resets all in-memory tracking and cleans the Redis event stream.
        """
        logger.info("🔄 Starting daily reset...")

        # 1. Reset ALL detector plugins (cooldowns + custom tracking)
        for detector in self.detectors:
            detector.reset_daily()
        logger.info("✅ All detector plugins reset")

        # 2. Clear state cache (previous ticker states)
        old_states = self.state_cache.size
        self.state_cache.clear()
        logger.info(f"✅ State cache cleared ({old_states} states)")

        # 3. Clear in-memory event store
        old_events = self.event_store.size
        self.event_store = EventStore(max_age_seconds=3600)
        logger.info(f"✅ Event store cleared ({old_events} events)")

        # 4. Trim Redis event stream (clear yesterday's events)
        try:
            await self.raw_redis.xtrim(STREAM_EVENTS, maxlen=0)
            logger.info(f"✅ Redis stream '{STREAM_EVENTS}' trimmed")
        except Exception as e:
            logger.error(f"Error trimming Redis stream: {e}")

        # 5. Refresh enriched cache from fresh data
        await self._refresh_enriched_cache()
        logger.info(f"✅ Enriched cache refreshed: {len(self._enriched_cache)} tickers")

        # 5b. Refresh screener daily indicators
        await self._refresh_screener_cache()
        logger.info(f"✅ Screener cache refreshed: {len(self._screener_cache)} tickers")

        # 6. Re-initialize tracked extremes from fresh enriched data
        if self.price_detector:
            await self._initialize_tracked_extremes()

        logger.info("✅ Daily reset complete")

    # ========================================================================
    # STREAM CONSUMERS
    # ========================================================================

    async def _consume_aggregates_loop(self):
        """
        Consume aggregate stream using XREADGROUP (consumer group) for reliable processing.

        ARCHITECTURE:
        - Consumer group 'event_detector_aggregates' ensures only this service processes each message
        - XACK after processing guarantees no re-delivery of processed messages
        - Auto-healing: recreates consumer group if missing (NOGROUP error)
        - Separate group from websocket_server_aggregates → both services get all messages
        """
        stream_name = "stream:realtime:aggregates"
        consumer_group = "event_detector_aggregates"
        consumer_name = "detector_1"

        logger.info(f"Consuming {stream_name} (consumer group: {consumer_group})")

        # Create consumer group (idempotent - BUSYGROUP if already exists)
        try:
            await self.raw_redis.xgroup_create(
                stream_name, consumer_group, id="$", mkstream=True
            )
            logger.info(f"✅ Created consumer group '{consumer_group}' for {stream_name}")
        except Exception as e:
            if "BUSYGROUP" in str(e):
                logger.debug(f"Consumer group '{consumer_group}' already exists")
            else:
                logger.error(f"Error creating consumer group: {e}")

        while self.running:
            try:
                # Skip processing in holiday mode (reduce CPU)
                if is_holiday_mode:
                    await asyncio.sleep(30)
                    continue

                # XREADGROUP: This consumer group is separate from websocket_server's group
                # Both get all messages, but within this group, only one instance processes each
                messages = await self.raw_redis.xreadgroup(
                    consumer_group, consumer_name,
                    {stream_name: ">"},
                    count=100,
                    block=1000
                )

                if not messages:
                    continue

                msg_ids = []
                for stream, entries in messages:
                    for msg_id, data in entries:
                        msg_ids.append(msg_id)
                        await self._process_aggregate(data)

                # ACK processed messages - prevents re-delivery on restart
                if msg_ids:
                    try:
                        await self.raw_redis.xack(stream_name, consumer_group, *msg_ids)
                    except Exception as e:
                        logger.error(f"Error ACKing aggregate messages: {e}")

            except Exception as e:
                error_msg = str(e)
                # Auto-healing: recreate consumer group if missing
                if "NOGROUP" in error_msg:
                    logger.warning(f"🔧 Consumer group '{consumer_group}' missing - recreating")
                    try:
                        await self.raw_redis.xgroup_create(
                            stream_name, consumer_group, id="0", mkstream=True
                        )
                        logger.info(f"✅ Consumer group '{consumer_group}' recreated")
                        continue
                    except Exception as re_err:
                        logger.error(f"Failed to recreate consumer group: {re_err}")
                logger.error(f"Error consuming aggregates: {e}")
                await asyncio.sleep(1)

    async def _consume_halts_loop(self):
        """
        Consume halt events stream using XREADGROUP (consumer group).

        Same pattern as aggregates - uses consumer group for reliable processing.
        """
        stream_name = "stream:halt:events"
        consumer_group = "event_detector_halts"
        consumer_name = "detector_1"

        logger.info(f"Consuming {stream_name} (consumer group: {consumer_group})")

        # Create consumer group
        try:
            await self.raw_redis.xgroup_create(
                stream_name, consumer_group, id="$", mkstream=True
            )
            logger.info(f"✅ Created consumer group '{consumer_group}' for {stream_name}")
        except Exception as e:
            if "BUSYGROUP" in str(e):
                logger.debug(f"Consumer group '{consumer_group}' already exists")
            else:
                logger.error(f"Error creating consumer group: {e}")

        while self.running:
            try:
                messages = await self.raw_redis.xreadgroup(
                    consumer_group, consumer_name,
                    {stream_name: ">"},
                    count=100,
                    block=1000
                )

                if not messages:
                    continue

                msg_ids = []
                for stream, entries in messages:
                    for msg_id, data in entries:
                        msg_ids.append(msg_id)
                        await self._process_halt_event(data)

                # ACK processed messages
                if msg_ids:
                    try:
                        await self.raw_redis.xack(stream_name, consumer_group, *msg_ids)
                    except Exception as e:
                        logger.error(f"Error ACKing halt messages: {e}")

            except Exception as e:
                error_msg = str(e)
                # Auto-healing
                if "NOGROUP" in error_msg:
                    logger.warning(f"🔧 Consumer group '{consumer_group}' missing - recreating")
                    try:
                        await self.raw_redis.xgroup_create(
                            stream_name, consumer_group, id="0", mkstream=True
                        )
                        logger.info(f"✅ Consumer group '{consumer_group}' recreated")
                        continue
                    except Exception as re_err:
                        logger.error(f"Failed to recreate consumer group: {re_err}")
                logger.error(f"Error consuming halts: {e}")
                await asyncio.sleep(1)

    # ========================================================================
    # AGGREGATE PROCESSING
    # ========================================================================

    async def _process_aggregate(self, data: Dict):
        """Process a single aggregate tick through all detectors."""
        try:
            symbol = data.get("sym") or data.get("symbol")
            if not symbol:
                return

            # Build TickerState from aggregate + enriched cache
            current = await self._build_ticker_state(symbol, data)
            if current is None:
                return

            # Get previous state
            previous = self.state_cache.get(symbol)

            # Run ALL detectors
            all_events: List[EventRecord] = []
            for detector in self.detectors:
                try:
                    events = detector.detect(current, previous)
                    all_events.extend(events)
                except Exception as e:
                    logger.error(f"Detector {detector.__class__.__name__} error for {symbol}: {e}")

            # Store current state for next comparison
            self.state_cache.set(symbol, current)

            # Publish detected events
            for event in all_events:
                await self._publish_event(event)

        except Exception as e:
            logger.error(f"Error processing aggregate: {e}")

    async def _build_ticker_state(self, symbol: str, data: Dict) -> Optional[TickerState]:
        """Build TickerState from aggregate data + enriched cache."""
        try:
            # Real-time data from aggregate
            price = float(data.get("c", 0) or data.get("close", 0))
            if price <= 0:
                return None

            volume = int(data.get("av", 0) or data.get("volume", 0) or 0)
            minute_volume = int(data.get("v", 0) or data.get("vol", 0) or 0) or None

            # Enriched data from local cache
            enriched = self._enriched_cache.get(symbol, {})

            # RVOL from dedicated Redis hash (more real-time than enriched cache)
            rvol = await self._get_rvol(symbol)

            # VWAP: prefer enriched cache (daily VWAP from analytics)
            vwap = enriched.get("vwap")
            if vwap is None:
                raw_vw = data.get("vw") or data.get("vwap")
                vwap = float(raw_vw) if raw_vw else None

            # Reference prices
            open_price = enriched.get("open_price")
            prev_close = enriched.get("prev_close")

            # Computed changes - calculate in REAL-TIME from current price
            # (enriched change_percent can be up to 30s stale)
            change_percent = None
            if prev_close and prev_close > 0:
                change_percent = ((price - prev_close) / prev_close) * 100
            else:
                change_percent = enriched.get("change_percent")  # fallback

            gap_percent = None
            if open_price and prev_close and prev_close > 0:
                gap_percent = ((open_price - prev_close) / prev_close) * 100

            change_from_open = None
            if open_price and open_price > 0:
                change_from_open = ((price - open_price) / open_price) * 100

            # Daily indicators from screener (SMA, Bollinger, RSI, 52w)
            screener = self._screener_cache.get(symbol, {})

            return TickerState(
                symbol=symbol,
                price=price,
                volume=volume,
                minute_volume=minute_volume,
                timestamp=datetime.utcnow(),
                vwap=vwap,
                intraday_high=enriched.get("intraday_high"),
                intraday_low=enriched.get("intraday_low"),
                prev_close=prev_close,
                open_price=open_price,
                day_high=enriched.get("day_high"),
                day_low=enriched.get("day_low"),
                change_percent=change_percent,
                gap_percent=gap_percent,
                change_from_open=change_from_open,
                chg_1min=enriched.get("chg_1min"),
                chg_5min=enriched.get("chg_5min"),
                chg_10min=enriched.get("chg_10min"),
                chg_15min=enriched.get("chg_15min"),
                chg_30min=enriched.get("chg_30min"),
                vol_1min=enriched.get("vol_1min"),
                vol_5min=enriched.get("vol_5min"),
                rvol=rvol if rvol else enriched.get("rvol"),
                atr=enriched.get("atr"),
                atr_percent=enriched.get("atr_percent"),
                trades_z_score=enriched.get("trades_z_score"),
                # Daily indicators from screener
                sma_20=screener.get("sma_20"),
                sma_50=screener.get("sma_50"),
                sma_200=screener.get("sma_200"),
                bb_upper=screener.get("bb_upper"),
                bb_lower=screener.get("bb_lower"),
                rsi=screener.get("rsi"),
                high_52w=screener.get("high_52w"),
                low_52w=screener.get("low_52w"),
                prev_day_high=enriched.get("day_high"),  # yesterday's high
                prev_day_low=enriched.get("day_low"),    # yesterday's low
                # Fundamentals (prefer screener, fallback enriched)
                market_cap=screener.get("market_cap") or enriched.get("market_cap"),
                float_shares=screener.get("float_shares"),
            )
        except Exception as e:
            logger.error(f"Error building TickerState for {symbol}: {e}")
            return None

    # ========================================================================
    # HALT PROCESSING
    # ========================================================================

    async def _process_halt_event(self, data: Dict):
        """Process a halt/resume event from the halt stream."""
        try:
            event_type_raw = data.get("event_type", "").upper()
            symbol = data.get("symbol", "")

            if not symbol or not event_type_raw:
                return

            # Parse nested data
            halt_data = {}
            if data.get("data"):
                try:
                    halt_data = json.loads(data["data"]) if isinstance(data["data"], str) else data["data"]
                except Exception:
                    halt_data = {}

            # Map to EventType
            if event_type_raw == "HALT":
                event_type = EventType.HALT
            elif event_type_raw == "RESUME":
                event_type = EventType.RESUME
            else:
                return

            # Get enriched data
            enriched = self._enriched_cache.get(symbol, {})
            rvol = await self._get_rvol(symbol)
            change_percent = enriched.get("change_percent")

            event = EventRecord(
                event_type=event_type,
                rule_id=f"event:system:{event_type.value}",
                symbol=symbol,
                timestamp=datetime.utcnow(),
                price=halt_data.get("pause_threshold_price") or 0,
                change_percent=change_percent,
                rvol=rvol,
                details={
                    "halt_reason": halt_data.get("halt_reason"),
                    "halt_reason_desc": halt_data.get("halt_reason_desc"),
                    "company_name": halt_data.get("company_name"),
                    "exchange": halt_data.get("exchange"),
                }
            )

            await self._publish_event(event)

        except Exception as e:
            logger.error(f"Error processing halt event: {e}")

    # ========================================================================
    # EVENT PUBLISHING
    # ========================================================================

    async def _publish_event(self, event: EventRecord):
        """Publish event to Redis stream."""
        self.event_store.add(event)

        try:
            await self.raw_redis.xadd(
                STREAM_EVENTS,
                event.to_dict(),
                maxlen=10000
            )
            logger.info(f"Event: {event.event_type.value} | {event.symbol} @ ${event.price:.2f}")
        except Exception as e:
            logger.error(f"Error publishing event: {e}")

    # ========================================================================
    # DATA FETCHING
    # ========================================================================

    async def _get_rvol(self, symbol: str) -> Optional[float]:
        """Get RVOL from Analytics hash."""
        try:
            rvol_str = await self.raw_redis.hget("rvol:current_slot", symbol)
            if rvol_str:
                return float(rvol_str)
            return None
        except Exception:
            return None

    async def _refresh_enriched_cache(self):
        """Refresh enriched data cache from Redis Hash (snapshot:enriched:latest)."""
        try:
            # Read all tickers from Redis Hash (replaces reading full JSON blob)
            all_data = await self.raw_redis.hgetall("snapshot:enriched:latest")
            if not all_data:
                return

            # Remove metadata field
            all_data.pop(b"__meta__", None)
            all_data.pop("__meta__", None)

            # Parse each ticker from hash fields
            tickers = []
            for sym_key, ticker_json in all_data.items():
                try:
                    if isinstance(ticker_json, bytes):
                        ticker_json = ticker_json.decode('utf-8')
                    t = json.loads(ticker_json)
                    tickers.append(t)
                except Exception:
                    continue

            new_cache = {}
            for t in tickers:
                sym = t.get("ticker") or t.get("symbol", "")
                if not sym:
                    continue

                # Extract nested fields safely
                day = t.get("day") or {}
                prev_day = t.get("prevDay") or {}

                prev_close_val = prev_day.get("c") if isinstance(prev_day, dict) else None

                new_cache[sym] = {
                    # Changes
                    "change_percent": t.get("todaysChangePerc"),

                    # Reference prices
                    "open_price": day.get("o") if isinstance(day, dict) else None,
                    "prev_close": prev_close_val,
                    "day_high": day.get("h") if isinstance(day, dict) else None,
                    "day_low": day.get("l") if isinstance(day, dict) else None,

                    # Intraday extremes (from analytics intraday tracker)
                    "intraday_high": t.get("intraday_high"),
                    "intraday_low": t.get("intraday_low"),

                    # VWAP
                    "vwap": t.get("vwap"),

                    # RVOL (fallback if redis hash unavailable)
                    "rvol": t.get("rvol"),

                    # Current price (for initialization)
                    "current_price": t.get("current_price"),

                    # Window metrics
                    "chg_1min": t.get("chg_1min"),
                    "chg_5min": t.get("chg_5min"),
                    "chg_10min": t.get("chg_10min"),
                    "chg_15min": t.get("chg_15min"),
                    "chg_30min": t.get("chg_30min"),
                    "vol_1min": int(t["vol_1min"]) if t.get("vol_1min") else None,
                    "vol_5min": int(t["vol_5min"]) if t.get("vol_5min") else None,

                    # Technical
                    "atr": t.get("atr"),
                    "atr_percent": t.get("atr_percent"),
                    "trades_z_score": t.get("trades_z_score"),

                    # Fundamentals
                    "market_cap": t.get("market_cap"),
                }

            self._enriched_cache = new_cache
            logger.debug(f"Enriched cache refreshed: {len(new_cache)} tickers")

        except Exception as e:
            logger.error(f"Error refreshing enriched cache: {e}")

    async def _initialize_tracked_extremes(self):
        """Initialize price detector's tracked extremes from enriched cache."""
        if not self.price_detector:
            return

        initialized = 0
        for symbol, data in self._enriched_cache.items():
            high = data.get("intraday_high")
            low = data.get("intraday_low")
            price = data.get("current_price")

            if high is not None and low is not None:
                self.price_detector.initialize_extremes(symbol, float(high), float(low))
                initialized += 1
            elif price is not None:
                self.price_detector.initialize_extremes(symbol, float(price), float(price))
                initialized += 1

        logger.info(f"Initialized tracked extremes for {initialized} symbols")

    # ========================================================================
    # MAINTENANCE LOOPS
    # ========================================================================

    async def _enriched_refresh_loop(self):
        """Refresh enriched cache every 30 seconds for accurate detection."""
        while self.running:
            await asyncio.sleep(30)
            await self._refresh_enriched_cache()

    async def _screener_refresh_loop(self):
        """Refresh screener daily indicators every 60 seconds."""
        while self.running:
            await asyncio.sleep(60)
            await self._refresh_screener_cache()

    async def _refresh_screener_cache(self):
        """
        Load daily indicators from screener service via Redis.
        
        The screener exports SMA(20/50/200), Bollinger Bands, RSI, 52w highs/lows
        to Redis key 'screener:daily_indicators:latest' every 5 minutes.
        We consume this to enable SMA cross and Bollinger breakout detection.
        """
        try:
            data_json = await self.raw_redis.get("screener:daily_indicators:latest")
            if not data_json:
                logger.debug("No screener daily indicators in Redis (screener may not be running)")
                return

            data = json.loads(data_json)
            tickers = data.get("tickers", {})

            new_cache = {}
            for symbol, ind in tickers.items():
                new_cache[symbol] = {
                    "sma_20": self._safe_float(ind.get("sma_20")),
                    "sma_50": self._safe_float(ind.get("sma_50")),
                    "sma_200": self._safe_float(ind.get("sma_200")),
                    "bb_upper": self._safe_float(ind.get("bb_upper")),
                    "bb_lower": self._safe_float(ind.get("bb_lower")),
                    "rsi": self._safe_float(ind.get("rsi")),
                    "high_52w": self._safe_float(ind.get("high_52w")),
                    "low_52w": self._safe_float(ind.get("low_52w")),
                    "prev_day_high": self._safe_float(ind.get("last_close")),  # approximation
                    "market_cap": self._safe_float(ind.get("market_cap")),
                    "float_shares": self._safe_float(ind.get("free_float")),
                }

            self._screener_cache = new_cache
            logger.debug(f"Screener cache refreshed: {len(new_cache)} tickers")
        except Exception as e:
            logger.error(f"Error refreshing screener cache: {e}")

    @staticmethod
    def _safe_float(val) -> Optional[float]:
        """Safely convert a value to float, returning None for invalid values."""
        if val is None:
            return None
        try:
            f = float(val)
            # DuckDB can return NaN/Inf for edge cases
            import math
            return f if math.isfinite(f) else None
        except (ValueError, TypeError):
            return None

    async def _cleanup_loop(self):
        """Periodic cleanup of old in-memory data. Daily reset is handled by EventBus."""
        while self.running:
            await asyncio.sleep(300)  # Every 5 minutes

            # Regular cleanup (NOT daily reset - that's EventBus driven)
            events_removed = self.event_store.cleanup_old()
            states_removed = self.state_cache.cleanup_old()

            # Cleanup detector tracking data for inactive symbols
            active_symbols = set(self.state_cache._states.keys())
            for detector in self.detectors:
                detector.cleanup_old_symbols(active_symbols)

            if events_removed or states_removed:
                logger.info(f"Cleanup: {events_removed} events, {states_removed} states removed")


# ============================================================================
# ENTRY POINT
# ============================================================================

async def main():
    global redis_client, event_bus, engine

    logger.info("Starting Event Detector Service...")

    # Initialize Redis (shared wrapper - same as scanner/analytics)
    redis_client = RedisClient()
    await redis_client.connect()
    logger.info("✅ Redis connected")

    # Check market status
    await check_initial_market_status()

    # Initialize EventBus (subscribe to DAY_CHANGED, SESSION_CHANGED)
    event_bus = EventBus(redis_client, "event_detector")
    event_bus.subscribe(BusEventType.DAY_CHANGED, handle_day_changed)
    event_bus.subscribe(BusEventType.SESSION_CHANGED, handle_session_changed)
    await event_bus.start_listening()
    logger.info("✅ EventBus initialized - subscribed to DAY_CHANGED, SESSION_CHANGED")

    # Initialize and start engine
    engine = EventEngine(redis_client)

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(engine.stop()))

    await engine.start()


if __name__ == "__main__":
    asyncio.run(main())
