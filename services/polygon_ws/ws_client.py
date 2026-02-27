"""
Polygon WebSocket Client — Production Architecture

High-throughput WebSocket client with:
- Infinite reconnection via websockets v12 async iterator (exponential backoff)
- asyncio.Queue decouples WS recv from Redis writes (non-blocking event loop)
- No client-side pings (Polygon pings us, library auto-pongs)
- Watchdog supervisor for health monitoring
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Set, Optional, Callable, Dict, Any
import structlog
import websockets
from websockets.exceptions import ConnectionClosed, ConnectionClosedOK

from shared.config.settings import settings
from shared.models.polygon import PolygonTrade, PolygonQuote, PolygonAgg, PolygonLuld

logger = structlog.get_logger(__name__)

# Number of worker tasks draining the queue
NUM_WORKERS = 4
# Max queue depth before logging backpressure warning
QUEUE_HIGH_WATERMARK = 10_000
# Watchdog check interval
WATCHDOG_INTERVAL = 60


class PolygonWebSocketClient:
    """
    Production WebSocket client for Polygon.

    Architecture:
        WS recv → json.loads → queue.put_nowait()   (non-blocking)
                                    ↓
                Worker 1..N: queue.get() → await handler() → await Redis XADD
    """

    WS_URL = "wss://socket.polygon.io/stocks"

    EVENT_TRADE = "T"
    EVENT_QUOTE = "Q"
    EVENT_AGGREGATE = "A"
    EVENT_LULD = "LULD"
    EVENT_MINUTE_AGG = "AM"

    def __init__(
        self,
        api_key: str,
        on_trade: Optional[Callable] = None,
        on_quote: Optional[Callable] = None,
        on_aggregate: Optional[Callable] = None,
        on_minute_aggregate: Optional[Callable] = None,
        on_luld: Optional[Callable] = None,
        num_workers: int = NUM_WORKERS,
    ):
        self.api_key = api_key
        self.on_trade = on_trade
        self.on_quote = on_quote
        self.on_aggregate = on_aggregate
        self.on_minute_aggregate = on_minute_aggregate
        self.on_luld = on_luld
        self.num_workers = num_workers

        # Connection state
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.is_connected = False
        self.is_authenticated = False
        self._closing = False

        # Subscriptions
        self.subscribed_tickers: Set[str] = set()

        # Queue & workers
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=50_000)
        self._worker_tasks: list[asyncio.Task] = []
        self._watchdog_task: Optional[asyncio.Task] = None

        # Handler dispatch table
        self._handlers: Dict[str, Callable] = {}

        # Stats
        self.stats = {
            "trades_received": 0,
            "quotes_received": 0,
            "aggregates_received": 0,
            "minute_aggregates_received": 0,
            "luld_received": 0,
            "luld_halts": 0,
            "luld_resumes": 0,
            "errors": 0,
            "reconnections": 0,
            "last_message_time": None,
            "queue_peak": 0,
            "queue_drops": 0,
            "messages_dispatched": 0,
        }

        logger.info("polygon_ws_client_initialized", workers=num_workers)

    # =====================================================================
    # Connection lifecycle
    # =====================================================================

    async def connect(self):
        """
        Connect to Polygon WebSocket with infinite auto-reconnection.

        Uses websockets v12 async iterator pattern:
        - Exponential backoff: 0 → 3.1 → 5 → 8 → 13 → ... → 90s cap
        - Retries ALL errors (network, DNS, timeout) by default
        - No max_reconnects — runs forever
        """
        self._build_handler_table()
        self._watchdog_task = asyncio.create_task(self._watchdog())

        logger.info("ws_connect_loop_starting", url=self.WS_URL)

        async for ws in websockets.connect(
            self.WS_URL,
            ping_interval=None,       # No client-side pings
            ping_timeout=None,        # Polygon pings us, library auto-pongs
            close_timeout=10,
            max_size=10_485_760,      # 10 MB max message
            open_timeout=15,
        ):
            try:
                self.ws = ws
                self.is_connected = True
                logger.info("connected_to_polygon_ws")

                # Authenticate
                await self._authenticate()

                # Start queue workers
                self._start_workers()

                # Non-blocking recv loop
                await self._process_messages()

            except ConnectionClosedOK:
                logger.info("connection_closed_ok")
                if self._closing:
                    return  # Graceful shutdown
            except ConnectionClosed as e:
                self.stats["reconnections"] += 1
                logger.warning(
                    "connection_closed",
                    code=e.code,
                    reason=e.reason,
                    reconnections=self.stats["reconnections"],
                )
            except Exception as e:
                self.stats["errors"] += 1
                self.stats["reconnections"] += 1
                logger.error(
                    "unexpected_error",
                    error=str(e),
                    error_type=type(e).__name__,
                    reconnections=self.stats["reconnections"],
                )
            finally:
                self.is_connected = False
                self.is_authenticated = False
                self._stop_workers()
                # Clear stale subscriptions — will be re-applied by reconciler
                self.subscribed_tickers.clear()

            if self._closing:
                return

            logger.info("ws_reconnecting_with_backoff")
            # websockets.connect() handles backoff automatically via __aiter__

    # =====================================================================
    # Authentication
    # =====================================================================

    async def _authenticate(self):
        auth_message = {"action": "auth", "params": self.api_key}
        await self.ws.send(json.dumps(auth_message))

        response = await self.ws.recv()
        response_data = json.loads(response)

        if response_data[0].get("status") in ["auth_success", "connected", "success"]:
            self.is_authenticated = True
            logger.info("authenticated_successfully", response=response_data[0])
        else:
            logger.error("authentication_failed", response=response_data)
            raise Exception("Failed to authenticate with Polygon WebSocket")

    # =====================================================================
    # Non-blocking message processing
    # =====================================================================

    def _build_handler_table(self):
        """Build dispatch table from callbacks."""
        self._handlers = {}
        if self.on_trade:
            self._handlers[self.EVENT_TRADE] = self._handle_trade
        if self.on_quote:
            self._handlers[self.EVENT_QUOTE] = self._handle_quote
        if self.on_aggregate:
            self._handlers[self.EVENT_AGGREGATE] = self._handle_aggregate
        if self.on_minute_aggregate:
            self._handlers[self.EVENT_MINUTE_AGG] = self._handle_minute_aggregate
        if self.on_luld:
            self._handlers[self.EVENT_LULD] = self._handle_luld

    async def _process_messages(self):
        """
        Non-blocking recv loop.

        Parses JSON and dispatches to queue without awaiting Redis.
        The event loop stays free to handle pong responses.
        """
        async for message in self.ws:
            try:
                data = json.loads(message)

                if not isinstance(data, list):
                    continue

                for event in data:
                    ev_type = event.get("ev")

                    if ev_type == "status":
                        logger.debug("status_message", message=event.get("message"))
                        continue

                    if ev_type in self._handlers:
                        self._dispatch_to_queue(ev_type, event)

                self.stats["last_message_time"] = datetime.now(timezone.utc).isoformat()

            except json.JSONDecodeError as e:
                logger.error("json_decode_error", error=str(e))
                self.stats["errors"] += 1
            except Exception as e:
                logger.error(
                    "message_processing_error",
                    error=str(e),
                    error_type=type(e).__name__,
                )
                self.stats["errors"] += 1

    def _dispatch_to_queue(self, ev_type: str, event: dict):
        """Non-blocking put to queue. Drops if full (backpressure)."""
        try:
            self._queue.put_nowait((ev_type, event))
            self.stats["messages_dispatched"] += 1

            # Track peak queue depth
            qsize = self._queue.qsize()
            if qsize > self.stats["queue_peak"]:
                self.stats["queue_peak"] = qsize

            if qsize > QUEUE_HIGH_WATERMARK and qsize % 1000 == 0:
                logger.warning("queue_backpressure", depth=qsize)

        except asyncio.QueueFull:
            self.stats["queue_drops"] += 1
            if self.stats["queue_drops"] % 1000 == 1:
                logger.error(
                    "queue_full_dropping",
                    drops=self.stats["queue_drops"],
                    ev_type=ev_type,
                )

    # =====================================================================
    # Queue workers
    # =====================================================================

    def _start_workers(self):
        """Start N worker tasks to drain the queue."""
        self._stop_workers()  # Clean up any stale workers
        for i in range(self.num_workers):
            task = asyncio.create_task(self._queue_worker(i))
            self._worker_tasks.append(task)
        logger.info("workers_started", count=self.num_workers)

    def _stop_workers(self):
        """Cancel all worker tasks."""
        for task in self._worker_tasks:
            task.cancel()
        self._worker_tasks.clear()

    async def _queue_worker(self, worker_id: int):
        """Drain queue and call handlers (which do the Redis writes)."""
        while True:
            try:
                ev_type, event = await self._queue.get()
                try:
                    handler = self._handlers.get(ev_type)
                    if handler:
                        await handler(event)
                except Exception as e:
                    logger.error(
                        "worker_handler_error",
                        worker=worker_id,
                        ev_type=ev_type,
                        error=str(e),
                    )
                    self.stats["errors"] += 1
                finally:
                    self._queue.task_done()
            except asyncio.CancelledError:
                return

    # =====================================================================
    # Event handlers (unchanged interface — called from workers)
    # =====================================================================

    async def _handle_trade(self, data: Dict[str, Any]):
        try:
            trade = PolygonTrade(**data)
            self.stats["trades_received"] += 1
            if self.on_trade:
                await self.on_trade(trade)
        except Exception as e:
            logger.error("trade_processing_error", error=str(e), symbol=data.get("sym"))
            self.stats["errors"] += 1

    async def _handle_quote(self, data: Dict[str, Any]):
        try:
            quote = PolygonQuote(**data)
            self.stats["quotes_received"] += 1
            if self.on_quote:
                await self.on_quote(quote)
        except Exception as e:
            logger.error("quote_processing_error", error=str(e), symbol=data.get("sym"))
            self.stats["errors"] += 1

    async def _handle_aggregate(self, data: Dict[str, Any]):
        try:
            aggregate = PolygonAgg(**data)
            self.stats["aggregates_received"] += 1
            if self.on_aggregate:
                await self.on_aggregate(aggregate)
        except Exception as e:
            logger.error("aggregate_processing_error", error=str(e), symbol=data.get("sym"))
            self.stats["errors"] += 1

    async def _handle_minute_aggregate(self, data: Dict[str, Any]):
        try:
            aggregate = PolygonAgg(**data)
            self.stats["minute_aggregates_received"] += 1
            if self.on_minute_aggregate:
                await self.on_minute_aggregate(aggregate)
        except Exception as e:
            logger.error("minute_aggregate_processing_error", error=str(e), symbol=data.get("sym"))
            self.stats["errors"] += 1

    async def _handle_luld(self, data: Dict[str, Any]):
        try:
            luld = PolygonLuld(**data)
            self.stats["luld_received"] += 1
            if luld.is_halted:
                self.stats["luld_halts"] += 1
            if luld.is_resuming:
                self.stats["luld_resumes"] += 1
            if self.on_luld:
                await self.on_luld(luld)
        except Exception as e:
            logger.error("luld_processing_error", error=str(e), symbol=data.get("sym"))
            self.stats["errors"] += 1

    # =====================================================================
    # Subscriptions (unchanged public interface)
    # =====================================================================

    async def subscribe_to_tickers(self, tickers: Set[str], event_types: Set[str]):
        if not self.is_authenticated:
            logger.warning("not_authenticated_cannot_subscribe")
            return

        tickers_list = list(tickers)
        BATCH_SIZE = 50

        for i in range(0, len(tickers_list), BATCH_SIZE):
            batch = tickers_list[i:i + BATCH_SIZE]

            subscriptions = []
            for ticker in batch:
                for event_type in event_types:
                    subscriptions.append(f"{event_type}.{ticker}")

            subscribe_message = {
                "action": "subscribe",
                "params": ",".join(subscriptions)
            }

            await self.ws.send(json.dumps(subscribe_message))
            self.subscribed_tickers.update(batch)

            logger.info(
                "subscribed_to_tickers_batch",
                batch_number=i // BATCH_SIZE + 1,
                batch_size=len(batch),
                total_subscriptions=len(subscriptions),
            )

            if i + BATCH_SIZE < len(tickers_list):
                await asyncio.sleep(0.1)

        logger.info(
            "subscribed_to_tickers_complete",
            total_tickers=len(tickers),
            event_types=list(event_types),
            batches_sent=len(tickers_list) // BATCH_SIZE + 1,
        )

    async def unsubscribe_from_tickers(self, tickers: Set[str], event_types: Set[str]):
        if not self.is_authenticated:
            logger.warning("not_authenticated_cannot_unsubscribe")
            return

        tickers_list = list(tickers)
        BATCH_SIZE = 50

        for i in range(0, len(tickers_list), BATCH_SIZE):
            batch = tickers_list[i:i + BATCH_SIZE]

            unsubscriptions = []
            for ticker in batch:
                for event_type in event_types:
                    unsubscriptions.append(f"{event_type}.{ticker}")

            unsubscribe_message = {
                "action": "unsubscribe",
                "params": ",".join(unsubscriptions)
            }

            await self.ws.send(json.dumps(unsubscribe_message))
            self.subscribed_tickers.difference_update(batch)

            logger.info(
                "unsubscribed_from_tickers_batch",
                batch_number=i // BATCH_SIZE + 1,
                batch_size=len(batch),
                total_subscriptions=len(unsubscriptions),
            )

            if i + BATCH_SIZE < len(tickers_list):
                await asyncio.sleep(0.1)

        logger.info(
            "unsubscribed_from_tickers_complete",
            total_tickers=len(tickers),
            event_types=list(event_types),
        )

    async def update_subscriptions(self, new_tickers: Set[str], event_types: Set[str]):
        to_unsubscribe = self.subscribed_tickers - new_tickers
        to_subscribe = new_tickers - self.subscribed_tickers

        if to_unsubscribe:
            await self.unsubscribe_from_tickers(to_unsubscribe, event_types)
        if to_subscribe:
            await self.subscribe_to_tickers(to_subscribe, event_types)

        logger.info(
            "subscriptions_updated",
            unsubscribed=len(to_unsubscribe),
            subscribed=len(to_subscribe),
            total_active=len(self.subscribed_tickers),
        )

    async def subscribe_luld_all(self) -> bool:
        if not self.is_authenticated:
            logger.warning("not_authenticated_cannot_subscribe_luld")
            return False
        try:
            await self.ws.send(json.dumps({"action": "subscribe", "params": "LULD.*"}))
            logger.info("subscribed_to_luld_all_market")
            return True
        except Exception as e:
            logger.error("luld_subscription_failed", error=str(e))
            return False

    async def subscribe_minute_aggs_all(self) -> bool:
        if not self.is_authenticated:
            logger.warning("not_authenticated_cannot_subscribe_am")
            return False
        try:
            await self.ws.send(json.dumps({"action": "subscribe", "params": "AM.*"}))
            logger.info("subscribed_to_am_all_market", channel="AM.*")
            return True
        except Exception as e:
            logger.error("am_subscription_failed", error=str(e))
            return False

    async def unsubscribe_minute_aggs_all(self) -> bool:
        if not self.is_authenticated:
            return False
        try:
            await self.ws.send(json.dumps({"action": "unsubscribe", "params": "AM.*"}))
            logger.info("unsubscribed_from_am_all_market")
            return True
        except Exception as e:
            logger.error("am_unsubscription_failed", error=str(e))
            return False

    async def unsubscribe_luld_all(self) -> bool:
        if not self.is_authenticated:
            logger.warning("not_authenticated_cannot_unsubscribe_luld")
            return False
        try:
            await self.ws.send(json.dumps({"action": "unsubscribe", "params": "LULD.*"}))
            logger.info("unsubscribed_from_luld_all_market")
            return True
        except Exception as e:
            logger.error("luld_unsubscription_failed", error=str(e))
            return False

    # =====================================================================
    # Watchdog
    # =====================================================================

    async def _watchdog(self):
        """Periodically check connection health and log metrics."""
        while True:
            try:
                await asyncio.sleep(WATCHDOG_INTERVAL)
                qsize = self._queue.qsize()
                logger.info(
                    "watchdog",
                    connected=self.is_connected,
                    authenticated=self.is_authenticated,
                    queue_depth=qsize,
                    queue_peak=self.stats["queue_peak"],
                    queue_drops=self.stats["queue_drops"],
                    workers=len(self._worker_tasks),
                    reconnections=self.stats["reconnections"],
                    tickers=len(self.subscribed_tickers),
                )
                if not self.is_connected:
                    logger.warning("watchdog_disconnected", reconnections=self.stats["reconnections"])
            except asyncio.CancelledError:
                return

    # =====================================================================
    # Shutdown
    # =====================================================================

    async def close(self):
        """Graceful shutdown."""
        self._closing = True

        # Cancel watchdog
        if self._watchdog_task:
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except asyncio.CancelledError:
                pass

        # Stop workers
        self._stop_workers()

        # Close WebSocket
        if self.ws and not self.ws.closed:
            await self.ws.close()

        self.is_connected = False
        self.is_authenticated = False
        logger.info("websocket_closed")

    # =====================================================================
    # Stats
    # =====================================================================

    def get_stats(self) -> Dict[str, Any]:
        return {
            **self.stats,
            "is_connected": self.is_connected,
            "is_authenticated": self.is_authenticated,
            "subscribed_tickers_count": len(self.subscribed_tickers),
            "queue_depth": self._queue.qsize(),
            "workers_active": len(self._worker_tasks),
        }
