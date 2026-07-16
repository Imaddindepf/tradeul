"""
Dry-run — "when would this alert have fired?"

Replays an AlertSpec against the real market_events history (60-day
retention, 240+ event types) via strategy.scan_day_setups, one call per
trading day, in parallel. Returns per-day matches WITH evidence (timestamp,
price and VWAP of every sequence step) so the user confirms the compiled
spec means what they meant BEFORE arming it.

This is the trust loop competitors built on polling/webhooks cannot close.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from agents.mcp_catalog import MCP
from alerts.spec import AlertSpec

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")

MAX_DRY_RUN_DAYS = 10
_SCAN_TIMEOUT = 150.0
_MAX_PARALLEL = 3  # avoid saturating TimescaleDB with heavy parallel scans


def _last_trading_days(n: int) -> list[str]:
    """Most recent N weekdays (ET), today included, oldest first.

    Market holidays return zero matches and are reported as empty days —
    acceptable for a preview, no calendar dependency needed.
    """
    days: list[str] = []
    cursor = datetime.now(ET)
    while len(days) < n:
        if cursor.weekday() < 5:
            days.append(cursor.strftime("%Y-%m-%d"))
        cursor -= timedelta(days=1)
    return list(reversed(days))


def _summarize_match(m: dict[str, Any]) -> dict[str, Any]:
    """Keep the evidence, drop scanner noise."""
    row: dict[str, Any] = {
        "symbol": m.get("symbol"),
        "open": m.get("o_price"),
        "close": m.get("c_price"),
        "close_vs_open_pct": m.get("close_vs_open_pct"),
        "market_cap": m.get("mcap"),
    }
    if m.get("opening_drop_pct") is not None:
        row["opening_drop_pct"] = m.get("opening_drop_pct")
    for i in range(5):
        ts = m.get(f"s{i}_ts")
        if ts is None:
            break
        row[f"step{i + 1}_event"] = m.get(f"s{i}_event")
        row[f"step{i + 1}_time"] = ts
        row[f"step{i + 1}_price"] = m.get(f"s{i}_price")
        if m.get(f"s{i}_vwap") is not None:
            row[f"step{i + 1}_vwap"] = m.get(f"s{i}_vwap")
    return row


async def _scan_one_day(spec: AlertSpec, date: str, sem: asyncio.Semaphore) -> dict[str, Any]:
    async with sem:
        try:
            raw = await MCP.strategy.scan_day_setups(
                spec.to_scan_args(date), timeout=_SCAN_TIMEOUT,
            )
        except Exception as exc:
            logger.warning("dry-run scan failed for %s on %s: %s", spec.id, date, exc)
            return {"date": date, "error": str(exc), "count": 0, "matches": []}

    if isinstance(raw, dict) and raw.get("error"):
        return {"date": date, "error": raw["error"], "count": 0, "matches": []}

    # The scan runs universe-wide; symbol lists are applied here.
    include = {s.upper() for s in spec.universe.symbols_include}
    exclude = {s.upper() for s in spec.universe.symbols_exclude}
    rows = [
        m for m in (raw.get("matches") or [])
        if (not include or str(m.get("symbol", "")).upper() in include)
        and str(m.get("symbol", "")).upper() not in exclude
    ]
    matches = [_summarize_match(m) for m in rows]
    return {
        "date": date,
        "count": len(matches),
        "matches": matches[:15],  # cap per-day evidence for the synthesizer
        "elapsed_ms": raw.get("elapsed_ms"),
    }


async def run_dry_run(spec: AlertSpec, days: int = 5) -> dict[str, Any]:
    """Replay the spec over the last `days` trading days in parallel.

    Returns:
        {
          "days_scanned": [...],
          "total_fires": int,
          "unique_symbols": [...],
          "per_day": [{"date", "count", "matches": [evidence rows]}],
          "errors": [...],
          "elapsed_ms": int,
        }
    """
    t0 = time.time()
    days = max(1, min(int(days), MAX_DRY_RUN_DAYS))

    if not spec.steps:
        return {
            "days_scanned": [],
            "total_fires": 0,
            "unique_symbols": [],
            "per_day": [],
            "errors": ["spec has no sequence steps to replay (membership/agentic "
                       "tiers get live-only evaluation)"],
            "elapsed_ms": 0,
        }

    dates = _last_trading_days(days)
    sem = asyncio.Semaphore(_MAX_PARALLEL)
    results = await asyncio.gather(*(_scan_one_day(spec, d, sem) for d in dates))

    per_day = sorted(results, key=lambda r: r["date"], reverse=True)
    errors = [f"{r['date']}: {r['error']}" for r in per_day if r.get("error")]
    symbols: set[str] = set()
    total = 0
    for r in per_day:
        total += r["count"]
        for m in r["matches"]:
            if m.get("symbol"):
                symbols.add(m["symbol"])

    return {
        "days_scanned": dates,
        "total_fires": total,
        "unique_symbols": sorted(symbols)[:60],
        "per_day": per_day,
        "errors": errors,
        "elapsed_ms": int((time.time() - t0) * 1000),
    }
