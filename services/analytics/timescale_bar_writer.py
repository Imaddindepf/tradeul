"""
TimescaleDB Bar Writer - Async persistence of closed minute bars.

Responsibilities:
1. Periodically drain closed bars from BarEngine and batch-insert to TimescaleDB
2. On startup, load historical bars from TimescaleDB to warm up BarEngine

Architecture:
    BarEngine._bars_closed_buffer → TimescaleBarWriter.run() → INSERT minute_bars
    TimescaleDB minute_bars → TimescaleBarWriter.warmup() → BarEngine.warmup()

Design:
    - Fire-and-forget: if DB insert fails, bars are lost in DB but BarEngine is unaffected
    - Batch inserts: collects bars for 60 seconds, then does one INSERT
    - Warmup: ONE query on startup to load last 200 bars per symbol
    - NEVER queried during normal operation (hot path is 100% in-memory)
"""

import asyncio
from typing import Optional, List
from datetime import datetime

from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import get_logger
from bar_engine import BarEngine

logger = get_logger(__name__)

# Configuration
PERSIST_INTERVAL_SECONDS = 60  # Batch write every 60 seconds
WARMUP_MINUTES = 200           # Load last 200 minutes on startup
MAX_BATCH_SIZE = 50000         # Safety limit per batch insert


