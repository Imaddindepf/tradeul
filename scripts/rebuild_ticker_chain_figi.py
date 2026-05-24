#!/usr/bin/env python3
"""
Rebuild Ticker Chain (FIGI-validated)
=====================================

Standalone script to atomically rebuild the Redis hash `ticker:chain` using
the new FIGI-validated logic in
`services/data_maintenance/tasks/build_ticker_chain.py`.

This is the same task that runs weekly inside `tradeul_data_maintenance`,
but executable from the host so we don't need to rebuild/restart the
container during market hours.

Usage:
    REDIS_PASSWORD=... POLYGON_API_KEY=... \\
        python3 /opt/tradeul/scripts/rebuild_ticker_chain_figi.py [--dry-run]

The script:
1. Loads `BuildTickerChainTask` from the repo (no container required).
2. Fetches all active US stock tickers from Polygon (~12k).
3. For each ticker fetches ticker_change events.
4. Validates each predecessor via historical composite_figi.
5. Atomically replaces `ticker:chain` in Redis (single transaction).

Set --dry-run to print a diff against the existing hash without writing.
"""

import argparse
import asyncio
import importlib.util
import logging
import os
import sys
import types
from typing import Dict, List

import httpx
import orjson
import redis.asyncio as aioredis

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOB_PATH = os.path.join(REPO_ROOT, "services/data_maintenance/tasks/build_ticker_chain.py")
HASH_KEY = "ticker:chain"


def _install_shared_stubs() -> None:
    """Stub the few `shared.utils` modules the job imports at module load."""
    shared = types.ModuleType("shared"); shared.utils = types.ModuleType("shared.utils")
    sys.modules.setdefault("shared", shared)
    sys.modules.setdefault("shared.utils", shared.utils)

    rc = types.ModuleType("shared.utils.redis_client")
    rc.RedisClient = type("RedisClient", (), {})
    sys.modules.setdefault("shared.utils.redis_client", rc)

    tc = types.ModuleType("shared.utils.timescale_client")
    tc.TimescaleClient = type("TimescaleClient", (), {})
    sys.modules.setdefault("shared.utils.timescale_client", tc)

    lg = types.ModuleType("shared.utils.logger")

    def get_logger(name: str):
        base = logging.getLogger(name)

        class W:
            def info(self, m, **k):
                base.info("%s %s", m, k)

            def warning(self, m, **k):
                base.warning("%s %s", m, k)

            def debug(self, m, **k):
                base.debug("%s %s", m, k)

            def error(self, m, **k):
                base.error("%s %s", m, k)

        return W()

    lg.get_logger = get_logger
    sys.modules.setdefault("shared.utils.logger", lg)


