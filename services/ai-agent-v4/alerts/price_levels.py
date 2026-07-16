"""
Price-level cross runtime — "avísame cuando AMD reclame 502 o pierda 500".

The firehose publishes a constant stream of events per liquid symbol, each
carrying the current price. This runtime keeps the last observed price per
(user, spec, symbol) in Redis and detects true CROSSES through absolute
levels — not just "price is above X" — so an alert armed while AMD already
trades at 503 does not fire immediately.

Semantics:
  direction=above : fires when last < value and now >= value  (reclaim)
  direction=below : fires when last > value and now <= value  (breakdown)
Multiple levels on one spec are OR'ed; each cross reports which level hit.

The first observation after arming only seeds the state (no fire), which is
exactly the hysteresis a trader expects from a level alert.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

_STATE_PREFIX = "alerts:pl"          # alerts:pl:{user_id}:{spec_id}:{symbol}
_STATE_TTL = 172800                  # 2 days — dead state self-cleans


class PriceLevelRuntime:
    """Stateful cross detection over Redis for price-level alerts."""

    def __init__(self, redis: aioredis.Redis) -> None:
        self._redis = redis

    @staticmethod
    def _key(user_id: str, spec_id: str, symbol: str) -> str:
        return f"{_STATE_PREFIX}:{user_id}:{spec_id}:{symbol.upper()}"

    async def evaluate(
        self,
        user_id: str,
        spec_id: str,
        symbol: str,
        price: float,
        levels: list[dict[str, Any]],
    ) -> Optional[dict[str, Any]]:
        """Update last-price state and return the first level crossed, if any.

        Args:
            levels: [{"direction": "above"|"below", "value": float}, ...]

        Returns:
            {"direction", "value", "from_price", "to_price"} on a cross,
            None otherwise. State is ALWAYS updated (even during cooldown the
            caller must keep feeding prices, or oscillations around a level
            would be re-detected as fresh crosses).
        """
        key = self._key(user_id, spec_id, symbol)
        # SET ... GET: atomically store the new price and read the previous one
        raw = await self._redis.set(key, str(price), get=True, ex=_STATE_TTL)

        if raw is None:
            return None  # first observation: seed only
        try:
            last = float(raw if isinstance(raw, str) else raw.decode())
        except (ValueError, AttributeError):
            return None

        for lvl in levels:
            try:
                value = float(lvl["value"])
                direction = lvl["direction"]
            except (KeyError, TypeError, ValueError):
                continue
            crossed = (
                (direction == "above" and last < value <= price)
                or (direction == "below" and last > value >= price)
            )
            if crossed:
                return {
                    "direction": direction,
                    "value": value,
                    "from_price": last,
                    "to_price": price,
                }
        return None

    async def clear_spec(self, user_id: str, spec_id: str) -> int:
        """Drop all per-symbol state for a spec (on pause/archive)."""
        pattern = f"{_STATE_PREFIX}:{user_id}:{spec_id}:*"
        removed = 0
        cursor: int = 0
        while True:
            cursor, keys = await self._redis.scan(cursor=cursor, match=pattern, count=100)
            if keys:
                removed += await self._redis.delete(*keys)
            if cursor == 0:
                break
        return removed
