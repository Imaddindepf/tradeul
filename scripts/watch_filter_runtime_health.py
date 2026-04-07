#!/usr/bin/env python3
"""
Runtime health checker for event filters.

What it does:
- Reads the shared filter catalog (single source of truth)
- Maps filter data keys to enriched snapshot field keys
- Computes non-null coverage for each field in snapshot:enriched:latest
- Prints healthy/low/zero groups
- Optional watch mode for real-time monitoring

Usage examples:
  python3 scripts/watch_filter_runtime_health.py
  python3 scripts/watch_filter_runtime_health.py --watch --interval 5
  python3 scripts/watch_filter_runtime_health.py --low-threshold 60
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple

import redis


ROOT = Path("/opt/tradeul")
CATALOG_PATH = ROOT / "shared/config/event_filter_catalog.json"
SNAPSHOT_KEY = "snapshot:enriched:latest"
META_FIELD = "__meta__"


def derive_snapshot_fields(catalog: dict) -> Set[str]:
    fields: Set[str] = set()

    for row in catalog.get("numeric", []):
        data_key = row["dataKey"]
        if data_key in ("change_min", "change_max"):
            fields.add("change_percent")
        elif data_key.endswith("_min"):
            fields.add(data_key[:-4])
        elif data_key.endswith("_max"):
            fields.add(data_key[:-4])
        else:
            fields.add(data_key)

    for row in catalog.get("string", []):
        fields.add(row["dataKey"])

    return fields


def pct(numerator: int, denominator: int) -> float:
    return (numerator / denominator * 100.0) if denominator else 0.0


def load_snapshot_rows(r: redis.Redis) -> List[dict]:
    raw = r.hgetall(SNAPSHOT_KEY)
    raw.pop(META_FIELD, None)
    rows: List[dict] = []
    for payload in raw.values():
        try:
            rows.append(json.loads(payload))
        except Exception:
            continue
    return rows


def coverage_for_fields(rows: List[dict], fields: Iterable[str]) -> Dict[str, int]:
    def candidates_for_key(key: str) -> List[str]:
        # Runtime compatibility aliases used by websocket filtering logic.
        cands = [key]
        if key == "change_percent":
            cands.extend(["change_pct", "change"])
        if key == "rsi":
            cands.append("rsi_14")
        if key.startswith("rsi_") and key.endswith("m"):
            # Catalog uses rsi_2m/rsi_5m..., runtime currently emits rsi_14_2m/rsi_14_5m...
            cands.append(key.replace("rsi_", "rsi_14_", 1))
        return cands

    counts: Dict[str, int] = {}
    for key in fields:
        non_null = 0
        candidates = candidates_for_key(key)
        for row in rows:
            value = None
            for cand in candidates:
                value = row.get(cand)
                if value is not None:
                    break
            if value is not None:
                non_null += 1
        counts[key] = non_null
    return counts


def print_report(
    rows: List[dict],
    fields: Set[str],
    counts: Dict[str, int],
    low_threshold: float,
) -> None:
    def get_count(key: str) -> int:
        if key in counts:
            return counts[key]
        # Reverse compatibility for runtime-only keys used in summary output.
        if key == "rsi_14_2m":
            return counts.get("rsi_2m", 0)
        if key == "rsi_14_5m":
            return counts.get("rsi_5m", 0)
        if key == "rsi_14_15m":
            return counts.get("rsi_15m", 0)
        if key == "rsi_14_60m":
            return counts.get("rsi_60m", 0)
        if key == "rsi_14":
            return counts.get("rsi", 0)
        return 0

    total = len(rows)
    zero: List[Tuple[str, int, float]] = []
    low: List[Tuple[str, int, float]] = []
    healthy: List[Tuple[str, int, float]] = []

    for key in sorted(fields):
        c = counts.get(key, 0)
        p = pct(c, total)
        item = (key, c, p)
        if c == 0:
            zero.append(item)
        elif p < low_threshold:
            low.append(item)
        else:
            healthy.append(item)

    print("=" * 88)
    print(f"snapshot_symbols={total} | catalog_fields={len(fields)} | low_threshold={low_threshold:.1f}%")
    print(
        f"healthy={len(healthy)} | low={len(low)} | zero={len(zero)}"
    )

    def print_group(title: str, items: List[Tuple[str, int, float]], limit: int = 40) -> None:
        print(f"\n[{title}]")
        if not items:
            print("  (none)")
            return
        for key, c, p in items[:limit]:
            print(f"  {key}: {c}/{total} ({p:.1f}%)")
        if len(items) > limit:
            print(f"  ... +{len(items) - limit} more")

    # Show lowest first in "low"
    low.sort(key=lambda x: x[1])

    print_group("ZERO_COVERAGE", zero, limit=80)
    print_group("LOW_COVERAGE", low, limit=80)

    # Key families that usually matter for event strategies
    families = {
        "chg_dollars": [f"chg_{m}min_dollars" for m in (1, 2, 5, 10, 15, 30, 60, 120)],
        "chg_percent": [f"chg_{m}min" for m in (1, 2, 5, 10, 15, 30, 60, 120)],
        "vol_pct": [f"vol_{m}min_pct" for m in (1, 5, 10, 15, 30)],
        "rsi_tf": ["rsi_14_2m", "rsi_14_5m", "rsi_14_15m", "rsi_14_60m"],
        "consecutive_tf": [
            "consecutive_candles",
            "consecutive_candles_2m",
            "consecutive_candles_5m",
            "consecutive_candles_10m",
            "consecutive_candles_15m",
            "consecutive_candles_30m",
            "consecutive_candles_60m",
        ],
    }

    print("\n[FAMILY_SUMMARY]")
    for name, keys in families.items():
        print(f"  {name}:")
        for key in keys:
            c = get_count(key)
            print(f"    {key}: {c}/{total} ({pct(c, total):.1f}%)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Real-time runtime health checker for event filters")
    parser.add_argument("--redis-host", default=os.getenv("REDIS_HOST", "localhost"))
    parser.add_argument("--redis-port", type=int, default=int(os.getenv("REDIS_PORT", "6379")))
    parser.add_argument("--redis-db", type=int, default=int(os.getenv("REDIS_DB", "0")))
    parser.add_argument("--redis-password", default=os.getenv("REDIS_PASSWORD", "tradeul_redis_secure_2024"))
    parser.add_argument("--interval", type=float, default=5.0, help="Watch interval in seconds")
    parser.add_argument("--watch", action="store_true", help="Keep running and refresh report")
    parser.add_argument("--low-threshold", type=float, default=50.0, help="Percent below which a field is LOW")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not CATALOG_PATH.exists():
        print(f"ERROR: catalog not found: {CATALOG_PATH}")
        return 1

    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    fields = derive_snapshot_fields(catalog)

    try:
        r = redis.Redis(
            host=args.redis_host,
            port=args.redis_port,
            db=args.redis_db,
            password=args.redis_password,
            decode_responses=True,
            socket_timeout=5,
        )
        r.ping()
    except Exception as exc:
        print(f"ERROR: redis connection failed: {exc}")
        return 2

    while True:
        rows = load_snapshot_rows(r)
        counts = coverage_for_fields(rows, fields)
        print_report(rows, fields, counts, args.low_threshold)
        if not args.watch:
            break
        time.sleep(args.interval)

    return 0


if __name__ == "__main__":
    sys.exit(main())