def _load_task_class():
    _install_shared_stubs()
    spec = importlib.util.spec_from_file_location("build_ticker_chain_figi", JOB_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.BuildTickerChainTask


async def _connect_redis() -> aioredis.Redis:
    pw = os.environ.get("REDIS_PASSWORD")
    url = (
        f"redis://:{pw}@localhost:6379/0" if pw else "redis://localhost:6379/0"
    )
    r = aioredis.from_url(url, decode_responses=True)
    await r.ping()
    return r


async def _rebuild(dry_run: bool) -> None:
    if not os.environ.get("POLYGON_API_KEY"):
        # The repo file has a default key embedded — let it use that.
        pass

    Task = _load_task_class()
    task = Task(redis_client=None)

    print("=" * 60)
    print("REBUILD ticker:chain WITH FIGI VALIDATION")
    print("=" * 60)
    print(f"Dry run: {dry_run}")
    print()

    async with httpx.AsyncClient(timeout=30.0) as client:
        print("[1/3] Fetching active US tickers from Polygon...")
        tickers = await task._fetch_all_tickers(client)
        print(f"      → {len(tickers)} active tickers")

        print("[2/3] Scanning ticker_change events and validating with composite_figi...")
        chains: Dict[str, List[str]] = await task._scan_all_events(client, tickers)
        print(f"      → {len(chains)} validated chains")

    r = await _connect_redis()
    before = await r.hgetall(HASH_KEY)
    before_count = len(before)

    # Build the new hash. A ticker can appear in multiple chains (it can be
    # the CURRENT of one chain and a PREDECESSOR of another, e.g. META is the
    # current of [FB, META] *and* a predecessor in [META, METV] — the ETF
    # Roundhill used to trade as META before Facebook renamed itself).
    # When that happens, the "current" claim wins: a user typing META wants
    # the active instrument, not a legacy lookup.
    new_hash: Dict[str, str] = {}
    # Pass 1: assign each ticker that is the CURRENT (chain[-1]) of a chain.
    for sym, chain in chains.items():
        if chain and chain[-1].upper() == str(sym).upper():
            new_hash[str(sym).upper()] = orjson.dumps(chain).decode()
    # Pass 2: assign predecessors only if the symbol hasn't been claimed as a
    # current already. This preserves legacy lookups (FB -> [FB, META]) without
    # overwriting current tickers (META keeps [FB, META]).
    for sym, chain in chains.items():
        if not chain:
            continue
        encoded = orjson.dumps(chain).decode()
        for old in chain[:-1]:
            key = str(old).upper()
            if key not in new_hash:
                new_hash[key] = encoded
    new_count = len(new_hash)

    print()
    print("[3/3] Diff against current Redis state:")
    print(f"      current entries:    {before_count}")
    print(f"      next entries:       {new_count}")

    removed = set(before.keys()) - set(new_hash.keys())
    added = set(new_hash.keys()) - set(before.keys())
    changed = {
        k: (before[k], new_hash[k])
        for k in (set(before.keys()) & set(new_hash.keys()))
        if before[k] != new_hash[k]
    }
    print(f"      will REMOVE keys:   {len(removed)}")
    print(f"      will ADD keys:      {len(added)}")
    print(f"      will UPDATE keys:   {len(changed)}")

    # Show samples for human review.
    print()
    print("Sample REMOVED (was in Redis, no longer valid):")
    for k in list(removed)[:15]:
        print(f"  {k:10s} was={before[k]}")
    print()
    print("Sample ADDED (new validated chain):")
    for k in list(added)[:15]:
        print(f"  {k:10s} new={new_hash[k]}")
    print()
    print("Sample UPDATED:")
    for k, (b, n) in list(changed.items())[:15]:
        print(f"  {k:10s} {b} -> {n}")

    print()
    print("Key tickers preview:")
    for sym in ["META", "FB", "METV", "DJT", "DWAC", "SBFM", "SBFMW", "NEP", "AAPL", "NVDA", "ERTS", "EA", "NLOK", "GEN"]:
        bv = before.get(sym)
        nv = new_hash.get(sym)
        marker = "=" if bv == nv else "→"
        print(f"  {sym:8s} {bv!r}  {marker}  {nv!r}")

    if dry_run:
        print()
        print("--dry-run: NOT writing to Redis.")
        await r.aclose()
        return

    print()
    print("Applying changes atomically to Redis...")
    async with r.pipeline(transaction=True) as pipe:
        pipe.delete(HASH_KEY)
        if new_hash:
            # HSET accepts a mapping argument; one call per chunk is fine but
            # a single mapping is atomic within the transaction either way.
            pipe.hset(HASH_KEY, mapping=new_hash)
        # Also bump the maintenance timestamp.
        from datetime import date as _date
        pipe.set("maintenance:last_ticker_chain_build", _date.today().isoformat(), ex=86400 * 30)
        await pipe.execute()

    after_count = await r.hlen(HASH_KEY)
    print(f"Done. ticker:chain has {after_count} entries.")
    await r.aclose()


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="Do not write to Redis")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(_rebuild(dry_run=args.dry_run))
