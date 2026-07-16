"""
Membership watcher — fire when a symbol ENTERS or EXITS a scanner category.

Polls the scanner service for each armed membership AlertSpec, diffs the
ranked set against the previous snapshot, and publishes user alerts for
transitions (optionally filtered by rank_lte).
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Callable, Awaitable, Optional

import httpx
import orjson
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

POLL_S = 12.0
STATE_KEY = "alerts:membership:prev"  # hash: {spec_id} -> JSON list of symbols


class MembershipWatcher:
    def __init__(
        self,
        *,
        redis_url: str,
        on_transition: Callable[[dict[str, Any]], Awaitable[None]],
        scanner_url: Optional[str] = None,
    ) -> None:
        self._redis_url = redis_url
        self._scanner_url = (
            scanner_url
            or os.getenv("SCANNER_URL", "http://scanner:8003")
        ).rstrip("/")
        self._on_transition = on_transition
        self._redis: Optional[aioredis.Redis] = None
        self._running = False
        self._task: Optional[asyncio.Task] = None
        # In-memory: spec_id -> TriggerConfig-like dict
        self._watches: dict[str, dict[str, Any]] = {}

    def set_watches(self, watches: dict[str, dict[str, Any]]) -> None:
        """Replace the set of armed membership watches (keyed by trigger id)."""
        self._watches = {
            tid: w for tid, w in watches.items()
            if w.get("kind") == "membership" and w.get("membership")
        }

    async def start(self) -> None:
        if self._running:
            return
        self._redis = aioredis.from_url(self._redis_url, decode_responses=False)
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="membership-watcher")
        logger.info("MembershipWatcher started (poll=%.0fs)", POLL_S)

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

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("MembershipWatcher tick failed")
            await asyncio.sleep(POLL_S)

    async def _fetch_category(self, category: str, limit: int = 50) -> list[dict]:
        url = f"{self._scanner_url}/api/categories/{category}"
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(url, params={"limit": limit})
                resp.raise_for_status()
                data = resp.json()
            return data.get("tickers") or []
        except Exception as exc:
            logger.warning("membership fetch %s failed: %s", category, exc)
            return []

    async def _tick(self) -> None:
        if not self._watches or not self._redis:
            return
        # Group by category to avoid N identical HTTP calls
        by_cat: dict[str, list[tuple[str, dict]]] = {}
        for tid, watch in self._watches.items():
            cat = (watch.get("membership") or {}).get("category")
            if cat:
                by_cat.setdefault(cat, []).append((tid, watch))

        for category, items in by_cat.items():
            tickers = await self._fetch_category(category, limit=80)
            ranked = [(i + 1, t) for i, t in enumerate(tickers)]
            for tid, watch in items:
                await self._diff_one(tid, watch, ranked)

    async def _diff_one(
        self, tid: str, watch: dict, ranked: list[tuple[int, dict]],
    ) -> None:
        mem = watch.get("membership") or {}
        on = mem.get("on", "enter")
        rank_lte = mem.get("rank_lte")
        cond = watch.get("conditions") or {}

        current: dict[str, dict] = {}
        for rank, t in ranked:
            sym = (t.get("symbol") or "").upper()
            if not sym:
                continue
            if rank_lte is not None and rank > int(rank_lte):
                continue
            # Universe filters (price / rvol)
            price = t.get("price")
            rvol = t.get("rvol")
            if cond.get("min_price") is not None and (price is None or price < cond["min_price"]):
                continue
            if cond.get("max_price") is not None and (price is None or price > cond["max_price"]):
                continue
            if cond.get("min_rvol") is not None and (rvol is None or rvol < cond["min_rvol"]):
                continue
            include = [s.upper() for s in (cond.get("symbols_include") or [])]
            exclude = [s.upper() for s in (cond.get("symbols_exclude") or [])]
            if include and sym not in include:
                continue
            if sym in exclude:
                continue
            current[sym] = {"rank": rank, "price": price, "rvol": rvol, **{k: t.get(k) for k in ("change_percent", "gap_percent")}}

        spec_id = watch.get("spec_id") or tid
        prev_raw = await self._redis.hget(STATE_KEY, spec_id)
        prev_syms: set[str] = set()
        if prev_raw:
            try:
                prev_syms = set(orjson.loads(prev_raw))
            except Exception:
                prev_syms = set()

        cur_syms = set(current)
        # First observation: seed state, don't fire a storm of "enters"
        if not prev_syms and cur_syms:
            await self._redis.hset(STATE_KEY, spec_id, orjson.dumps(sorted(cur_syms)))
            return

        entered = cur_syms - prev_syms
        exited = prev_syms - cur_syms
        await self._redis.hset(STATE_KEY, spec_id, orjson.dumps(sorted(cur_syms)))

        targets = entered if on == "enter" else exited
        for sym in targets:
            meta = current.get(sym) or {}
            await self._on_transition({
                "trigger": watch,
                "symbol": sym,
                "event_type": f"membership_{on}_{mem.get('category', 'unknown')}",
                "price": meta.get("price"),
                "rvol": meta.get("rvol"),
                "rank": meta.get("rank"),
                "timestamp": time.time(),
            })
