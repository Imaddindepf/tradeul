"""
Scheduler runtime — T4 "scheduled" workflows: 'every N minutes, capture X'.

Runs periodic snapshot tasks for armed scheduled AlertSpecs and publishes
each capture to the user's alert stream (``stream:alerts:{user_id}``) with
the full ranked table attached, so the Live Workflows canvas shows the
"picture" refreshing in real time (e.g. top after-hours stocks >1B every
minute).

Hydrates from Postgres at startup; the REST arm/pause/archive endpoints
register/unregister specs in-memory afterwards.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Optional

import orjson
import redis.asyncio as aioredis

from alerts.spec import AlertSpec

logger = logging.getLogger(__name__)

TICK_S = 5.0
_SNAPSHOT_FIELDS = ("symbol", "price", "change_percent", "change_pct", "gap_percent",
                    "postmarket_change_percent", "premarket_change_percent",
                    "volume", "rvol", "market_cap", "sector")


def _compact_row(t: dict[str, Any]) -> dict[str, Any]:
    return {k: t.get(k) for k in _SNAPSHOT_FIELDS if t.get(k) is not None}


async def _post_market_fallback(spec: "AlertSpec") -> list[dict[str, Any]]:
    """Top after-hours desde el snapshot enriquecido.

    La categoría post_market del scanner no tiene regla RETE que la alimente,
    así que rankeamos directamente por postmarket_change_percent sobre el
    universo completo (~11K tickers) con los filtros del universe de la spec.
    """
    from agents.mcp_catalog import MCP

    sched = spec.schedule
    filters: list[dict[str, Any]] = [
        {"field": "postmarket_change_percent", "op": "gt", "value": -1000},
        {"field": "volume", "op": "gt", "value": 0},
    ]
    uni = spec.universe
    if uni.min_market_cap is not None:
        filters.append({"field": "market_cap", "op": "gte", "value": uni.min_market_cap})
    if uni.max_market_cap is not None:
        filters.append({"field": "market_cap", "op": "lte", "value": uni.max_market_cap})
    if uni.min_price is not None:
        filters.append({"field": "price", "op": "gte", "value": uni.min_price})
    if uni.max_price is not None:
        filters.append({"field": "price", "op": "lte", "value": uni.max_price})
    if uni.min_rvol is not None:
        filters.append({"field": "rvol", "op": "gte", "value": uni.min_rvol})

    raw = await MCP.scanner.apply_dynamic_filter({
        "filters": filters,
        "sort_by": "postmarket_change_percent",
        "sort_order": "desc",
        "limit": sched.limit if sched else 10,
    })
    if isinstance(raw, dict) and raw.get("error"):
        return []
    return [_compact_row(t) for t in (raw or {}).get("tickers") or []]


async def run_snapshot_task(spec: AlertSpec) -> dict[str, Any]:
    """Execute one snapshot capture for a scheduled spec (also used as preview).

    Returns {"rows": [...], "session": "...", "skipped": bool, "note": str}.
    """
    from agents.mcp_catalog import MCP

    sched = spec.schedule
    if sched is None:
        return {"rows": [], "skipped": True, "note": "spec has no schedule"}

    session = ""
    try:
        s = await MCP.scanner.get_market_session()
        session = (s or {}).get("current_session") or (s or {}).get("session", "")
    except Exception:
        pass
    if sched.sessions and session and session not in sched.sessions:
        return {
            "rows": [], "session": session, "skipped": True,
            "note": f"fuera de ventana ({session}; espera {'/'.join(sched.sessions)})",
        }

    args: dict[str, Any] = {"category": sched.category, "limit": sched.limit}
    uni = spec.universe
    if uni.min_price is not None:
        args["min_price"] = uni.min_price
    if uni.min_rvol is not None:
        args["min_rvol"] = uni.min_rvol
    if uni.min_volume is not None:
        args["min_volume"] = uni.min_volume
    if uni.min_market_cap is not None:
        args["min_market_cap"] = uni.min_market_cap
    if uni.sector:
        args["sector"] = uni.sector

    raw = await MCP.scanner.get_scanner_snapshot(args)
    if isinstance(raw, dict) and raw.get("error"):
        raise RuntimeError(str(raw["error"]))
    tickers = (raw or {}).get("tickers") or []
    rows = [_compact_row(t) for t in tickers[: sched.limit]]

    # La categoría post_market del scanner está vacía (sin regla RETE):
    # rankear after-hours directamente desde el snapshot enriquecido.
    if not rows and sched.category == "post_market":
        rows = await _post_market_fallback(spec)

    return {"rows": rows, "session": session, "skipped": False, "note": ""}


class SchedulerRuntime:
    """Cron-like loop that executes armed scheduled specs on their interval."""

    def __init__(self, redis_url: Optional[str] = None) -> None:
        self._redis_url = redis_url or os.getenv("REDIS_URL", "redis://redis:6379/5")
        self._redis: Optional[aioredis.Redis] = None
        self._running = False
        self._task: Optional[asyncio.Task] = None
        # spec_id -> (spec, next_run_epoch)
        self._specs: dict[str, tuple[AlertSpec, float]] = {}

    # ── lifecycle ────────────────────────────────────────────────

    async def start(self) -> None:
        if self._running:
            return
        self._redis = aioredis.from_url(self._redis_url, decode_responses=False)
        await self._hydrate()
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="scheduler-runtime")
        logger.info("SchedulerRuntime started (%d scheduled specs)", len(self._specs))

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._redis:
            await self._redis.aclose()
            self._redis = None

    async def _hydrate(self) -> None:
        """Load armed scheduled specs from Postgres (all users)."""
        try:
            from alerts.store import get_store
            store = get_store()
            if not store.available:
                return
            rows = await store.list_armed_scheduled()
            for data in rows:
                try:
                    spec = AlertSpec(**data)
                    if spec.is_scheduled_armable():
                        self.register(spec)
                except Exception:
                    logger.warning("scheduler: skipping malformed spec", exc_info=True)
        except Exception:
            logger.exception("scheduler hydration failed")

    # ── registration (called by arm/pause/archive endpoints) ────

    def register(self, spec: AlertSpec) -> None:
        # First run almost immediately so the user sees the workflow alive.
        self._specs[spec.id] = (spec, time.time() + 2)
        logger.info(
            "scheduler: registered '%s' every %ss (category=%s)",
            spec.name, spec.schedule.every_seconds if spec.schedule else "?",
            spec.schedule.category if spec.schedule else "?",
        )

    def unregister(self, spec_id: str) -> bool:
        return self._specs.pop(spec_id, None) is not None

    @property
    def count(self) -> int:
        return len(self._specs)

    # ── loop ─────────────────────────────────────────────────────

    async def _loop(self) -> None:
        while self._running:
            now = time.time()
            due = [s for s, (spec, nxt) in self._specs.items() if nxt <= now]
            for spec_id in due:
                spec, _ = self._specs[spec_id]
                interval = spec.schedule.every_seconds if spec.schedule else 60
                self._specs[spec_id] = (spec, now + interval)
                asyncio.create_task(
                    self._run_one(spec), name=f"sched-{spec_id[:8]}",
                )
            try:
                await asyncio.sleep(TICK_S)
            except asyncio.CancelledError:
                break

    async def _run_one(self, spec: AlertSpec) -> None:
        try:
            result = await run_snapshot_task(spec)
        except Exception as exc:
            logger.warning("scheduler task failed for %s: %s", spec.id, exc)
            return
        if result.get("skipped"):
            return
        rows = result.get("rows") or []
        if not rows:
            # Nothing ranked yet (e.g. post_market just opened) — publishing
            # an empty capture every interval would only add noise.
            logger.debug("scheduler: empty capture for %s, skipping publish", spec.id)
            return
        await self._publish(spec, rows, result.get("session", ""))

    async def _publish(self, spec: AlertSpec, rows: list[dict], session: str) -> None:
        """Push the snapshot to the user's alert stream (canvas + feed relay)."""
        if self._redis is None:
            return
        top = rows[0] if rows else {}
        alert_action = next((a for a in spec.actions if a.channel == "in_app"), None)
        message = (
            (alert_action.message_template if alert_action else None)
            or "{trigger_name}: {n} valores en el snapshot"
        )
        try:
            message = message.format(
                trigger_name=spec.name, n=len(rows),
                symbol=top.get("symbol", ""), price=top.get("price", ""),
            )
        except Exception:
            message = f"{spec.name}: {len(rows)} valores"

        payload = {
            "trigger_id": spec.trigger_id or "",
            "trigger_name": spec.name,
            "user_id": spec.user_id,
            "message": message,
            "symbol": str(top.get("symbol") or ""),
            "event_type": "scheduled_snapshot",
            "price": str(top.get("price") or ""),
            "rvol": str(top.get("rvol") or ""),
            "volume": str(top.get("volume") or ""),
            "spec_id": spec.id,
            "timestamp": str(time.time()),
            "snapshot": orjson.dumps({
                "category": spec.schedule.category if spec.schedule else "",
                "session": session,
                "rows": rows,
            }).decode(),
        }
        try:
            stream_key = f"stream:alerts:{spec.user_id}"
            await self._redis.xadd(stream_key, payload, maxlen=1000)
        except Exception:
            logger.exception("scheduler publish failed for %s", spec.id)
