"""
Lightweight CEP (Complex Event Processing) for AlertSpec sequences.

State machine per (user, spec, symbol):
  step_idx=0 → waiting for steps[0]
  step_idx=k → waiting for steps[k], started at `since`

Redis key: alert_seq:{user_id}:{spec_id}:{symbol}
TTL: max within_minutes across remaining steps (default 1 trading day).

Evaluated by TriggerEngine for armed sequence-tier specs (no day_conditions).
Day-level filters still need end-of-day context — those stay dry-run only.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

import orjson

logger = logging.getLogger(__name__)

KEY_PREFIX = "alert_seq"
DEFAULT_WINDOW_S = 6 * 3600  # session-length fallback


def _key(user_id: str, spec_id: str, symbol: str) -> str:
    return f"{KEY_PREFIX}:{user_id}:{spec_id}:{symbol.upper()}"


class SequenceRuntime:
    """Per-symbol NFA advancement for multi-step AlertSpecs."""

    def __init__(self, redis) -> None:
        self._r = redis

    async def evaluate(
        self,
        *,
        user_id: str,
        spec_id: str,
        steps: list[dict[str, Any]],
        symbol: str,
        event_type: str,
        now: Optional[float] = None,
    ) -> Optional[dict[str, Any]]:
        """Feed one market event into the automaton.

        Returns a fire payload when the FULL sequence completes, else None.
        """
        if not steps:
            return None
        now = now or time.time()
        symbol = symbol.upper()
        key = _key(user_id, spec_id, symbol)

        raw = await self._r.get(key)
        state: dict[str, Any]
        if raw:
            try:
                state = orjson.loads(raw)
            except Exception:
                state = {"step_idx": 0, "since": now, "path": []}
        else:
            state = {"step_idx": 0, "since": now, "path": []}

        idx = int(state.get("step_idx", 0))
        if idx >= len(steps):
            idx = 0
            state = {"step_idx": 0, "since": now, "path": []}

        step = steps[idx]
        wanted = {e.lower() for e in (step.get("event_types") or [])}
        if event_type.lower() not in wanted:
            # Stale window? expire waiting state
            within = step.get("within_minutes")
            if idx > 0 and within and (now - float(state.get("since", now))) > within * 60:
                await self._r.delete(key)
            return None

        # within_minutes only applies after the first step
        if idx > 0:
            within = step.get("within_minutes")
            since = float(state.get("since", now))
            if within is not None and (now - since) > within * 60:
                # Window expired — restart if this event matches step 0
                await self._r.delete(key)
                if 0 < len(steps) and event_type.lower() in {
                    e.lower() for e in (steps[0].get("event_types") or [])
                }:
                    return await self.evaluate(
                        user_id=user_id, spec_id=spec_id, steps=steps,
                        symbol=symbol, event_type=event_type, now=now,
                    )
                return None

        path = list(state.get("path") or [])
        path.append({"event_type": event_type, "ts": now, "step": idx})
        next_idx = idx + 1

        if next_idx >= len(steps):
            # Sequence complete
            await self._r.delete(key)
            return {
                "completed": True,
                "path": path,
                "symbol": symbol,
                "steps_matched": len(path),
            }

        # Advance
        ttl = DEFAULT_WINDOW_S
        nxt = steps[next_idx]
        if nxt.get("within_minutes"):
            ttl = max(int(nxt["within_minutes"]) * 60 + 60, 120)
        new_state = {"step_idx": next_idx, "since": now, "path": path}
        await self._r.set(key, orjson.dumps(new_state), ex=ttl)
        return None

    async def clear_spec(self, user_id: str, spec_id: str) -> int:
        """Drop all in-flight sequence state for a spec (on pause/archive)."""
        pattern = f"{KEY_PREFIX}:{user_id}:{spec_id}:*"
        n = 0
        cursor = 0
        while True:
            cursor, keys = await self._r.scan(cursor=cursor, match=pattern, count=200)
            if keys:
                n += await self._r.delete(*keys)
            if cursor == 0:
                break
        return n
