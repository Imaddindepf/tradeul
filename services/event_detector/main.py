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
import time
from datetime import datetime, date
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

import httpx
import redis.asyncio as aioredis

from shared.config.settings import settings
from shared.utils.redis_client import RedisClient
from shared.events import EventBus, EventType as BusEventType, Event

from models import EventRecord, EventType, TickerState, TickerStateCache
from detectors import ALL_DETECTOR_CLASSES, PriceEventsDetector
from store import EventStore
from persistence import EventWriter

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
event_writer: Optional[EventWriter] = None

is_holiday_mode: bool = False
current_trading_date: Optional[date] = None
current_market_session: str = "UNKNOWN"

STREAM_EVENTS = "stream:events:market"


# ============================================================================
# MARKET STATUS (same as scanner/analytics)
# ============================================================================

async def check_initial_market_status() -> None:
    """
    Lee el estado del mercado UNA VEZ al iniciar.
    Determina si es día festivo para evitar resetear cachés.
    También inicializa current_market_session.
    """
    global is_holiday_mode, current_trading_date, current_market_session

    try:
        status_data = await redis_client.get(f"{settings.key_prefix_market}:session:status")

        if status_data:
            is_holiday = status_data.get('is_holiday', False)
            is_trading_day = status_data.get('is_trading_day', True)
            trading_date_str = status_data.get('trading_date')

            is_holiday_mode = is_holiday or not is_trading_day

            if trading_date_str:
                current_trading_date = date.fromisoformat(trading_date_str)

            # Read current session
            session_val = status_data.get('current_session', 'UNKNOWN')
            current_market_session = session_val
            logger.info(
                f"📅 Market status: holiday={is_holiday}, trading_day={is_trading_day}, "
                f"holiday_mode={is_holiday_mode}, date={trading_date_str}, "
                f"session={current_market_session}"
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
    """Handler para SESSION_CHANGED - actualiza sesión actual."""
    global current_market_session
    from_session = event.data.get('from_session', '?')
    to_session = event.data.get('to_session', '?')
    current_market_session = to_session
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

    def __init__(self, redis: RedisClient, writer: Optional[EventWriter] = None):
        self.redis = redis
        self.writer = writer
        # Raw async redis client for stream operations (xread, xadd, etc.)
        self.raw_redis: Optional[aioredis.Redis] = None
        self.running = False

        # State cache for tracking previous values (per-second stream)
        self.state_cache = TickerStateCache(max_age_seconds=3600)

        # Event store for recent events (in-memory)
        self.event_store = EventStore(max_age_seconds=3600)

        # Enriched data cache (from Analytics service)
        self._enriched_cache: Dict[str, Dict] = {}

        # === SNAPSHOT-DRIVEN FULL-MARKET DETECTION ===
        # Previous snapshot state for transition detection (all 11K+ tickers)
        self._snapshot_prev: Dict[str, Dict] = {}
        # Cooldown tracker: (symbol, event_type) -> last_fire_timestamp
        self._snapshot_cooldowns: Dict[str, float] = {}
        # Symbols being processed by per-second stream (avoid duplicate detection)
        self._realtime_symbols: set = set()
        # Stats
        self._snapshot_events_total: int = 0
        self._snapshot_cycles: int = 0

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

        if self.price_detector:
            await self._initialize_tracked_extremes()

        # Start consumer tasks
        tasks = [
            asyncio.create_task(self._consume_aggregates_loop()),
            asyncio.create_task(self._consume_halts_loop()),
            asyncio.create_task(self._enriched_refresh_loop()),
            asyncio.create_task(self._snapshot_evaluation_loop()),
            asyncio.create_task(self._cleanup_loop()),
        ]

        # Add persistence writer if available
        if self.writer:
            tasks.append(asyncio.create_task(self.writer.run()))
            logger.info("✅ EventWriter persistence loop started")

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

        # 2b. Clear snapshot-driven state
        self._snapshot_prev.clear()
        self._snapshot_cooldowns.clear()
        self._realtime_symbols.clear()
        self._snapshot_events_total = 0
        self._snapshot_cycles = 0
        logger.info("✅ Snapshot evaluation state cleared")

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
                # Technical indicators (all from enriched — BarEngine intraday)
                ema_20=enriched.get("ema_20"),
                ema_50=enriched.get("ema_50"),
                # SMA intraday (from BarEngine 1-min bars via enriched)
                sma_5=enriched.get("sma_5"),
                sma_8=enriched.get("sma_8"),
                sma_20=enriched.get("sma_20"),
                sma_50=enriched.get("sma_50"),
                sma_200=enriched.get("sma_200"),
                bb_upper=enriched.get("bb_upper"),
                bb_lower=enriched.get("bb_lower"),
                rsi=enriched.get("rsi_14"),
                # MACD / Stochastic / ADX (from BarEngine via enriched)
                macd_line=enriched.get("macd_line"),
                macd_signal=enriched.get("macd_signal"),
                macd_hist=enriched.get("macd_hist"),
                stoch_k=enriched.get("stoch_k"),
                stoch_d=enriched.get("stoch_d"),
                adx_14=enriched.get("adx_14"),
                # Daily indicators (from screener via enriched)
                high_52w=enriched.get("high_52w"),
                low_52w=enriched.get("low_52w"),
                prev_day_high=enriched.get("day_high"),
                prev_day_low=enriched.get("day_low"),
                daily_sma_200=enriched.get("daily_sma_200"),
                # Fundamentals (from metadata via enriched)
                market_cap=enriched.get("market_cap"),
                float_shares=enriched.get("float_shares"),
                security_type=enriched.get("security_type"),
                # Session context (for pre/post market detectors)
                market_session=current_market_session,
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

            # ── Layer 1: Local enriched cache (fast, in-memory) ──
            enriched = self._enriched_cache.get(symbol, {})
            rvol = await self._get_rvol(symbol)

            # ── Layer 2: Full enriched blob from Redis hash ──
            full_enriched = {}
            try:
                raw = await self.raw_redis.hget("snapshot:enriched:latest", symbol)
                if raw:
                    full_enriched = json.loads(raw if isinstance(raw, str) else raw.decode("utf-8"))
            except Exception:
                pass

            price = (
                full_enriched.get("current_price")
                or enriched.get("current_price")
                or halt_data.get("pause_threshold_price")
            )

            # ── Layer 3: Polygon API fallback (via api_gateway, cached 5 min) ──
            # Only when we have no price — halts can be on tickers not in enriched cache
            polygon_snapshot = {}
            if not price:
                polygon_snapshot = await self._fetch_polygon_snapshot(symbol)

            # Resolve final values: enriched → full_enriched → polygon
            if not price:
                price = polygon_snapshot.get("price", 0)

            open_price = enriched.get("open_price") or polygon_snapshot.get("open_price")
            prev_close = enriched.get("prev_close") or polygon_snapshot.get("prev_close")
            volume = full_enriched.get("current_volume") or polygon_snapshot.get("volume")
            change_percent = enriched.get("change_percent") or polygon_snapshot.get("change_percent")
            market_cap = full_enriched.get("market_cap") or enriched.get("market_cap")
            float_shares = full_enriched.get("float_shares")
            security_type = full_enriched.get("security_type")
            sector = full_enriched.get("sector")

            # Compute derived fields
            change_from_open = None
            gap_percent = None
            if price and open_price and open_price > 0:
                change_from_open = ((price - open_price) / open_price) * 100
            if open_price and prev_close and prev_close > 0:
                gap_percent = ((open_price - prev_close) / prev_close) * 100

            event = EventRecord(
                event_type=event_type,
                rule_id=f"event:system:{event_type.value}",
                symbol=symbol,
                timestamp=datetime.utcnow(),
                price=price,
                change_percent=change_percent,
                rvol=rvol,
                volume=int(volume) if volume else None,
                market_cap=market_cap,
                gap_percent=gap_percent,
                change_from_open=change_from_open,
                open_price=open_price,
                prev_close=prev_close,
                vwap=enriched.get("vwap") or polygon_snapshot.get("vwap"),
                atr_percent=enriched.get("atr_percent"),
                intraday_high=enriched.get("intraday_high") or polygon_snapshot.get("intraday_high"),
                intraday_low=enriched.get("intraday_low") or polygon_snapshot.get("intraday_low"),
                chg_1min=enriched.get("chg_1min"),
                chg_5min=enriched.get("chg_5min"),
                chg_10min=enriched.get("chg_10min"),
                chg_15min=enriched.get("chg_15min"),
                chg_30min=enriched.get("chg_30min"),
                vol_1min=enriched.get("vol_1min"),
                vol_5min=enriched.get("vol_5min"),
                float_shares=float_shares,
                security_type=security_type,
                sector=sector,
                details={
                    "halt_reason": halt_data.get("halt_reason"),
                    "halt_reason_desc": halt_data.get("halt_reason_desc"),
                    "company_name": halt_data.get("company_name"),
                    "exchange": halt_data.get("exchange"),
                    "data_source": "polygon_fallback" if polygon_snapshot else "enriched",
                }
            )

            await self._publish_event(event)

        except Exception as e:
            logger.error(f"Error processing halt event: {e}")

    async def _fetch_polygon_snapshot(self, symbol: str) -> Dict:
        """
        Fallback: fetch single-ticker snapshot from Polygon via api_gateway.
        The api_gateway caches responses for 5 minutes, so repeated calls are cheap.
        Only called when enriched cache has no data for this symbol.
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"http://api_gateway:8000/api/v1/ticker/{symbol}/snapshot"
                )
                if resp.status_code != 200:
                    logger.warning(f"Polygon snapshot fallback failed for {symbol}: HTTP {resp.status_code}")
                    return {}

                data = resp.json()
                ticker = data.get("ticker", {})
                if not ticker:
                    return {}

                day = ticker.get("day") or {}
                prev_day = ticker.get("prevDay") or {}
                last_trade = ticker.get("lastTrade") or {}
                minute_bar = ticker.get("min") or {}

                result = {
                    "price": last_trade.get("p") or day.get("c") or minute_bar.get("c") or 0,
                    "open_price": day.get("o"),
                    "prev_close": prev_day.get("c"),
                    "volume": int(day.get("v", 0)) if day.get("v") else None,
                    "vwap": day.get("vw"),
                    "intraday_high": day.get("h"),
                    "intraday_low": day.get("l"),
                    "change_percent": ticker.get("todaysChangePerc"),
                }
                logger.info(f"📡 Polygon fallback for {symbol}: price=${result['price']:.2f}, vol={result.get('volume')}")
                return result

        except httpx.TimeoutException:
            logger.warning(f"Polygon snapshot timeout for {symbol}")
            return {}
        except Exception as e:
            logger.warning(f"Polygon snapshot fallback error for {symbol}: {e}")
            return {}

    # ========================================================================
    # EVENT PUBLISHING
    # ========================================================================

    async def _publish_event(self, event: EventRecord, enriched_override: Optional[Dict] = None):
        """
        Publish event to Redis stream and buffer for TimescaleDB persistence.

        Args:
            event: The event to publish
            enriched_override: Optional full enriched snapshot to store in context JSONB.
                              If None, falls back to self._enriched_cache (basic subset).
                              Used by snapshot-driven events which have the full data.
        """
        self.event_store.add(event)

        event_dict = event.to_dict()

        try:
            await self.raw_redis.xadd(
                STREAM_EVENTS,
                event_dict,
                maxlen=10000
            )
            logger.info(f"Event: {event.event_type.value} | {event.symbol} @ ${event.price:.2f}")
        except Exception as e:
            logger.error(f"Error publishing event: {e}")

        # Buffer for TimescaleDB persistence (fire-and-forget)
        if self.writer:
            try:
                enriched = enriched_override or self._enriched_cache.get(event.symbol)
                self.writer.buffer_event(event_dict, enriched)
            except Exception as e:
                logger.error(f"Error buffering event for persistence: {e}")

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
    # SNAPSHOT-DRIVEN FULL-MARKET EVALUATION
    # ========================================================================

    async def _snapshot_evaluation_loop(self):
        """
        Evaluate enriched snapshot every ~2s for state transitions across
        the FULL universe (11K+ tickers).

        This complements the per-second aggregate stream (which only covers
        ~300 WS-subscribed tickers) by detecting events for ALL tickers
        using the enriched snapshot data (which includes BarEngine indicators).

        Detected events:
        - new_high / new_low (intraday extremes changed)
        - vwap_cross_up / vwap_cross_down
        - bb_upper_breakout / bb_lower_breakdown
        - crossed_above_sma200/50/20
        - percent_up_5/10, percent_down_5/10 (threshold crosses)
        - volume_spike_1min (vol_1min >> avg)

        Deduplication:
        - Skips symbols covered by the per-second stream (self._realtime_symbols)
        - Uses cooldown per (symbol, event_type) to avoid flooding
        """
        COOLDOWN_SECONDS = 60.0  # Min seconds between same event for same symbol
        LOOP_INTERVAL = 2.0

        # Wait for initial enriched data to be available
        await asyncio.sleep(5)
        logger.info("📡 Snapshot evaluation loop started (full-market coverage)")

        while self.running:
            try:
                if is_holiday_mode:
                    await asyncio.sleep(30)
                    continue

                # Read full enriched snapshot
                all_data = await self.raw_redis.hgetall("snapshot:enriched:latest")
                if not all_data:
                    await asyncio.sleep(LOOP_INTERVAL)
                    continue

                now = time.monotonic()
                cycle_events = 0
                tickers_evaluated = 0

                for sym_bytes, ticker_json in all_data.items():
                    sym = sym_bytes.decode() if isinstance(sym_bytes, bytes) else sym_bytes
                    if sym == '__meta__':
                        continue

                    # Skip symbols covered by per-second realtime stream
                    if sym in self._realtime_symbols:
                        continue

                    try:
                        current = json.loads(
                            ticker_json if isinstance(ticker_json, str)
                            else ticker_json.decode()
                        )
                    except Exception:
                        continue

                    prev = self._snapshot_prev.get(sym)
                    if prev is None:
                        # First time seeing this ticker - store and skip
                        self._snapshot_prev[sym] = current
                        continue

                    tickers_evaluated += 1

                    # Detect state transitions
                    events = self._detect_snapshot_transitions(sym, current, prev, now, COOLDOWN_SECONDS)
                    for event in events:
                        # Pass full enriched snapshot for richer context in TimescaleDB
                        await self._publish_event(event, enriched_override=current)
                        cycle_events += 1

                    # Update previous state
                    self._snapshot_prev[sym] = current

                self._snapshot_cycles += 1
                self._snapshot_events_total += cycle_events

                if cycle_events > 0 or self._snapshot_cycles % 30 == 0:
                    logger.info(
                        f"📡 Snapshot eval cycle #{self._snapshot_cycles}: "
                        f"{cycle_events} events from {tickers_evaluated} tickers "
                        f"(skipped {len(self._realtime_symbols)} realtime)"
                    )

            except Exception as e:
                logger.error(f"Snapshot evaluation error: {e}")

            await asyncio.sleep(LOOP_INTERVAL)

    def _detect_snapshot_transitions(
        self,
        symbol: str,
        current: Dict,
        prev: Dict,
        now: float,
        cooldown: float,
    ) -> List[EventRecord]:
        """
        Compare current vs previous enriched snapshot for a single ticker.
        Returns list of EventRecord for any detected transitions.
        """
        events: List[EventRecord] = []
        price = current.get("current_price")
        if not price or price <= 0:
            return events

        prev_price = prev.get("current_price")
        if not prev_price or prev_price <= 0:
            return events

        # Compute gap_percent and change_from_open if not present
        open_price = (current.get("day") or {}).get("o")
        prev_close = (current.get("prevDay") or {}).get("c")
        gap_percent = current.get("gap_percent")
        if gap_percent is None and open_price and prev_close and prev_close > 0:
            gap_percent = ((open_price - prev_close) / prev_close) * 100
        change_from_open = current.get("change_from_open")
        if change_from_open is None and open_price and open_price > 0:
            change_from_open = ((price - open_price) / open_price) * 100

        def _fire(event_type: EventType, prev_val=None, new_val=None, details=None):
            """Helper to create an event with cooldown check."""
            key = f"{symbol}:{event_type.value}"
            last_fire = self._snapshot_cooldowns.get(key, 0)
            if now - last_fire < cooldown:
                return  # Still in cooldown
            self._snapshot_cooldowns[key] = now

            delta = None
            delta_pct = None
            if prev_val is not None and new_val is not None:
                delta = new_val - prev_val
                if prev_val != 0:
                    delta_pct = (delta / abs(prev_val)) * 100

            events.append(EventRecord(
                event_type=event_type,
                rule_id=f"event:system:{event_type.value}",
                symbol=symbol,
                timestamp=datetime.utcnow(),
                price=price,
                prev_value=prev_val,
                new_value=new_val,
                delta=delta,
                delta_percent=delta_pct,
                # Full context from enriched snapshot
                change_percent=current.get("todaysChangePerc"),
                rvol=current.get("rvol"),
                volume=current.get("current_volume"),
                # Fundamentals (from metadata via enriched)
                market_cap=current.get("market_cap"),
                gap_percent=gap_percent,
                change_from_open=change_from_open,
                open_price=open_price,
                prev_close=prev_close,
                vwap=current.get("vwap"),
                atr_percent=current.get("atr_percent"),
                intraday_high=current.get("intraday_high"),
                intraday_low=current.get("intraday_low"),
                # Time-window changes
                chg_1min=current.get("chg_1min"),
                chg_5min=current.get("chg_5min"),
                chg_10min=current.get("chg_10min"),
                chg_15min=current.get("chg_15min"),
                chg_30min=current.get("chg_30min"),
                vol_1min=current.get("vol_1min"),
                vol_5min=current.get("vol_5min"),
                # Technical indicators + fundamentals (all from enriched)
                float_shares=current.get("float_shares"),
                rsi=current.get("rsi_14"),
                ema_20=current.get("ema_20"),
                ema_50=current.get("ema_50"),
                security_type=current.get("security_type"),
                sector=current.get("sector"),
                details=details,
            ))

        # --- NEW HIGH ---
        curr_high = current.get("intraday_high")
        prev_high = prev.get("intraday_high")
        if curr_high and prev_high and curr_high > prev_high:
            _fire(EventType.NEW_HIGH, prev_high, curr_high)

        # --- NEW LOW ---
        curr_low = current.get("intraday_low")
        prev_low = prev.get("intraday_low")
        if curr_low and prev_low and curr_low < prev_low:
            _fire(EventType.NEW_LOW, prev_low, curr_low)

        # --- VWAP CROSS ---
        vwap = current.get("vwap")
        prev_vwap = prev.get("vwap")
        if vwap and prev_vwap and vwap > 0:
            if prev_price <= prev_vwap and price > vwap:
                _fire(EventType.VWAP_CROSS_UP, prev_vwap, vwap,
                      {"vwap": vwap, "direction": "up"})
            elif prev_price >= prev_vwap and price < vwap:
                _fire(EventType.VWAP_CROSS_DOWN, prev_vwap, vwap,
                      {"vwap": vwap, "direction": "down"})

        # --- BOLLINGER BAND BREAKOUT ---
        bb_upper = current.get("bb_upper")
        bb_lower = current.get("bb_lower")
        prev_bb_upper = prev.get("bb_upper")
        prev_bb_lower = prev.get("bb_lower")
        if bb_upper and prev_bb_upper and prev_price <= prev_bb_upper and price > bb_upper:
            _fire(EventType.BB_UPPER_BREAKOUT, prev_bb_upper, bb_upper,
                  {"bb_upper": bb_upper, "direction": "up"})
        if bb_lower and prev_bb_lower and prev_price >= prev_bb_lower and price < bb_lower:
            _fire(EventType.BB_LOWER_BREAKDOWN, prev_bb_lower, bb_lower,
                  {"bb_lower": bb_lower, "direction": "down"})

        # =====================================================================
        # DAILY SMA CROSSES — Price vs Daily MAs (Trade Ideas CA20/CA50)
        # These are the REAL MA cross alerts — rare, meaningful signals.
        # =====================================================================
        daily_sma_20 = current.get("daily_sma_20")
        prev_daily_sma_20 = prev.get("daily_sma_20")
        if daily_sma_20 and daily_sma_20 > 0 and prev_daily_sma_20 and prev_daily_sma_20 > 0:
            if prev_price <= prev_daily_sma_20 and price > daily_sma_20:
                _fire(EventType.CROSSED_ABOVE_SMA20_DAILY, prev_daily_sma_20, daily_sma_20,
                      {"ma_type": "daily_sma_20", "ma_value": daily_sma_20})
            elif prev_price >= prev_daily_sma_20 and price < daily_sma_20:
                _fire(EventType.CROSSED_BELOW_SMA20_DAILY, prev_daily_sma_20, daily_sma_20,
                      {"ma_type": "daily_sma_20", "ma_value": daily_sma_20})

        daily_sma_50 = current.get("daily_sma_50")
        prev_daily_sma_50 = prev.get("daily_sma_50")
        if daily_sma_50 and daily_sma_50 > 0 and prev_daily_sma_50 and prev_daily_sma_50 > 0:
            if prev_price <= prev_daily_sma_50 and price > daily_sma_50:
                _fire(EventType.CROSSED_ABOVE_SMA50_DAILY, prev_daily_sma_50, daily_sma_50,
                      {"ma_type": "daily_sma_50", "ma_value": daily_sma_50})
            elif prev_price >= prev_daily_sma_50 and price < daily_sma_50:
                _fire(EventType.CROSSED_BELOW_SMA50_DAILY, prev_daily_sma_50, daily_sma_50,
                      {"ma_type": "daily_sma_50", "ma_value": daily_sma_50})

        # =====================================================================
        # 5-MIN MA-TO-MA CROSS — SMA(8) vs SMA(20) on 5m bars (Trade Ideas ECAY5)
        # =====================================================================
        sma_8_5m = current.get("sma_8_5m")
        sma_20_5m = current.get("sma_20_5m")
        prev_sma_8_5m = prev.get("sma_8_5m")
        prev_sma_20_5m = prev.get("sma_20_5m")
        if sma_8_5m and sma_20_5m and prev_sma_8_5m and prev_sma_20_5m:
            if prev_sma_8_5m <= prev_sma_20_5m and sma_8_5m > sma_20_5m:
                _fire(EventType.SMA8_ABOVE_SMA20_5M, prev_sma_8_5m, sma_8_5m,
                      {"sma_8_5m": sma_8_5m, "sma_20_5m": sma_20_5m, "cross_type": "golden", "timeframe": "5m"})
            elif prev_sma_8_5m >= prev_sma_20_5m and sma_8_5m < sma_20_5m:
                _fire(EventType.SMA8_BELOW_SMA20_5M, prev_sma_8_5m, sma_8_5m,
                      {"sma_8_5m": sma_8_5m, "sma_20_5m": sma_20_5m, "cross_type": "death", "timeframe": "5m"})

        # =====================================================================
        # 5-MIN MACD CROSSES (Trade Ideas MDAS5/MDBS5/MDAZ5/MDBZ5)
        # =====================================================================
        macd_l_5m = current.get("macd_line_5m")
        macd_s_5m = current.get("macd_signal_5m")
        prev_macd_l_5m = prev.get("macd_line_5m")
        prev_macd_s_5m = prev.get("macd_signal_5m")
        if macd_l_5m is not None and macd_s_5m is not None and prev_macd_l_5m is not None and prev_macd_s_5m is not None:
            # Signal cross
            if prev_macd_l_5m <= prev_macd_s_5m and macd_l_5m > macd_s_5m:
                _fire(EventType.MACD_ABOVE_SIGNAL_5M, prev_macd_l_5m, macd_l_5m,
                      {"macd_line_5m": macd_l_5m, "macd_signal_5m": macd_s_5m, "timeframe": "5m"})
            elif prev_macd_l_5m >= prev_macd_s_5m and macd_l_5m < macd_s_5m:
                _fire(EventType.MACD_BELOW_SIGNAL_5M, prev_macd_l_5m, macd_l_5m,
                      {"macd_line_5m": macd_l_5m, "macd_signal_5m": macd_s_5m, "timeframe": "5m"})
            # Zero cross
            if prev_macd_l_5m <= 0 and macd_l_5m > 0:
                _fire(EventType.MACD_ABOVE_ZERO_5M, prev_macd_l_5m, macd_l_5m,
                      {"timeframe": "5m"})
            elif prev_macd_l_5m >= 0 and macd_l_5m < 0:
                _fire(EventType.MACD_BELOW_ZERO_5M, prev_macd_l_5m, macd_l_5m,
                      {"timeframe": "5m"})

        # =====================================================================
        # 5-MIN STOCHASTIC CROSSES (Trade Ideas SC20_5/SC80_5)
        # =====================================================================
        stoch_k_5m = current.get("stoch_k_5m")
        stoch_d_5m = current.get("stoch_d_5m")
        prev_stoch_k_5m = prev.get("stoch_k_5m")
        prev_stoch_d_5m = prev.get("stoch_d_5m")
        if stoch_k_5m is not None and stoch_d_5m is not None and prev_stoch_k_5m is not None and prev_stoch_d_5m is not None:
            # Bullish: %K crosses above %D while in oversold (<30) on 5m
            if prev_stoch_k_5m <= prev_stoch_d_5m and stoch_k_5m > stoch_d_5m and stoch_k_5m < 30:
                _fire(EventType.STOCH_CROSS_BULLISH_5M, prev_stoch_k_5m, stoch_k_5m,
                      {"stoch_k_5m": stoch_k_5m, "stoch_d_5m": stoch_d_5m, "zone": "oversold", "timeframe": "5m"})
            # Bearish: %K crosses below %D while in overbought (>70) on 5m
            elif prev_stoch_k_5m >= prev_stoch_d_5m and stoch_k_5m < stoch_d_5m and stoch_k_5m > 70:
                _fire(EventType.STOCH_CROSS_BEARISH_5M, prev_stoch_k_5m, stoch_k_5m,
                      {"stoch_k_5m": stoch_k_5m, "stoch_d_5m": stoch_d_5m, "zone": "overbought", "timeframe": "5m"})
            # Zone entries on 5m
            if prev_stoch_k_5m >= 20 and stoch_k_5m < 20:
                _fire(EventType.STOCH_OVERSOLD_5M, prev_stoch_k_5m, stoch_k_5m,
                      {"timeframe": "5m"})
            elif prev_stoch_k_5m <= 80 and stoch_k_5m > 80:
                _fire(EventType.STOCH_OVERBOUGHT_5M, prev_stoch_k_5m, stoch_k_5m,
                      {"timeframe": "5m"})

        # --- PERCENTAGE THRESHOLD CROSSES ---
        chg = current.get("todaysChangePerc")
        prev_chg = prev.get("todaysChangePerc")
        if chg is not None and prev_chg is not None:
            # +5% threshold
            if prev_chg < 5 and chg >= 5:
                _fire(EventType.PERCENT_UP_5, prev_chg, chg)
            if prev_chg > -5 and chg <= -5:
                _fire(EventType.PERCENT_DOWN_5, prev_chg, chg)
            # +10% threshold
            if prev_chg < 10 and chg >= 10:
                _fire(EventType.PERCENT_UP_10, prev_chg, chg)
            if prev_chg > -10 and chg <= -10:
                _fire(EventType.PERCENT_DOWN_10, prev_chg, chg)

        # --- CROSSED ABOVE/BELOW OPEN ---
        day_data = current.get("day") or {}
        open_price = day_data.get("o")
        prev_day = prev.get("day") or {}
        prev_open = prev_day.get("o")
        if open_price and open_price > 0 and prev_open and prev_open > 0:
            if prev_price <= prev_open and price > open_price:
                _fire(EventType.CROSSED_ABOVE_OPEN, prev_open, open_price)
            elif prev_price >= prev_open and price < open_price:
                _fire(EventType.CROSSED_BELOW_OPEN, prev_open, open_price)

        # --- VOLUME SPIKE 1MIN ---
        vol_1 = current.get("vol_1min")
        vol_5 = current.get("vol_5min")
        prev_vol_1 = prev.get("vol_1min")
        if vol_1 and vol_5 and vol_5 > 0:
            avg_1min = vol_5 / 5
            if avg_1min > 100 and vol_1 > avg_1min * 3:
                # Check it's a NEW spike (wasn't already spiking)
                if not (prev_vol_1 and prev_vol_1 > avg_1min * 3):
                    _fire(EventType.VOLUME_SPIKE_1MIN, avg_1min, vol_1,
                          {"avg_1min_from_5min": round(avg_1min), "ratio": round(vol_1 / avg_1min, 1)})

        # --- CROSSED ABOVE/BELOW PREV CLOSE ---
        prev_close = (current.get("prevDay") or {}).get("c")
        p_prev_close = (prev.get("prevDay") or {}).get("c")
        if prev_close and prev_close > 0 and p_prev_close and p_prev_close > 0:
            if prev_price <= p_prev_close and price > prev_close:
                _fire(EventType.CROSSED_ABOVE_PREV_CLOSE, p_prev_close, prev_close)
            elif prev_price >= p_prev_close and price < prev_close:
                _fire(EventType.CROSSED_BELOW_PREV_CLOSE, p_prev_close, prev_close)

        # --- RVOL SPIKE (crossed 3x) ---
        rvol = current.get("rvol")
        prev_rvol = prev.get("rvol")
        if rvol and prev_rvol is not None:
            if prev_rvol < 3.0 and rvol >= 3.0:
                _fire(EventType.RVOL_SPIKE, prev_rvol, rvol,
                      {"threshold": 3.0})
            if prev_rvol < 5.0 and rvol >= 5.0:
                _fire(EventType.VOLUME_SURGE, prev_rvol, rvol,
                      {"threshold": 5.0})

        # --- CROSSED DAILY HIGH RESISTANCE (prevDay.h) ---
        prev_day_high = (current.get("prevDay") or {}).get("h")
        p_prev_day_high = (prev.get("prevDay") or {}).get("h")
        if prev_day_high and prev_day_high > 0 and p_prev_day_high:
            if prev_price <= p_prev_day_high and price > prev_day_high:
                _fire(EventType.CROSSED_DAILY_HIGH_RESISTANCE, p_prev_day_high, prev_day_high,
                      {"prev_day_high": prev_day_high})

        # --- CROSSED DAILY LOW SUPPORT (prevDay.l) ---
        prev_day_low = (current.get("prevDay") or {}).get("l")
        p_prev_day_low = (prev.get("prevDay") or {}).get("l")
        if prev_day_low and prev_day_low > 0 and p_prev_day_low:
            if prev_price >= p_prev_day_low and price < prev_day_low:
                _fire(EventType.CROSSED_DAILY_LOW_SUPPORT, p_prev_day_low, prev_day_low,
                      {"prev_day_low": prev_day_low})

        # --- FALSE GAP RETRACEMENT ---
        gap_pct = current.get("gap_percent")
        prev_close_val = (current.get("prevDay") or {}).get("c")
        if gap_pct and prev_close_val and prev_close_val > 0:
            # Gap up > 2% and price retraces below prev close
            if gap_pct >= 2.0 and prev_price > prev_close_val and price <= prev_close_val:
                _fire(EventType.FALSE_GAP_UP_RETRACEMENT, prev_close_val, price,
                      {"gap_percent": gap_pct})
            # Gap down < -2% and price retraces above prev close
            elif gap_pct <= -2.0 and prev_price < prev_close_val and price >= prev_close_val:
                _fire(EventType.FALSE_GAP_DOWN_RETRACEMENT, prev_close_val, price,
                      {"gap_percent": gap_pct})

        # --- RUNNING SUSTAINED (chg_10min > 3%) ---
        chg_10 = current.get("chg_10min")
        prev_chg_10 = prev.get("chg_10min")
        if chg_10 is not None and prev_chg_10 is not None:
            if prev_chg_10 < 3.0 and chg_10 >= 3.0:
                _fire(EventType.RUNNING_UP_SUSTAINED, prev_chg_10, chg_10,
                      {"window": "10min", "threshold": 3.0})
            if prev_chg_10 > -3.0 and chg_10 <= -3.0:
                _fire(EventType.RUNNING_DOWN_SUSTAINED, prev_chg_10, chg_10,
                      {"window": "10min", "threshold": -3.0})

        # --- RUNNING CONFIRMED (chg_5min > 2% AND chg_15min > 4%) ---
        chg_5 = current.get("chg_5min")
        chg_15 = current.get("chg_15min")
        prev_chg_5 = prev.get("chg_5min")
        prev_chg_15 = prev.get("chg_15min")
        if chg_5 is not None and chg_15 is not None and prev_chg_5 is not None and prev_chg_15 is not None:
            # Bullish: both positive thresholds crossed
            was_confirmed_up = prev_chg_5 >= 2.0 and prev_chg_15 >= 4.0
            is_confirmed_up = chg_5 >= 2.0 and chg_15 >= 4.0
            if is_confirmed_up and not was_confirmed_up:
                _fire(EventType.RUNNING_UP_CONFIRMED, prev_chg_5, chg_5,
                      {"chg_5min": chg_5, "chg_15min": chg_15})
            # Bearish: both negative thresholds crossed
            was_confirmed_dn = prev_chg_5 <= -2.0 and prev_chg_15 <= -4.0
            is_confirmed_dn = chg_5 <= -2.0 and chg_15 <= -4.0
            if is_confirmed_dn and not was_confirmed_dn:
                _fire(EventType.RUNNING_DOWN_CONFIRMED, prev_chg_5, chg_5,
                      {"chg_5min": chg_5, "chg_15min": chg_15})

        # --- DAILY SMA(200) CROSS ---
        daily_sma_200 = current.get("daily_sma_200")
        prev_daily_sma_200 = prev.get("daily_sma_200")
        if daily_sma_200 and daily_sma_200 > 0 and prev_daily_sma_200 and prev_daily_sma_200 > 0:
            if prev_price <= prev_daily_sma_200 and price > daily_sma_200:
                _fire(EventType.CROSSED_ABOVE_SMA200, prev_daily_sma_200, daily_sma_200,
                      {"ma_type": "daily_sma_200", "ma_value": daily_sma_200})
            elif prev_price >= prev_daily_sma_200 and price < daily_sma_200:
                _fire(EventType.CROSSED_BELOW_SMA200, prev_daily_sma_200, daily_sma_200,
                      {"ma_type": "daily_sma_200", "ma_value": daily_sma_200})

        return events

    # ========================================================================
    # MAINTENANCE LOOPS
    # ========================================================================

    async def _enriched_refresh_loop(self):
        """Refresh enriched cache every 30 seconds for accurate detection."""
        while self.running:
            await asyncio.sleep(30)
            await self._refresh_enriched_cache()

    # NOTE: _screener_cache and _refresh_screener_cache REMOVED.
    # All fundamental and daily indicator data now flows through
    # snapshot:enriched:latest, populated by the Enrichment Pipeline.
    # This eliminates the event_detector's direct Redis dependency
    # on screener:daily_indicators:latest.

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
    global redis_client, event_bus, engine, event_writer

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

    # Initialize TimescaleDB for event persistence
    event_writer = None
    try:
        from shared.utils.timescale_client import TimescaleClient
        ts_client = TimescaleClient()
        await ts_client.connect(min_size=2, max_size=5)
        logger.info("✅ TimescaleDB connected for event persistence")

        event_writer = EventWriter(ts_client)
        table_ok = await event_writer.ensure_table()
        if table_ok:
            logger.info("✅ market_events table ready")
        else:
            logger.warning("⚠️ market_events table setup failed — events will stream-only")
            event_writer = None
    except Exception as e:
        logger.warning(f"⚠️ TimescaleDB not available — events will stream-only: {e}")
        event_writer = None

    # Initialize and start engine
    engine = EventEngine(redis_client, writer=event_writer)

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(engine.stop()))

    await engine.start()


if __name__ == "__main__":
    asyncio.run(main())
