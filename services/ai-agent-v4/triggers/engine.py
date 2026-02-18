"""
Trigger Evaluation Engine

Subscribes to the Redis stream ``stream:events:market`` as a consumer,
loads active user triggers from ``triggers:active:{user_id}`` hashes, and
evaluates every inbound market event against all registered triggers.

When a trigger matches, the engine dispatches the associated action:
  - **workflow** -> invoke the LangGraph orchestrator with trigger context
  - **alert**    -> publish an alert message to ``stream:alerts:{user_id}``
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from typing import Any, Optional

import orjson
import redis.asyncio as aioredis

from triggers.models import TriggerConfig, TriggerEvent

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────

STREAM_KEY = "stream:events:market"
CONSUMER_GROUP = "trigger-engine"
CONSUMER_NAME = f"engine-{uuid.uuid4().hex[:8]}"
BLOCK_MS = 2000          # xreadgroup block time
BATCH_SIZE = 50          # max events per read
ACTIVE_KEY_PREFIX = "triggers:active"  # triggers:active:{user_id}


class TriggerEngine:
    """Reactive trigger evaluation engine backed by Redis Streams."""

    def __init__(self, redis_url: Optional[str] = None) -> None:
        self._redis_url = redis_url or os.getenv("REDIS_URL", "redis://redis:6379/5")
        self._redis: Optional[aioredis.Redis] = None
        self._running = False
        self._task: Optional[asyncio.Task] = None

        # In-memory cache: user_id -> {trigger_id -> TriggerConfig}
        self._triggers: dict[str, dict[str, TriggerConfig]] = {}

    # ── lifecycle ────────────────────────────────────────────────

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(
                self._redis_url,
                decode_responses=False,  # we use orjson
            )
        return self._redis

    async def start(self) -> None:
        """Start consuming market events from the Redis stream."""
        if self._running:
            logger.warning("TriggerEngine is already running")
            return

        r = await self._get_redis()

        # Ensure the consumer group exists (MKSTREAM creates the stream if needed)
        try:
            await r.xgroup_create(STREAM_KEY, CONSUMER_GROUP, id="0", mkstream=True)
            logger.info("Created consumer group '%s' on '%s'", CONSUMER_GROUP, STREAM_KEY)
        except aioredis.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise
            logger.debug("Consumer group '%s' already exists", CONSUMER_GROUP)

        # Hydrate triggers from Redis
        await self._load_all_triggers()

        self._running = True
        self._task = asyncio.create_task(self._consume_loop(), name="trigger-engine")
        logger.info(
            "TriggerEngine started (consumer=%s, triggers_loaded=%d)",
            CONSUMER_NAME,
            sum(len(t) for t in self._triggers.values()),
        )

    async def stop(self) -> None:
        """Gracefully stop the consumer loop."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

        logger.info("TriggerEngine stopped")

    # ── trigger registration ─────────────────────────────────────

    async def register_trigger(self, user_id: str, trigger_config: dict[str, Any]) -> TriggerConfig:
        """Add or update a trigger for a user.

        Persists to Redis **and** updates the in-memory cache.

        Returns:
            The validated TriggerConfig.
        """
        config = TriggerConfig(**trigger_config)
        r = await self._get_redis()

        key = f"{ACTIVE_KEY_PREFIX}:{user_id}"
        await r.hset(key, config.id, orjson.dumps(config.model_dump()))

        # Only cache enabled triggers for evaluation (disabled ones stay in Redis only)
        if config.enabled:
            self._triggers.setdefault(user_id, {})[config.id] = config
        else:
            user_triggers = self._triggers.get(user_id, {})
            user_triggers.pop(config.id, None)
            if not user_triggers and user_id in self._triggers:
                del self._triggers[user_id]
        logger.info("Registered trigger %s for user %s (enabled=%s)", config.id, user_id, config.enabled)
        return config

    async def unregister_trigger(self, user_id: str, trigger_id: str) -> bool:
        """Remove a trigger for a user.

        Returns:
            True if the trigger existed and was removed, False otherwise.
        """
        r = await self._get_redis()
        key = f"{ACTIVE_KEY_PREFIX}:{user_id}"
        removed = await r.hdel(key, trigger_id)

        user_triggers = self._triggers.get(user_id, {})
        user_triggers.pop(trigger_id, None)
        if not user_triggers:
            self._triggers.pop(user_id, None)

        logger.info("Unregistered trigger %s for user %s (existed=%s)", trigger_id, user_id, bool(removed))
        return bool(removed)

    def get_user_triggers(self, user_id: str) -> dict[str, TriggerConfig]:
        """Return the in-memory cache of triggers for a user (public API)."""
        return dict(self._triggers.get(user_id, {}))

    async def get_all_user_triggers_from_redis(self, user_id: str) -> dict[str, dict]:
        """Fetch all triggers for a user directly from Redis (source of truth)."""
        r = await self._get_redis()
        key = f"{ACTIVE_KEY_PREFIX}:{user_id}"
        raw_entries = await r.hgetall(key)
        result: dict[str, dict] = {}
        for _tid, raw in raw_entries.items():
            try:
                data = orjson.loads(raw)
                result[data["id"]] = data
            except Exception:
                logger.warning("Skipping malformed trigger in %s:%s", key, _tid)
        return result

    # ── internal: hydration ──────────────────────────────────────

    async def _load_all_triggers(self) -> None:
        """Scan Redis for all ``triggers:active:*`` hashes and populate cache."""
        r = await self._get_redis()
        cursor: int | bytes = 0
        pattern = f"{ACTIVE_KEY_PREFIX}:*"

        while True:
            cursor, keys = await r.scan(cursor=cursor, match=pattern, count=200)
            for key in keys:
                raw_key = key if isinstance(key, str) else key.decode()
                user_id = raw_key.rsplit(":", 1)[-1]
                entries = await r.hgetall(key)
                user_triggers: dict[str, TriggerConfig] = {}
                for _tid, raw in entries.items():
                    try:
                        data = orjson.loads(raw)
                        cfg = TriggerConfig(**data)
                        if cfg.enabled:
                            user_triggers[cfg.id] = cfg
                    except Exception:
                        logger.warning("Skipping malformed trigger in %s", raw_key, exc_info=True)
                if user_triggers:
                    self._triggers[user_id] = user_triggers

            if cursor == 0:
                break

    # ── internal: consumer loop ──────────────────────────────────

    async def _consume_loop(self) -> None:
        """Main loop: read from the stream and evaluate triggers."""
        r = await self._get_redis()

        while self._running:
            try:
                results = await r.xreadgroup(
                    groupname=CONSUMER_GROUP,
                    consumername=CONSUMER_NAME,
                    streams={STREAM_KEY: ">"},
                    count=BATCH_SIZE,
                    block=BLOCK_MS,
                )
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error reading from stream, retrying in 2s")
                await asyncio.sleep(2)
                continue

            if not results:
                continue

            for _stream_name, messages in results:
                tasks: list[asyncio.Task] = []
                for msg_id, fields in messages:
                    event = self._parse_event(msg_id, fields)
                    if event is None:
                        # ACK and skip unparseable messages
                        await r.xack(STREAM_KEY, CONSUMER_GROUP, msg_id)
                        continue

                    # Evaluate against all triggers concurrently
                    for user_id, user_triggers in self._triggers.items():
                        for trigger in user_triggers.values():
                            if self._evaluate_trigger(trigger, event):
                                tasks.append(
                                    asyncio.create_task(
                                        self._dispatch_workflow(trigger, event),
                                        name=f"dispatch-{trigger.id[:8]}",
                                    )
                                )

                    # ACK the message regardless of dispatch outcome
                    await r.xack(STREAM_KEY, CONSUMER_GROUP, msg_id)

                # Await all dispatches for this batch
                if tasks:
                    results_done = await asyncio.gather(*tasks, return_exceptions=True)
                    for i, result in enumerate(results_done):
                        if isinstance(result, Exception):
                            logger.error("Dispatch task %d failed: %s", i, result)

    # ── internal: parsing ────────────────────────────────────────

    @staticmethod
    def _parse_event(msg_id: bytes | str, fields: dict) -> Optional[TriggerEvent]:
        """Parse a raw Redis stream entry into a TriggerEvent."""
        try:
            # Fields may be bytes or str depending on decode_responses
            decoded: dict[str, Any] = {}
            for k, v in fields.items():
                key_str = k.decode() if isinstance(k, bytes) else k
                val_str = v.decode() if isinstance(v, bytes) else v
                decoded[key_str] = val_str

            # Try to parse numeric fields
            price = None
            if "price" in decoded:
                try:
                    price = float(decoded["price"])
                except (ValueError, TypeError):
                    pass

            volume = None
            if "volume" in decoded:
                try:
                    volume = int(decoded["volume"])
                except (ValueError, TypeError):
                    pass

            rvol = None
            if "rvol" in decoded:
                try:
                    rvol = float(decoded["rvol"])
                except (ValueError, TypeError):
                    pass

            ts = float(decoded.get("timestamp", time.time()))
            msg_id_str = msg_id.decode() if isinstance(msg_id, bytes) else msg_id

            return TriggerEvent(
                event_id=msg_id_str,
                event_type=decoded.get("event_type", "unknown"),
                symbol=decoded.get("symbol", ""),
                price=price,
                volume=volume,
                rvol=rvol,
                timestamp=ts,
                raw=decoded,
            )
        except Exception:
            logger.warning("Failed to parse stream event %s", msg_id, exc_info=True)
            return None

    # ── internal: evaluation ─────────────────────────────────────

    @staticmethod
    def _evaluate_trigger(trigger: TriggerConfig, event: TriggerEvent) -> bool:
        """Check whether *event* satisfies *trigger* conditions.

        All conditions are ANDed.  Returns True if the trigger should fire.
        """
        if not trigger.enabled:
            return False

        # Cooldown check
        if trigger.last_triggered is not None:
            elapsed = time.time() - trigger.last_triggered
            if elapsed < trigger.cooldown_seconds:
                return False

        cond = trigger.conditions

        # Event type filter
        if cond.event_types and event.event_type not in cond.event_types:
            return False

        # Symbol include filter
        if cond.symbols_include and event.symbol not in cond.symbols_include:
            return False

        # Symbol exclude filter
        if cond.symbols_exclude and event.symbol in cond.symbols_exclude:
            return False

        # Price filters
        if cond.min_price is not None and (event.price is None or event.price < cond.min_price):
            return False
        if cond.max_price is not None and (event.price is None or event.price > cond.max_price):
            return False

        # Relative volume filter
        if cond.min_rvol is not None and (event.rvol is None or event.rvol < cond.min_rvol):
            return False

        # Absolute volume filter
        if cond.min_volume is not None and (event.volume is None or event.volume < cond.min_volume):
            return False

        return True

    # ── internal: dispatch ───────────────────────────────────────

    async def _dispatch_workflow(self, trigger: TriggerConfig, event: TriggerEvent) -> None:
        """Dispatch the trigger action (workflow invoke or alert publish)."""
        now = time.time()

        # Update cooldown timestamp in-memory and in Redis
        trigger.last_triggered = now
        r = await self._get_redis()
        key = f"{ACTIVE_KEY_PREFIX}:{trigger.user_id}"
        await r.hset(key, trigger.id, orjson.dumps(trigger.model_dump()))

        if trigger.action.type == "workflow":
            await self._invoke_workflow(trigger, event)
        elif trigger.action.type == "alert":
            await self._publish_alert(trigger, event)
        else:
            logger.warning("Unknown action type '%s' for trigger %s", trigger.action.type, trigger.id)

    async def _invoke_workflow(self, trigger: TriggerConfig, event: TriggerEvent) -> None:
        """Invoke the LangGraph orchestrator with trigger context."""
        try:
            from graph.orchestrator import get_graph

            graph = get_graph()
            thread_id = f"trigger-{trigger.id}-{int(time.time() * 1000)}"

            initial_state: dict[str, Any] = {
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            f"Reactive trigger fired: {trigger.name}. "
                            f"Event: {event.event_type} for {event.symbol} "
                            f"at ${event.price}."
                        ),
                    }
                ],
                "query": f"Trigger '{trigger.name}' fired for {event.symbol}",
                "language": "en",
                "mode": "auto",
                "tickers": [],
                "plan": "",
                "active_agents": [],
                "agent_results": {},
                "charts": [],
                "tables": [],
                "market_context": {
                    "symbol": event.symbol,
                    "price": event.price,
                    "volume": event.volume,
                    "rvol": event.rvol,
                    "event_type": event.event_type,
                },
                "memory_context": [],
                "workflow_id": trigger.action.workflow_id,
                "trigger_context": {
                    "trigger_id": trigger.id,
                    "trigger_name": trigger.name,
                    "event": event.model_dump(),
                },
                "node_config": None,
                "final_response": "",
                "execution_metadata": {},
                "clarification": None,
                "clarification_hint": "",
                "error": None,
            }

            config = {"configurable": {"thread_id": thread_id}}
            await graph.ainvoke(initial_state, config=config)

            logger.info(
                "Workflow dispatched for trigger %s (event=%s, symbol=%s, thread=%s)",
                trigger.id, event.event_type, event.symbol, thread_id,
            )
        except Exception:
            logger.exception("Failed to invoke workflow for trigger %s", trigger.id)

    async def _publish_alert(self, trigger: TriggerConfig, event: TriggerEvent) -> None:
        """Publish an alert message to the user's alert stream."""
        try:
            r = await self._get_redis()
            template = trigger.action.message_template or (
                "{symbol} triggered '{trigger_name}' ({event_type}) at ${price}"
            )

            message = template.format(
                symbol=event.symbol,
                price=event.price or "N/A",
                volume=event.volume or "N/A",
                event_type=event.event_type,
                trigger_name=trigger.name,
                rvol=event.rvol or "N/A",
            )

            alert_payload = {
                "trigger_id": trigger.id,
                "trigger_name": trigger.name,
                "user_id": trigger.user_id,
                "message": message,
                "symbol": event.symbol,
                "event_type": event.event_type,
                "price": str(event.price or ""),
                "timestamp": str(time.time()),
            }

            stream_key = f"stream:alerts:{trigger.user_id}"
            await r.xadd(stream_key, alert_payload, maxlen=1000)

            logger.info(
                "Alert published for trigger %s (user=%s, symbol=%s)",
                trigger.id, trigger.user_id, event.symbol,
            )
        except Exception:
            logger.exception("Failed to publish alert for trigger %s", trigger.id)
