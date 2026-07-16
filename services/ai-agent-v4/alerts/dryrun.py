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
import re
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


_SESSION_HOURS = {
    "regular": (9, 16),
    "premarket": (4, 9),
    "afterhours": (16, 20),
    "all": (4, 20),
}

_MAX_EVIDENCE_CHARTS = 2


def _et_wallclock(ts: float) -> int:
    """Epoch shifted so the chart lib (UTC display) shows ET wall-clock time."""
    offset = ET.utcoffset(datetime.fromtimestamp(ts, ET))
    return int(ts + (offset.total_seconds() if offset else 0))


def _parse_et_time(date: str, timestr: Any) -> float | None:
    """'09:34:26 ET' + '2026-07-15' → epoch seconds, or None."""
    m = re.search(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", str(timestr or ""))
    if not m:
        return None
    try:
        y, mo, d = (int(x) for x in date.split("-"))
        dt = datetime(y, mo, d, int(m.group(1)), int(m.group(2)),
                      int(m.group(3) or 0), tzinfo=ET)
        return dt.timestamp()
    except (ValueError, TypeError):
        return None


def _match_fire_point(date: str, m: dict[str, Any]) -> dict[str, Any] | None:
    """Extract {t, price, label} from a dry-run match row (any tier)."""
    # Price-level matches carry an exact epoch in "t".
    if m.get("t"):
        return {
            "t": _et_wallclock(float(m["t"])),
            "price": m.get("step1_price") or m.get("level"),
            "label": m.get("step1_event") or "fire",
        }
    # Event/sequence matches: use the LAST step (the moment the alert fires).
    last = None
    for i in range(1, 6):
        if m.get(f"step{i}_time") is None:
            break
        last = i
    if last is None:
        return None
    ts = _parse_et_time(date, m.get(f"step{last}_time"))
    if ts is None:
        return None
    return {
        "t": _et_wallclock(ts),
        "price": m.get(f"step{last}_price"),
        "label": m.get(f"step{last}_event") or "fire",
    }


async def _fetch_evidence_bars(spec: AlertSpec, symbol: str, date: str) -> list[dict[str, Any]]:
    start_hour, end_hour = _SESSION_HOURS.get(spec.universe.session, (9, 16))
    try:
        raw = await MCP.historical.get_minute_bars(
            {"date": date, "symbol": symbol,
             "start_hour": start_hour, "end_hour": end_hour},
            timeout=60.0,
        )
    except Exception:
        return []
    if isinstance(raw, dict) and raw.get("error"):
        return []
    out = []
    for b in raw.get("bars") or []:
        try:
            out.append({
                "t": _et_wallclock(int(b["window_start"]) / 1e9),
                "o": float(b["open"]), "h": float(b["high"]),
                "l": float(b["low"]), "c": float(b["close"]),
            })
        except (KeyError, TypeError, ValueError):
            continue
    return out


async def _build_chart_evidence(
    spec: AlertSpec, per_day: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Real candles + fire markers so the user SEES each dry-run trigger.

    Picks up to _MAX_EVIDENCE_CHARTS (date, symbol) pairs, most recent days
    with fires first. Specs with explicit tickers but zero fires still get
    the most recent session as context ("this is what the day looked like").
    """
    include = [s.upper() for s in spec.universe.symbols_include]
    pairs: list[tuple[str, str]] = []
    for day in per_day:  # already sorted desc by date
        for m in day.get("matches") or []:
            sym = str(m.get("symbol") or "").upper()
            if sym:
                p = (day["date"], sym)
                if p not in pairs:
                    pairs.append(p)
    context_only = not pairs
    if context_only and include:
        # No fires: still show recent context for the watched ticker. Try a
        # few days — the current day often has no minute bars loaded yet.
        pairs = [(d["date"], include[0]) for d in per_day[:3]]

    levels = [p.model_dump() for p in spec.price_levels]
    evidence: list[dict[str, Any]] = []
    # Try a couple extra pairs: today's minute bars usually aren't loaded
    # yet (T+1 flat files), so a fire from today falls through to yesterday.
    max_charts = 1 if context_only else _MAX_EVIDENCE_CHARTS
    for date, sym in pairs[: _MAX_EVIDENCE_CHARTS + 2]:
        if len(evidence) >= max_charts:
            break
        bars = await _fetch_evidence_bars(spec, sym, date)
        if len(bars) < 5:
            continue
        day = next((d for d in per_day if d["date"] == date), None)
        fires = []
        for m in (day or {}).get("matches") or []:
            if str(m.get("symbol") or "").upper() != sym:
                continue
            pt = _match_fire_point(date, m)
            if pt and pt["t"]:
                fires.append(pt)
        evidence.append({
            "symbol": sym, "date": date, "bars": bars,
            "fires": sorted(fires, key=lambda f: f["t"]),
            "levels": levels,
        })
    return evidence


async def _scan_price_levels_one_day(
    spec: AlertSpec, symbol: str, date: str, sem: asyncio.Semaphore,
) -> dict[str, Any]:
    """Replay price-level crosses over minute closes for one symbol/day.

    Uses bar CLOSES (not wick highs/lows) — conservative: a level counts as
    reclaimed/lost when a full minute settles through it, mirroring how the
    live runtime sees consecutive event prices. Cooldown is applied between
    fires exactly like the live lifecycle.
    """
    start_hour, end_hour = _SESSION_HOURS.get(spec.universe.session, (9, 16))
    async with sem:
        try:
            raw = await MCP.historical.get_minute_bars(
                {"date": date, "symbol": symbol,
                 "start_hour": start_hour, "end_hour": end_hour},
                timeout=60.0,
            )
        except Exception as exc:
            return {"date": date, "error": str(exc), "count": 0, "matches": []}

    if isinstance(raw, dict) and raw.get("error"):
        return {"date": date, "error": raw["error"], "count": 0, "matches": []}

    bars = raw.get("bars") or []
    if len(bars) < 2:
        return {"date": date, "count": 0, "matches": []}

    cooldown = spec.lifecycle.cooldown_seconds
    matches: list[dict[str, Any]] = []
    last_fire_ts: float | None = None
    prev_close = float(bars[0]["close"])
    for bar in bars[1:]:
        close = float(bar["close"])
        ts_ns = int(bar.get("window_start") or 0)
        ts = ts_ns / 1e9
        for lvl in spec.price_levels:
            crossed = (
                (lvl.direction == "above" and prev_close < lvl.value <= close)
                or (lvl.direction == "below" and prev_close > lvl.value >= close)
            )
            if not crossed:
                continue
            if last_fire_ts is not None and (ts - last_fire_ts) < cooldown:
                continue
            last_fire_ts = ts
            t_et = datetime.fromtimestamp(ts, ET).strftime("%H:%M ET") if ts else ""
            matches.append({
                "symbol": symbol,
                "step1_event": (
                    f"price_{'reclaim' if lvl.direction == 'above' else 'breakdown'}_"
                    f"{lvl.value:g}"
                ),
                "step1_time": t_et,
                "step1_price": close,
                "t": ts,
                "level": lvl.value,
                "direction": lvl.direction,
            })
            break  # one fire per bar max
        prev_close = close

    return {"date": date, "count": len(matches), "matches": matches[:15]}


async def _run_price_level_dry_run(spec: AlertSpec, days: int) -> dict[str, Any]:
    t0 = time.time()
    dates = _last_trading_days(days)
    symbols = [s.upper() for s in spec.universe.symbols_include][:5]
    sem = asyncio.Semaphore(_MAX_PARALLEL)

    results = await asyncio.gather(*(
        _scan_price_levels_one_day(spec, sym, d, sem)
        for d in dates for sym in symbols
    ))

    # Merge per (date) across symbols
    by_date: dict[str, dict[str, Any]] = {
        d: {"date": d, "count": 0, "matches": [], "error": None} for d in dates
    }
    for r in results:
        slot = by_date[r["date"]]
        slot["count"] += r["count"]
        slot["matches"].extend(r["matches"])
        if r.get("error") and "No minute data" not in str(r["error"]):
            slot["error"] = r["error"]

    per_day = sorted(by_date.values(), key=lambda r: r["date"], reverse=True)
    for slot in per_day:
        if not slot["error"]:
            slot.pop("error")
        slot["matches"] = slot["matches"][:15]
    errors = [f"{r['date']}: {r['error']}" for r in per_day if r.get("error")]
    fired_symbols = sorted({
        m["symbol"] for r in per_day for m in r["matches"] if m.get("symbol")
    })

    try:
        chart_evidence = await _build_chart_evidence(spec, per_day)
    except Exception:
        logger.exception("chart evidence failed for %s", spec.id)
        chart_evidence = []

    return {
        "days_scanned": dates,
        "total_fires": sum(r["count"] for r in per_day),
        "unique_symbols": fired_symbols,
        "per_day": per_day,
        "chart_evidence": chart_evidence,
        "errors": errors,
        "elapsed_ms": int((time.time() - t0) * 1000),
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

    if spec.price_levels and not spec.steps:
        return await _run_price_level_dry_run(spec, days)

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

    try:
        chart_evidence = await _build_chart_evidence(spec, per_day)
    except Exception:
        logger.exception("chart evidence failed for %s", spec.id)
        chart_evidence = []

    return {
        "days_scanned": dates,
        "total_fires": total,
        "unique_symbols": sorted(symbols)[:60],
        "per_day": per_day,
        "chart_evidence": chart_evidence,
        "errors": errors,
        "elapsed_ms": int((time.time() - t0) * 1000),
    }