class TimescaleBarWriter:
    """
    Async writer that persists closed minute bars to TimescaleDB
    and warms up the BarEngine on startup.
    """

    def __init__(
        self,
        timescale_client: TimescaleClient,
        bar_engine: BarEngine,
        persist_interval: int = PERSIST_INTERVAL_SECONDS,
        warmup_minutes: int = WARMUP_MINUTES,
    ):
        self.db = timescale_client
        self.bar_engine = bar_engine
        self.persist_interval = persist_interval
        self.warmup_minutes = warmup_minutes

        # Stats
        self._total_persisted = 0
        self._total_batches = 0
        self._total_errors = 0

    # ========================================================================
    # Warmup: load historical bars from TimescaleDB
    # ========================================================================

    async def warmup(self) -> int:
        """
        Load historical minute bars from TimescaleDB and feed to BarEngine.

        Called ONCE on startup to warm up talipp indicators so RSI, EMA etc.
        return values immediately instead of waiting for 14+ bars.

        Returns:
            Number of bars loaded.
        """
        try:
            # Check if table exists
            table_exists = await self._ensure_table_exists()
            if not table_exists:
                logger.info("minute_bars_table_created_no_historical_data")
                return 0

            logger.info(
                "bar_engine_warmup_starting",
                minutes=self.warmup_minutes,
            )

            # Query last N minutes of bars, ordered by symbol and timestamp
            query = """
                SELECT symbol, ts, open, high, low, close, volume
                FROM minute_bars
                WHERE ts > EXTRACT(EPOCH FROM (NOW() - INTERVAL '%s minutes')) * 1000
                ORDER BY symbol, ts ASC
            """ % self.warmup_minutes

            rows = await self.db.fetch(query)

            if not rows:
                logger.info("bar_engine_warmup_no_data")
                return 0

            # Group bars by symbol
            bars_by_symbol = {}
            for row in rows:
                sym = row['symbol']
                if sym not in bars_by_symbol:
                    bars_by_symbol[sym] = []
                bars_by_symbol[sym].append({
                    'ts': row['ts'],
                    'open': float(row['open']),
                    'high': float(row['high']),
                    'low': float(row['low']),
                    'close': float(row['close']),
                    'volume': int(row['volume']),
                    'av': 0,  # Not stored in DB, not needed for warmup
                    'vw': 0,
                })

            # Feed to BarEngine
            total_bars = 0
            for sym, bars in bars_by_symbol.items():
                self.bar_engine.warmup(sym, bars)
                total_bars += len(bars)

            # Clear persistence buffer (warmup bars came FROM DB, don't re-persist)
            self.bar_engine.warmup_complete()

            logger.info(
                "bar_engine_warmup_complete",
                symbols=len(bars_by_symbol),
                total_bars=total_bars,
                avg_bars_per_symbol=round(total_bars / max(len(bars_by_symbol), 1), 1),
            )

            return total_bars

        except Exception as e:
            logger.error(
                "bar_engine_warmup_error",
                error=str(e),
                error_type=type(e).__name__,
            )
            return 0

    # ========================================================================
    # Persistence loop: batch write closed bars
    # ========================================================================

    async def run(self) -> None:
        """
        Main persistence loop. Runs continuously.

        Every persist_interval seconds:
        1. Drains closed bars from BarEngine
        2. Batch inserts to TimescaleDB
        3. Logs stats
        """
        logger.info(
            "timescale_bar_writer_started",
            interval_seconds=self.persist_interval,
        )

        while True:
            try:
                await asyncio.sleep(self.persist_interval)
                await self._persist_batch()
            except asyncio.CancelledError:
                # Final flush on shutdown
                logger.info("timescale_bar_writer_final_flush")
                await self._persist_batch()
                raise
            except Exception as e:
                logger.error(
                    "timescale_bar_writer_error",
                    error=str(e),
                    error_type=type(e).__name__,
                )
                self._total_errors += 1

    async def _persist_batch(self) -> None:
        """Drain and persist closed bars."""
        bars = self.bar_engine.drain_closed_bars()

        if not bars:
            return

        # Safety limit
        if len(bars) > MAX_BATCH_SIZE:
            logger.warning(
                "bar_batch_too_large",
                size=len(bars),
                max=MAX_BATCH_SIZE,
                truncating=True,
            )
            bars = bars[:MAX_BATCH_SIZE]

        try:
            await self._batch_insert(bars)
            self._total_persisted += len(bars)
            self._total_batches += 1

            logger.info(
                "bars_persisted_to_timescale",
                bars=len(bars),
                total_persisted=self._total_persisted,
            )
        except Exception as e:
            logger.error(
                "bars_persist_failed",
                bars=len(bars),
                error=str(e),
            )
            self._total_errors += 1
            # Bars are lost in DB but BarEngine state is unaffected

    async def _batch_insert(self, bars: List[dict]) -> None:
        """
        Batch INSERT bars into TimescaleDB.

        Uses INSERT ... ON CONFLICT DO NOTHING to handle duplicates
        (e.g., from warmup + live overlap).
        """
        if not bars:
            return

        query = """
            INSERT INTO minute_bars (symbol, ts, open, high, low, close, volume)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (symbol, ts) DO NOTHING
        """

        # Prepare batch of tuples
        records = [
            (
                bar['symbol'],
                bar['ts'],
                bar['open'],
                bar['high'],
                bar['low'],
                bar['close'],
                bar['volume'],
            )
            for bar in bars
        ]

        await self.db.executemany(query, records)

    # ========================================================================
    # Table management
    # ========================================================================

    async def _ensure_table_exists(self) -> bool:
        """
        Ensure minute_bars table exists in TimescaleDB.

        Returns True if table already existed (may have data for warmup).
        Returns False if table was just created (no data).
        """
        try:
            # Check if table exists
            result = await self.db.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'minute_bars'
                )
            """)

            if result:
                return True

            # Create table
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS minute_bars (
                    symbol VARCHAR(20) NOT NULL,
                    ts BIGINT NOT NULL,
                    open DOUBLE PRECISION NOT NULL,
                    high DOUBLE PRECISION NOT NULL,
                    low DOUBLE PRECISION NOT NULL,
                    close DOUBLE PRECISION NOT NULL,
                    volume BIGINT NOT NULL,
                    PRIMARY KEY (symbol, ts)
                )
            """)

            # Create TimescaleDB hypertable (if extension available)
            try:
                await self.db.execute("""
                    SELECT create_hypertable('minute_bars', 'ts',
                        chunk_time_interval => 86400000,
                        if_not_exists => TRUE
                    )
                """)
                logger.info("minute_bars_hypertable_created")
            except Exception:
                # TimescaleDB extension not available, regular table is fine
                logger.info("minute_bars_regular_table_created")

            # Create index for warmup query
            await self.db.execute("""
                CREATE INDEX IF NOT EXISTS idx_minute_bars_ts
                ON minute_bars (ts DESC)
            """)

            return False

        except Exception as e:
            logger.error("ensure_table_error", error=str(e))
            return False

    # ========================================================================
    # Stats
    # ========================================================================

    def get_stats(self) -> dict:
        """Get writer statistics."""
        return {
            "total_persisted": self._total_persisted,
            "total_batches": self._total_batches,
            "total_errors": self._total_errors,
            "pending_bars": len(self.bar_engine.closed_bars_buffer),
        }
