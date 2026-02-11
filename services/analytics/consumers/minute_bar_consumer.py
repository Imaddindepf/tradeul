"""
Minute Bar Consumer - Reads AM.* bars from Redis Stream and feeds BarEngine.

Consumes stream:market:minutes with a consumer group.
Reads in batch (count=15000) for efficient burst handling.
Handles the minute close detection via BarEngine.on_bar().

Architecture:
    polygon_ws → XADD stream:market:minutes
    MinuteBarConsumer → XREADGROUP → BarEngine.on_bar()
"""

import asyncio
from typing import Optional

from shared.utils.redis_client import RedisClient
from shared.utils.logger import get_logger
from bar_engine import BarEngine, BarData, parse_bar_from_stream

logger = get_logger(__name__)

# Stream configuration
STREAM_NAME = "stream:market:minutes"
CONSUMER_GROUP = "analytics_bar_engine"
CONSUMER_NAME = "bar_consumer_0"  # For sharding: bar_consumer_{shard_id}
BATCH_SIZE = 15000  # Read up to 15K messages per batch (handles 11K burst)
BLOCK_MS = 2000     # Block 2 seconds waiting for new messages


class MinuteBarConsumer:
    """
    Consumes minute bars from Redis Stream and feeds them to BarEngine.

    Designed for high throughput:
    - Batch reads (up to 15K messages per XREADGROUP)
    - Processes entire batch in BarEngine.process_batch()
    - ACKs all processed messages in one pipeline call
    - Logs stream backlog for monitoring
    """

    def __init__(
        self,
        redis_client: RedisClient,
        bar_engine: BarEngine,
        stream_name: str = STREAM_NAME,
        consumer_group: str = CONSUMER_GROUP,
        consumer_name: str = CONSUMER_NAME,
        batch_size: int = BATCH_SIZE,
        block_ms: int = BLOCK_MS,
    ):
        self.redis = redis_client
        self.bar_engine = bar_engine
        self.stream_name = stream_name
        self.consumer_group = consumer_group
        self.consumer_name = consumer_name
        self.batch_size = batch_size
        self.block_ms = block_ms

        # Stats
        self._total_messages = 0
        self._total_batches = 0
        self._total_parse_errors = 0

    async def initialize(self) -> None:
        """Create consumer group if it doesn't exist."""
        try:
            await self.redis.create_consumer_group(
                self.stream_name,
                self.consumer_group,
                mkstream=True,
            )
            logger.info(
                "minute_bar_consumer_group_created",
                stream=self.stream_name,
                group=self.consumer_group,
            )
        except Exception as e:
            # Group already exists
            logger.debug(
                "minute_bar_consumer_group_exists",
                error=str(e),
            )

    async def run(self) -> None:
        """
        Main consumer loop. Runs continuously.

        Reads batches of minute bars from the stream,
        parses them, feeds BarEngine, and ACKs.
        """
        await self.initialize()
        logger.info(
            "minute_bar_consumer_started",
            stream=self.stream_name,
            batch_size=self.batch_size,
        )

        while True:
            try:
                await self._consume_batch()
            except asyncio.CancelledError:
                logger.info("minute_bar_consumer_cancelled")
                raise
            except Exception as e:
                logger.error(
                    "minute_bar_consumer_error",
                    error=str(e),
                    error_type=type(e).__name__,
                )
                await asyncio.sleep(2)

    async def _consume_batch(self) -> None:
        """Read and process one batch of messages."""
        messages = await self.redis.read_stream(
            stream_name=self.stream_name,
            consumer_group=self.consumer_group,
            consumer_name=self.consumer_name,
            count=self.batch_size,
            block=self.block_ms,
        )

        if not messages:
            return

        # Parse all messages into BarData objects
        bars = []
        message_ids = []

        for stream_name, stream_messages in messages:
            for message_id, data in stream_messages:
                message_ids.append(message_id)
                bar = parse_bar_from_stream(data)
                if bar is not None:
                    bars.append(bar)
                else:
                    self._total_parse_errors += 1

        if not bars:
            # ACK even if no valid bars (to consume bad messages)
            if message_ids:
                await self._ack_messages(message_ids)
            return

        # Process batch in BarEngine
        closed = self.bar_engine.process_batch(bars)

        # ACK all messages
        await self._ack_messages(message_ids)

        # Update stats
        self._total_messages += len(bars)
        self._total_batches += 1

        # Log stream backlog periodically (every 30 batches)
        if self._total_batches % 30 == 0:
            await self._log_backlog()

    async def _ack_messages(self, message_ids: list) -> None:
        """ACK processed messages."""
        try:
            if message_ids:
                await self.redis.xack(
                    self.stream_name,
                    self.consumer_group,
                    *message_ids,
                )
        except Exception as e:
            logger.error("minute_bar_ack_error", error=str(e))

    async def _log_backlog(self) -> None:
        """Log stream length for backlog monitoring."""
        try:
            stream_len = await self.redis.client.xlen(self.stream_name)
            engine_stats = self.bar_engine.get_stats()

            logger.info(
                "minute_bar_consumer_stats",
                total_messages=self._total_messages,
                total_batches=self._total_batches,
                parse_errors=self._total_parse_errors,
                stream_backlog=stream_len,
                engine_symbols=engine_stats["symbols"],
                engine_bars_closed=engine_stats["total_bars_closed"],
                p95_batch_ms=engine_stats["p95_batch_time_ms"],
                rss_mb=engine_stats["rss_mb"],
            )
        except Exception as e:
            logger.debug("backlog_check_error", error=str(e))

    def get_stats(self) -> dict:
        """Get consumer statistics."""
        return {
            "total_messages": self._total_messages,
            "total_batches": self._total_batches,
            "parse_errors": self._total_parse_errors,
        }
