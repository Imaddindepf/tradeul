"""
Trigger Evaluation Engine

Subscribes to the Redis stream ``stream:alerts:market`` as a consumer,
loads active user triggers from ``triggers:active:{user_id}`` hashes, and
evaluates every inbound market alert against all registered triggers.

When a trigger matches, the engine dispatches the associated action:
  - **workflow** -> invoke the LangGraph orchestrator with trigger context
  - **alert**    -> publish an alert message to ``stream:alerts:{user_id}``
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
import uuid
from datetime import datetime
from typing import Any, Optional

import orjson
import redis.asyncio as aioredis

from triggers.models import TriggerConfig, TriggerEvent

logger = logging.getLogger(__name__)

# Lazy imports inside methods avoid circular deps with alerts package.

# ── Constants ────────────────────────────────────────────────────

STREAM_KEY = "stream:alerts:market"
CONSUMER_GROUP = "trigger-engine"
CONSUMER_NAME = f"engine-{uuid.uuid4().hex[:8]}"
BLOCK_MS = 2000          # xreadgroup block time
BATCH_SIZE = 50          # max events per read
ACTIVE_KEY_PREFIX = "triggers:active"  # triggers:active:{user_id}


def _market_stream_url(base_url: str) -> str:
    """URL of the Redis DB where the alert_engine publishes the market firehose.

    The agent keeps its own state (triggers, user streams, memory) in the DB
    from REDIS_URL (…/5), but stream:alerts:market lives in DB 0 — the
    alert workers publish there (REDIS_DB=0). Override with
    MARKET_STREAM_REDIS_URL if that ever changes.
    """
    override = os.getenv("MARKET_STREAM_REDIS_URL", "").strip()
    if override:
        return override
    return re.sub(r"/\d+$", "/0", base_url)


class TriggerEngine:
    """Reactive trigger evaluation engine backed by Redis Streams."""

    def __init__(self, redis_url: Optional[str] = None) -> None:
        self._redis_url = redis_url or os.getenv("REDIS_URL", "redis://redis:6379/5")
        self._market_redis_url = _market_stream_url(self._redis_url)
        self._redis: Optional[aioredis.Redis] = None
        self._market_redis: Optional[aioredis.Redis] = None
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._membership = None  # MembershipWatcher | None

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

    async def _get_market_redis(self) -> aioredis.Redis:
        """Connection to the DB where the market firehose stream lives."""
        if self._market_redis is None:
            self._market_redis = aioredis.from_url(
                self._market_redis_url,
                decode_responses=False,
            )
        return self._market_redis

    async def start(self) -> None:
        """Start consuming market events from the Redis stream."""
        if self._running:
            logger.warning("TriggerEngine is already running")
            return

        mr = await self._get_market_redis()

        # Ensure the consumer group exists (MKSTREAM creates the stream if
        # needed). Start at "$": only events from now on — replaying a day of
        # firehose backlog on boot would fire stale alerts.
        try:
            await mr.xgroup_create(STREAM_KEY, CONSUMER_GROUP, id="$", mkstream=True)
            logger.info("Created consumer group '%s' on '%s' (db=%s)",
                        CONSUMER_GROUP, STREAM_KEY, self._market_redis_url.rsplit("/", 1)[-1])
        except aioredis.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise
            logger.debug("Consumer group '%s' already exists", CONSUMER_GROUP)

        # Hydrate triggers from Redis
        await self._load_all_triggers()

        self._running = True
        self._task = asyncio.create_task(self._consume_loop(), name="trigger-engine")

        # Membership (scanner enter/exit) runs on its own poll loop
        from alerts.membership import MembershipWatcher
        self._membership = MembershipWatcher(
            redis_url=self._redis_url,
            on_transition=self._on_membership_transition,
        )
        self._sync_membership_watches()
        await self._membership.start()

        logger.info(
            "TriggerEngine started (consumer=%s, triggers_loaded=%d)",
            CONSUMER_NAME,
            sum(len(t) for t in self._triggers.values()),
        )

    async def stop(self) -> None:
        """Gracefully stop the consumer loop."""
        self._running = False
        if self._membership is not None:
            try:
                await self._membership.stop()
            except Exception:
                pass
            self._membership = None
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
        if self._market_redis is not None:
            await self._market_redis.aclose()
            self._market_redis = None

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
        self._sync_membership_watches()
        logger.info(
            "Registered trigger %s for user %s (enabled=%s, kind=%s)",
            config.id, user_id, config.enabled, config.kind,
        )
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
        gone = user_triggers.pop(trigger_id, None)
        if not user_triggers:
            self._triggers.pop(user_id, None)

        # Clear in-flight CEP state for sequence specs
        if gone and gone.sequence_steps and gone.spec_id:
            try:
                from alerts.cep import SequenceRuntime
                r = await self._get_redis()
                n = await SequenceRuntime(r).clear_spec(user_id, gone.spec_id)
                if n:
                    logger.info("Cleared %d CEP states for spec %s", n, gone.spec_id)
            except Exception:
                logger.exception("CEP clear failed for %s", trigger_id)

        # Clear last-price state for price-level specs
        if gone and gone.price_levels and gone.spec_id:
            try:
                from alerts.price_levels import PriceLevelRuntime
                r = await self._get_redis()
                n = await PriceLevelRuntime(r).clear_spec(user_id, gone.spec_id)
                if n:
                    logger.info("Cleared %d price-level states for spec %s", n, gone.spec_id)
            except Exception:
                logger.exception("Price-level clear failed for %s", trigger_id)

        self._sync_membership_watches()
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
        r = await self._get_market_redis()

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
            except aioredis.TimeoutError:
                # redis-py 8.x: blocking XREADGROUP raises on expiry instead
                # of returning empty — normal when the market is quiet.
                continue
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
                            tasks.append(
                                asyncio.create_task(
                                    self._handle_event(trigger, event),
                                    name=f"eval-{trigger.id[:8]}",
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

            # Firehose publishes ISO timestamps ('2026-07-16T15:45:18');
            # synthetic/test events may use epoch floats. Accept both.
            raw_ts = decoded.get("timestamp", "")
            ts: float
            try:
                ts = float(raw_ts)
            except (ValueError, TypeError):
                try:
                    ts = datetime.fromisoformat(raw_ts).timestamp()
                except (ValueError, TypeError):
                    ts = time.time()
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

    def _sync_membership_watches(self) -> None:
        if self._membership is None:
            return
        watches: dict[str, dict[str, Any]] = {}
        for user_triggers in self._triggers.values():
            for tid, cfg in user_triggers.items():
                if cfg.kind == "membership" and cfg.enabled:
                    watches[tid] = cfg.model_dump()
        self._membership.set_watches(watches)

    async def _on_membership_transition(self, payload: dict[str, Any]) -> None:
        """Callback from MembershipWatcher → reuse alert publish path."""
        raw = payload.get("trigger") or {}
        try:
            trigger = TriggerConfig(**raw)
        except Exception:
            logger.exception("Bad membership trigger payload")
            return
        event = TriggerEvent(
            event_id=f"mem-{int(time.time()*1000)}",
            event_type=payload.get("event_type") or "membership",
            symbol=payload.get("symbol") or "",
            price=payload.get("price"),
            volume=None,
            rvol=payload.get("rvol"),
            timestamp=float(payload.get("timestamp") or time.time()),
            raw={"rank": payload.get("rank")},
        )
        if not self._passes_cooldown(trigger):
            return
        await self._dispatch_workflow(trigger, event)

    async def _handle_event(self, trigger: TriggerConfig, event: TriggerEvent) -> None:
        """Route a market event through the right evaluator for this trigger."""
        if not trigger.enabled:
            return
        if trigger.kind == "membership":
            return  # handled by MembershipWatcher poll loop

        if trigger.kind == "price_level" or trigger.price_levels:
            # Price levels update last-price state on EVERY event (even during
            # cooldown) so oscillations around a level aren't re-detected as
            # fresh crosses when the cooldown expires.
            await self._handle_price_level(trigger, event)
            return

        if not self._passes_universe(trigger, event):
            return
        if not self._passes_cooldown(trigger):
            return

        if trigger.sequence_steps:
            await self._handle_sequence(trigger, event)
            return

        # T0 single-event match
        if self._matches_event_types(trigger, event):
            await self._dispatch_workflow(trigger, event)

    async def _handle_price_level(self, trigger: TriggerConfig, event: TriggerEvent) -> None:
        """Absolute price-level crosses (reclaim/breakdown) via PriceLevelRuntime."""
        from alerts.price_levels import PriceLevelRuntime

        if event.price is None:
            return
        # Symbol scoping only — min/max_price universe filters would starve
        # the runtime of the very prices it needs to detect a cross.
        sym = (event.symbol or "").upper()
        include = {s.upper() for s in (trigger.conditions.symbols_include or [])}
        exclude = {s.upper() for s in (trigger.conditions.symbols_exclude or [])}
        if include and sym not in include:
            return
        if exclude and sym in exclude:
            return

        r = await self._get_redis()
        runtime = PriceLevelRuntime(r)
        cross = await runtime.evaluate(
            user_id=trigger.user_id,
            spec_id=trigger.spec_id or trigger.id,
            symbol=sym,
            price=event.price,
            levels=trigger.price_levels,
        )
        if cross is None:
            return
        if not self._passes_cooldown(trigger):
            return
        event.raw = {**(event.raw or {}), "level_cross": cross}
        # Make the fire self-describing regardless of the carrier event type
        event.event_type = (
            f"price_{'reclaim' if cross['direction'] == 'above' else 'breakdown'}_"
            f"{cross['value']:g}"
        )
        await self._dispatch_workflow(trigger, event)

    async def _handle_sequence(self, trigger: TriggerConfig, event: TriggerEvent) -> None:
        from alerts.cep import SequenceRuntime

        # Fast reject: event type must appear in SOME step
        all_types = {
            e.lower()
            for s in trigger.sequence_steps
            for e in (s.get("event_types") or [])
        }
        if event.event_type.lower() not in all_types:
            return

        r = await self._get_redis()
        runtime = SequenceRuntime(r)
        result = await runtime.evaluate(
            user_id=trigger.user_id,
            spec_id=trigger.spec_id or trigger.id,
            steps=trigger.sequence_steps,
            symbol=event.symbol,
            event_type=event.event_type,
            now=event.timestamp,
        )
        if result and result.get("completed"):
            # Attach path evidence onto the event raw payload
            event.raw = {**(event.raw or {}), "sequence_path": result.get("path")}
            await self._dispatch_workflow(trigger, event)

    @staticmethod
    def _passes_cooldown(trigger: TriggerConfig) -> bool:
        if trigger.last_triggered is None:
            return True
        return (time.time() - trigger.last_triggered) >= trigger.cooldown_seconds

    @staticmethod
    def _matches_event_types(trigger: TriggerConfig, event: TriggerEvent) -> bool:
        cond = trigger.conditions
        if not cond.event_types:
            return True
        return event.event_type in cond.event_types

    @staticmethod
    def _passes_universe(trigger: TriggerConfig, event: TriggerEvent) -> bool:
        cond = trigger.conditions
        sym = (event.symbol or "").upper()
        include = {s.upper() for s in (cond.symbols_include or [])}
        exclude = {s.upper() for s in (cond.symbols_exclude or [])}
        if include and sym not in include:
            return False
        if exclude and sym in exclude:
            return False
        if cond.min_price is not None and (event.price is None or event.price < cond.min_price):
            return False
        if cond.max_price is not None and (event.price is None or event.price > cond.max_price):
            return False
        if cond.min_rvol is not None and (event.rvol is None or event.rvol < cond.min_rvol):
            return False
        if cond.min_volume is not None and (event.volume is None or event.volume < cond.min_volume):
            return False
        return True

    @staticmethod
    def _evaluate_trigger(trigger: TriggerConfig, event: TriggerEvent) -> bool:
        """Legacy helper kept for tests: T0 single-event AND of all conditions."""
        if (
            not trigger.enabled
            or trigger.kind in ("membership", "price_level")
            or trigger.sequence_steps
            or trigger.price_levels
        ):
            return False
        eng = TriggerEngine
        return (
            eng._passes_cooldown(trigger)
            and eng._passes_universe(trigger, event)
            and eng._matches_event_types(trigger, event)
        )

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

        # LLM-compiled alerts keep a durable fire history with evidence
        if trigger.spec_id:
            await self._record_spec_fire(trigger, event)

    async def _record_spec_fire(self, trigger: TriggerConfig, event: TriggerEvent) -> None:
        try:
            from alerts.store import get_store

            store = get_store()
            if not store.available:
                return
            evidence: dict[str, Any] = {
                "rvol": event.rvol, "volume": event.volume,
                "timestamp": event.timestamp,
            }
            if (event.raw or {}).get("level_cross"):
                evidence["level_cross"] = event.raw["level_cross"]
            await store.record_fire(
                spec_id=trigger.spec_id,
                user_id=trigger.user_id,
                symbol=event.symbol,
                event_type=event.event_type,
                price=event.price,
                evidence=evidence,
            )
        except Exception:
            logger.exception("Failed to record spec fire for trigger %s", trigger.id)

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
                "user_id": trigger.user_id,
                "query": f"Trigger '{trigger.name}' fired for {event.symbol}",
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

            cross = (event.raw or {}).get("level_cross") or {}
            message = template.format(
                symbol=event.symbol,
                price=event.price or "N/A",
                volume=event.volume or "N/A",
                event_type=event.event_type,
                trigger_name=trigger.name,
                rvol=event.rvol or "N/A",
                rank=(event.raw or {}).get("rank", "N/A"),
                level=cross.get("value", "N/A"),
                direction=cross.get("direction", "N/A"),
            )

            alert_payload = {
                "trigger_id": trigger.id,
                "trigger_name": trigger.name,
                "user_id": trigger.user_id,
                "message": message,
                "symbol": event.symbol,
                "event_type": event.event_type,
                "price": str(event.price or ""),
                "rvol": str(event.rvol or ""),
                "volume": str(event.volume or ""),
                "spec_id": trigger.spec_id or "",
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
