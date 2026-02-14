"""
TimescaleDB Event Writer - Async batch persistence of market events.

Responsibilities:
1. Ensure market_events table exists (hypertable + indexes + compression + retention)
2. Periodically drain buffered events and batch-insert to TimescaleDB
3. Capture enriched snapshot at event time for full-context historical queries

Architecture:
    EventEngine._publish_event → EventWriter.buffer_event(record, enriched_snapshot)
    EventWriter.run() → COPY market_events (every 5s)
    websocket_server → SELECT market_events WHERE ... (on subscribe_events)

Design:
    - Fire-and-forget: if DB insert fails, events are lost in DB but real-time is unaffected
    - Batch inserts: collects events for 5 seconds, then does one INSERT
    - Schema-on-startup: creates table/hypertable/indexes on first connect
    - JSONB context: enriched snapshot stored as JSONB for flexible querying
    - Compression: auto-compresses chunks > 2 days (~90% reduction)
    - Retention: auto-drops chunks > 60 days
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

from shared.utils.timescale_client import TimescaleClient

logger = logging.getLogger("event-detector.writer")

# Configuration
PERSIST_INTERVAL_SECONDS = 5       # Batch write every 5 seconds
MAX_BUFFER_SIZE = 50_000           # Safety limit — drop oldest if exceeded
MAX_BATCH_SIZE = 10_000            # Max rows per INSERT
RETENTION_DAYS = 60                # Auto-drop data older than 60 days
COMPRESSION_AFTER_DAYS = 2         # Compress chunks older than 2 days

# Columns for the market_events table (order matters for INSERT)
COLUMNS = [
    "id", "ts", "symbol", "event_type", "rule_id", "price",
    # Core indexed columns
    "change_pct", "rvol", "volume", "market_cap", "float_shares",
    "gap_pct", "security_type", "sector",
    # Event-specific
    "prev_value", "new_value", "delta", "delta_pct",
    # Context at event time
    "change_from_open", "open_price", "prev_close", "vwap",
    "atr_pct", "intraday_high", "intraday_low",
    # Time-window changes
    "chg_1min", "chg_5min", "chg_10min", "chg_15min", "chg_30min",
    "vol_1min", "vol_5min",
    # Technical indicators
    "rsi", "ema_20", "ema_50",
    # Details + full enriched context
    "details", "context",
]


class EventWriter:
    """
    Async writer that batch-persists market events to TimescaleDB.

    Usage:
        writer = EventWriter(timescale_client)
        await writer.ensure_table()
        asyncio.create_task(writer.run())

        # From EventEngine._publish_event:
        writer.buffer_event(event_record, enriched_snapshot)
    """

    def __init__(self, db: TimescaleClient):
        self.db = db
        self._buffer: List[tuple] = []
        self._table_ready = False

        # Stats
        self._total_persisted = 0
        self._total_batches = 0
        self._total_errors = 0
        self._total_dropped = 0

    # ========================================================================
    # PUBLIC API
    # ========================================================================

    def buffer_event(
        self,
        event_dict: Dict[str, Any],
        enriched_snapshot: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Buffer an event for batch persistence.

        Args:
            event_dict: EventRecord.to_dict() output
            enriched_snapshot: Full enriched data for the symbol at event time
        """
        try:
            row = self._build_row(event_dict, enriched_snapshot)
            self._buffer.append(row)

            # Safety limit — drop oldest events if buffer grows too large
            if len(self._buffer) > MAX_BUFFER_SIZE:
                dropped = len(self._buffer) - MAX_BUFFER_SIZE
                self._buffer = self._buffer[dropped:]
                self._total_dropped += dropped
                logger.warning(f"Buffer overflow: dropped {dropped} oldest events")

        except Exception as e:
            logger.error(f"Error buffering event: {e}")

    # ========================================================================
    # PERSISTENCE LOOP
    # ========================================================================

    async def run(self) -> None:
        """
        Main persistence loop. Runs continuously.

        Every PERSIST_INTERVAL_SECONDS:
        1. Drains buffered events
        2. Batch inserts to TimescaleDB
        3. Logs stats
        """
        logger.info(f"EventWriter started (interval={PERSIST_INTERVAL_SECONDS}s, "
                     f"retention={RETENTION_DAYS}d, compression_after={COMPRESSION_AFTER_DAYS}d)")

        while True:
            try:
                await asyncio.sleep(PERSIST_INTERVAL_SECONDS)
                await self._persist_batch()
            except asyncio.CancelledError:
                # Final flush on shutdown
                logger.info("EventWriter final flush on shutdown")
                await self._persist_batch()
                raise
            except Exception as e:
                logger.error(f"EventWriter loop error: {e}")
                self._total_errors += 1

    async def _persist_batch(self) -> None:
        """Drain buffer and persist to TimescaleDB."""
        if not self._buffer:
            return

        if not self._table_ready:
            return

        # Drain buffer atomically
        batch = self._buffer[:MAX_BATCH_SIZE]
        self._buffer = self._buffer[len(batch):]

        try:
            await self._batch_insert(batch)
            self._total_persisted += len(batch)
            self._total_batches += 1

            if self._total_batches % 12 == 1 or len(batch) > 100:
                logger.info(
                    f"Events persisted: batch={len(batch)}, "
                    f"total={self._total_persisted}, pending={len(self._buffer)}"
                )
        except Exception as e:
            logger.error(f"Events persist failed: batch={len(batch)}, error={e}")
            self._total_errors += 1
            # Events are lost in DB but real-time is unaffected

    async def _batch_insert(self, batch: List[tuple]) -> None:
        """Batch INSERT events using executemany."""
        if not batch:
            return

        placeholders = ", ".join(f"${i+1}" for i in range(len(COLUMNS)))
        query = f"""
            INSERT INTO market_events ({", ".join(COLUMNS)})
            VALUES ({placeholders})
            ON CONFLICT (id, ts) DO NOTHING
        """

        await self.db.executemany(query, batch)

    # ========================================================================
    # ROW BUILDER
    # ========================================================================

    def _build_row(
        self,
        evt: Dict[str, Any],
        enriched: Optional[Dict[str, Any]] = None,
    ) -> tuple:
        """
        Build a tuple row for INSERT from event dict + enriched snapshot.

        The 'context' JSONB column captures the FULL enriched snapshot
        (all 87+ fields: SMAs, MACD, Stoch, bid/ask, daily indicators, etc.)
        so historical queries can filter on ANY field via JSONB operators.
        """
        def _f(key: str) -> Optional[float]:
            """Safe float extraction."""
            v = evt.get(key)
            if v is None or v == "":
                return None
            try:
                return float(v)
            except (ValueError, TypeError):
                return None

        def _i(key: str) -> Optional[int]:
            """Safe int extraction."""
            v = evt.get(key)
            if v is None or v == "":
                return None
            try:
                return int(float(v))
            except (ValueError, TypeError):
                return None

        # Parse timestamp
        ts_raw = evt.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_raw) if isinstance(ts_raw, str) else ts_raw
        except Exception:
            ts = datetime.utcnow()

        # Build context JSONB from enriched snapshot
        context_json = None
        if enriched:
            # Remove very large or redundant fields
            ctx = {k: v for k, v in enriched.items()
                   if v is not None and k not in ("day", "prevDay", "lastTrade", "lastQuote")}
            try:
                context_json = json.dumps(ctx)
            except Exception:
                context_json = None

        # Details JSONB
        details_raw = evt.get("details")
        details_json = None
        if details_raw:
            if isinstance(details_raw, str):
                details_json = details_raw  # Already JSON string
            elif isinstance(details_raw, dict):
                details_json = json.dumps(details_raw)

        return (
            evt.get("id", ""),
            ts,
            evt.get("symbol", ""),
            evt.get("event_type", ""),
            evt.get("rule_id", ""),
            _f("price"),
            # Core indexed
            _f("change_percent"),
            _f("rvol"),
            _i("volume"),
            _f("market_cap"),
            _f("float_shares"),
            _f("gap_percent"),
            evt.get("security_type"),
            evt.get("sector"),
            # Event-specific
            _f("prev_value"),
            _f("new_value"),
            _f("delta"),
            _f("delta_percent"),
            # Context
            _f("change_from_open"),
            _f("open_price"),
            _f("prev_close"),
            _f("vwap"),
            _f("atr_percent"),
            _f("intraday_high"),
            _f("intraday_low"),
            # Time-window
            _f("chg_1min"),
            _f("chg_5min"),
            _f("chg_10min"),
            _f("chg_15min"),
            _f("chg_30min"),
            _i("vol_1min"),
            _i("vol_5min"),
            # Technical
            _f("rsi"),
            _f("ema_20"),
            _f("ema_50"),
            # JSONB
            details_json,
            context_json,
        )

    # ========================================================================
    # TABLE MANAGEMENT
    # ========================================================================

    async def ensure_table(self) -> bool:
        """
        Ensure market_events table exists with hypertable, indexes,
        compression policy and retention policy.

        Returns True if ready.
        """
        try:
            exists = await self.db.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'market_events'
                )
            """)

            if not exists:
                await self._create_table()
                await self._create_hypertable()
                await self._create_indexes()
                await self._create_compression_policy()
                await self._create_retention_policy()
                logger.info("✅ market_events table created with all policies")
            else:
                logger.info("✅ market_events table already exists")

            self._table_ready = True
            return True

        except Exception as e:
            logger.error(f"Error ensuring market_events table: {e}")
            self._table_ready = False
            return False

    async def _create_table(self) -> None:
        """Create the market_events table."""
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS market_events (
                -- Identity
                id              VARCHAR(36)         NOT NULL,
                ts              TIMESTAMPTZ         NOT NULL,
                symbol          VARCHAR(20)         NOT NULL,
                event_type      VARCHAR(50)         NOT NULL,
                rule_id         VARCHAR(80)         NOT NULL,
                price           DOUBLE PRECISION,

                -- Core indexed columns (most-used filters)
                change_pct      DOUBLE PRECISION,
                rvol            DOUBLE PRECISION,
                volume          BIGINT,
                market_cap      DOUBLE PRECISION,
                float_shares    DOUBLE PRECISION,
                gap_pct         DOUBLE PRECISION,
                security_type   VARCHAR(10),
                sector          VARCHAR(60),

                -- Event-specific
                prev_value      DOUBLE PRECISION,
                new_value       DOUBLE PRECISION,
                delta           DOUBLE PRECISION,
                delta_pct       DOUBLE PRECISION,

                -- Context at event time
                change_from_open DOUBLE PRECISION,
                open_price      DOUBLE PRECISION,
                prev_close      DOUBLE PRECISION,
                vwap            DOUBLE PRECISION,
                atr_pct         DOUBLE PRECISION,
                intraday_high   DOUBLE PRECISION,
                intraday_low    DOUBLE PRECISION,

                -- Time-window changes
                chg_1min        DOUBLE PRECISION,
                chg_5min        DOUBLE PRECISION,
                chg_10min       DOUBLE PRECISION,
                chg_15min       DOUBLE PRECISION,
                chg_30min       DOUBLE PRECISION,
                vol_1min        BIGINT,
                vol_5min        BIGINT,

                -- Technical indicators
                rsi             DOUBLE PRECISION,
                ema_20          DOUBLE PRECISION,
                ema_50          DOUBLE PRECISION,

                -- Flexible storage
                details         JSONB,
                context         JSONB,

                PRIMARY KEY (id, ts)
            )
        """)
        logger.info("Created market_events table")

    async def _create_hypertable(self) -> None:
        """Convert to TimescaleDB hypertable with daily chunks."""
        try:
            await self.db.execute("""
                SELECT create_hypertable(
                    'market_events', 'ts',
                    chunk_time_interval => INTERVAL '1 day',
                    if_not_exists => TRUE
                )
            """)
            logger.info("Created market_events hypertable (1-day chunks)")
        except Exception as e:
            logger.warning(f"Hypertable creation note: {e}")

    async def _create_indexes(self) -> None:
        """Create indexes for common query patterns."""
        indexes = [
            # Primary query: filter by event_type + time range (DESC for recent-first)
            ("idx_mevt_type_ts", "event_type, ts DESC"),
            # Symbol lookup: "show me all events for AAPL today"
            ("idx_mevt_sym_ts", "symbol, ts DESC"),
            # Halt-specific partial index (rare events, fast lookup)
            ("idx_mevt_halts", "ts DESC", "WHERE event_type IN ('halt', 'resume')"),
        ]

        for idx_name, idx_cols, *extra in indexes:
            where_clause = extra[0] if extra else ""
            try:
                await self.db.execute(f"""
                    CREATE INDEX IF NOT EXISTS {idx_name}
                    ON market_events ({idx_cols})
                    {where_clause}
                """)
                logger.info(f"Created index {idx_name}")
            except Exception as e:
                logger.warning(f"Index {idx_name}: {e}")

    async def _create_compression_policy(self) -> None:
        """Enable compression on chunks older than COMPRESSION_AFTER_DAYS."""
        try:
            await self.db.execute("""
                ALTER TABLE market_events SET (
                    timescaledb.compress,
                    timescaledb.compress_segmentby = 'event_type, symbol',
                    timescaledb.compress_orderby = 'ts DESC'
                )
            """)
            await self.db.execute(f"""
                SELECT add_compression_policy(
                    'market_events',
                    INTERVAL '{COMPRESSION_AFTER_DAYS} days',
                    if_not_exists => TRUE
                )
            """)
            logger.info(f"Compression policy: after {COMPRESSION_AFTER_DAYS} days")
        except Exception as e:
            logger.warning(f"Compression policy note: {e}")

    async def _create_retention_policy(self) -> None:
        """Auto-drop chunks older than RETENTION_DAYS."""
        try:
            await self.db.execute(f"""
                SELECT add_retention_policy(
                    'market_events',
                    INTERVAL '{RETENTION_DAYS} days',
                    if_not_exists => TRUE
                )
            """)
            logger.info(f"Retention policy: drop after {RETENTION_DAYS} days")
        except Exception as e:
            logger.warning(f"Retention policy note: {e}")

    # ========================================================================
    # STATS
    # ========================================================================

    def get_stats(self) -> Dict[str, Any]:
        """Get writer statistics."""
        return {
            "total_persisted": self._total_persisted,
            "total_batches": self._total_batches,
            "total_errors": self._total_errors,
            "total_dropped": self._total_dropped,
            "pending": len(self._buffer),
            "table_ready": self._table_ready,
        }
