"""
RRG (Relative Rotation Graph) — JdK SMA-Ratio Model

Authentic JdK structure with stable data foundation:
  1. raw_rs = avg N-day change of group stocks (- SPY if benchmark)
  2. ratio = 100 + raw_rs (centers around 100)
  3. RS-Ratio (X) = 100 * SMA(ratio, fast) / SMA(ratio, slow)
  4. RS-Momentum (Y) = 100 * RS-Ratio / SMA(RS-Ratio, mom)

Center at 100. SMA-ratio structure produces natural clockwise rotation.
Values typically 96-104 range.
"""

import time
import asyncio
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Query
import orjson

router = APIRouter(prefix="/api/v1/performance", tags=["performance"])

_redis_client = None
_timescale_client = None


def set_redis_client(client):
    global _redis_client
    _redis_client = client


def set_timescale_client(client):
    global _timescale_client
    _timescale_client = client


# ── Caches ──

_rrg_cache: Dict[str, Tuple[float, dict]] = {}
RRG_CACHE_TTL = 300  # 5 min for trail (historical)

_cls_cache: Dict[str, Dict] = {}
_cls_ts: float = 0
_themes_cache: Dict[str, List[Dict]] = {}
_themes_ts: float = 0
CLS_TTL = 300


# ── JdK SMA-Ratio Parameters ──

RS_METRICS = {
    "change_5d":  {"label": "Short-term",  "lookback": 5,  "sma_fast": 5,  "sma_slow": 13, "mom_sma": 5, "snapshot_key": "change_5d"},
    "change_10d": {"label": "Medium-term", "lookback": 10, "sma_fast": 10, "sma_slow": 22, "mom_sma": 7, "snapshot_key": "change_10d"},
    "change_20d": {"label": "Long-term",   "lookback": 20, "sma_fast": 12, "sma_slow": 26, "mom_sma": 9, "snapshot_key": "change_20d"},
}

DEFAULT_RS_METRIC = "change_20d"


# ── Helpers ──

def _sma(series: List[float], window: int) -> List[Optional[float]]:
    """Simple Moving Average. Returns None for positions with insufficient data."""
    result: List[Optional[float]] = []
    for i in range(len(series)):
        if i < window - 1:
            result.append(None)
        else:
            vals = series[i - window + 1: i + 1]
            result.append(sum(vals) / len(vals))
    return result


async def _load_classifications() -> Dict[str, Dict]:
    global _cls_cache, _cls_ts
    if _cls_cache and time.time() - _cls_ts < CLS_TTL:
        return _cls_cache
    rows = await _timescale_client.fetch(
        "SELECT symbol, sector, industry FROM ticker_classification WHERE is_operating = TRUE"
    )
    _cls_cache = {r["symbol"]: {"sector": r["sector"], "industry": r["industry"]} for r in rows}
    _cls_ts = time.time()
    return _cls_cache


async def _load_themes() -> Dict[str, List[Dict]]:
    global _themes_cache, _themes_ts
    if _themes_cache and time.time() - _themes_ts < CLS_TTL:
        return _themes_cache
    rows = await _timescale_client.fetch(
        "SELECT symbol, theme, relevance FROM ticker_themes WHERE relevance >= 0.6 ORDER BY symbol, relevance DESC"
    )
    result = defaultdict(list)
    for r in rows:
        result[r["symbol"]].append({"theme": r["theme"], "relevance": float(r["relevance"])})
    _themes_cache = dict(result)
    _themes_ts = time.time()
    return _themes_cache


# ── Endpoint ──

@router.get("/rrg")
async def get_rrg(
    group_by: str = Query("sectors", regex="^(sectors|industries|themes)$"),
    rs_metric: str = Query(DEFAULT_RS_METRIC),
    benchmark: str = Query("none", regex="^(none|spy)$"),
    tail_length: int = Query(20, ge=5, le=60),
    min_market_cap: Optional[int] = Query(None),
):
    if rs_metric not in RS_METRICS:
        rs_metric = DEFAULT_RS_METRIC

    metric_info = RS_METRICS[rs_metric]
    lookback = metric_info["lookback"]
    sma_fast = metric_info["sma_fast"]
    sma_slow = metric_info["sma_slow"]
    mom_sma = metric_info["mom_sma"]
    snapshot_key = metric_info["snapshot_key"]

    cache_key = f"rrg6:{group_by}:{rs_metric}:{benchmark}:{tail_length}:{min_market_cap}"
    cached = _rrg_cache.get(cache_key)
    if cached and time.time() - cached[0] < RRG_CACHE_TTL:
        trail_result = cached[1]
    else:
        trail_result = None

    # ── Load enriched snapshot (always, for live point + market cap filter) ──
    raw_snapshot = await _redis_client.client.hgetall("snapshot:enriched:latest")
    raw_snapshot.pop(b"__meta__", None)

    snapshot: Dict[str, Dict] = {}
    eligible_symbols: Optional[set] = None
    if min_market_cap:
        eligible_symbols = set()

    for sym_b, val_b in raw_snapshot.items():
        try:
            d = orjson.loads(val_b)
            sym = sym_b.decode() if isinstance(sym_b, bytes) else sym_b
            snapshot[sym] = d
            if eligible_symbols is not None and (d.get("market_cap") or 0) >= min_market_cap:
                eligible_symbols.add(sym)
        except Exception:
            pass

    # ── Load classifications ──
    cls_task = _load_classifications()
    themes_task = _load_themes() if group_by == "themes" else asyncio.sleep(0)
    cls_data, themes_data_or_none = await asyncio.gather(cls_task, themes_task)
    themes_data = themes_data_or_none if isinstance(themes_data_or_none, dict) else {}

    # ── Build group -> symbols mapping ──
    group_symbols: Dict[str, set] = defaultdict(set)

    if group_by == "themes":
        for sym, theme_list in themes_data.items():
            if eligible_symbols is not None and sym not in eligible_symbols:
                continue
            for th in theme_list:
                group_symbols[th["theme"]].add(sym)
    else:
        key_field = "sector" if group_by == "sectors" else "industry"
        for sym, cls in cls_data.items():
            if eligible_symbols is not None and sym not in eligible_symbols:
                continue
            g = cls.get(key_field)
            if g:
                group_symbols[g].add(sym)

    min_tickers = 3 if group_by == "themes" else 2
    group_symbols = {g: s for g, s in group_symbols.items() if len(s) >= min_tickers}

    if not group_symbols:
        return {"groups": [], "quadrant_distribution": {}, "center": 100}

    # ══════════════════════════════════════════════
    # Compute trail (historical, cached)
    # ══════════════════════════════════════════════
    if trail_result is None:
        # Need: lookback + sma_slow + mom_sma + tail_length + buffer
        total_days = lookback + sma_slow + mom_sma + tail_length + 10

        start_row = await _timescale_client.fetchrow(
            "SELECT MIN(d) AS start_date FROM ("
            "  SELECT DISTINCT trading_date AS d FROM market_data_daily"
            "  ORDER BY d DESC LIMIT $1"
            ") sub",
            total_days,
        )
        start_date = start_row["start_date"]

        daily_rows = await _timescale_client.fetch(
            "SELECT trading_date, symbol, close "
            "FROM market_data_daily WHERE trading_date >= $1 "
            "ORDER BY trading_date, symbol",
            start_date,
        )

        # Build per-day close prices
        daily_close: Dict[str, Dict[str, float]] = defaultdict(dict)
        for row in daily_rows:
            d = str(row["trading_date"])
            if row["close"]:
                daily_close[d][row["symbol"]] = float(row["close"])

        all_dates = sorted(daily_close.keys())
        if len(all_dates) < lookback + sma_slow + 2:
            return {"groups": [], "quadrant_distribution": {}, "error": "Insufficient data", "center": 100}

        date_index = {d: i for i, d in enumerate(all_dates)}

        # ── Step 1: raw_rs per group per date ──
        # Raw RS = avg N-day change of group stocks (optionally minus SPY)
        computable_start = lookback
        computable_dates = all_dates[computable_start:]

        # SPY changes for benchmark subtraction
        spy_changes: Dict[str, float] = {}
        if benchmark == "spy":
            for date in computable_dates:
                idx = date_index[date]
                prev_date = all_dates[idx - lookback]
                spy_today = daily_close[date].get("SPY")
                spy_prev = daily_close[prev_date].get("SPY")
                if spy_today and spy_prev and spy_prev > 0:
                    spy_changes[date] = ((spy_today - spy_prev) / spy_prev) * 100

        # raw_rs per group aligned with computable_dates
        group_raw_rs: Dict[str, List[float]] = {g: [] for g in group_symbols}

        for date in computable_dates:
            idx = date_index[date]
            prev_date = all_dates[idx - lookback]
            day_prices = daily_close[date]
            prev_prices = daily_close[prev_date]

            for gname, symbols in group_symbols.items():
                changes = []
                for sym in symbols:
                    if sym in day_prices and sym in prev_prices and prev_prices[sym] > 0:
                        changes.append(((day_prices[sym] - prev_prices[sym]) / prev_prices[sym]) * 100)
                if changes:
                    raw = sum(changes) / len(changes)
                    if benchmark == "spy" and date in spy_changes:
                        raw -= spy_changes[date]
                    group_raw_rs[gname].append(raw)
                else:
                    group_raw_rs[gname].append(0.0)

        # ── Step 2-4: ratio -> RS-Ratio -> RS-Momentum (JdK SMA structure) ──
        group_trails: Dict[str, List[Dict]] = {}
        group_live_stats: Dict[str, Dict] = {}

        for gname in group_symbols:
            raw_series = group_raw_rs.get(gname, [])
            if len(raw_series) < sma_slow + mom_sma:
                continue

            # Convert raw_rs to ratio-like series centered at 100
            ratio_series = [100.0 + v for v in raw_series]

            # SMA of ratio
            sma_f = _sma(ratio_series, sma_fast)
            sma_s = _sma(ratio_series, sma_slow)

            # RS-Ratio = 100 * SMA_fast / SMA_slow
            rs_ratio_series: List[Optional[float]] = []
            for i in range(len(ratio_series)):
                if sma_f[i] is not None and sma_s[i] is not None and sma_s[i] > 0:
                    rs_ratio_series.append(100.0 * sma_f[i] / sma_s[i])
                else:
                    rs_ratio_series.append(None)

            # Extract valid RS-Ratio for momentum SMA
            valid_rs_entries: List[Tuple[int, float]] = []
            for i, v in enumerate(rs_ratio_series):
                if v is not None:
                    valid_rs_entries.append((i, v))

            if len(valid_rs_entries) < mom_sma:
                continue

            valid_rs_vals = [v for _, v in valid_rs_entries]
            sma_mom = _sma(valid_rs_vals, mom_sma)

            # RS-Momentum = 100 * RS_Ratio / SMA(RS_Ratio, mom_sma)
            rs_mom_series: List[Optional[float]] = [None] * len(rs_ratio_series)
            for j, (orig_i, rs_val) in enumerate(valid_rs_entries):
                if sma_mom[j] is not None and sma_mom[j] > 0:
                    rs_mom_series[orig_i] = 100.0 * rs_val / sma_mom[j]

            # ── Extract trail (last tail_length valid points) ──
            trail_points: List[Dict] = []
            for i in range(len(computable_dates) - 1, -1, -1):
                if i < len(rs_ratio_series) and rs_ratio_series[i] is not None and rs_mom_series[i] is not None:
                    trail_points.append({
                        "date": computable_dates[i],
                        "x": round(rs_ratio_series[i], 2),
                        "y": round(rs_mom_series[i], 2),
                    })
                if len(trail_points) >= tail_length:
                    break

            trail_points.reverse()

            if trail_points:
                group_trails[gname] = trail_points

                # Save state for live point computation
                # Need last sma_slow ratio values + last mom_sma RS-Ratio values
                group_live_stats[gname] = {
                    "last_ratio_values": ratio_series[-sma_slow:],
                    "last_rs_ratio_values": valid_rs_vals[-mom_sma:],
                }

        trail_result = {
            "group_trails": group_trails,
            "group_live_stats": group_live_stats,
            "sma_fast": sma_fast,
            "sma_slow": sma_slow,
            "mom_sma": mom_sma,
        }
        _rrg_cache[cache_key] = (time.time(), trail_result)

    # ══════════════════════════════════════════════
    # Phase 2: LIVE current point from snapshot
    # ══════════════════════════════════════════════
    group_trails = trail_result["group_trails"]
    group_live_stats = trail_result.get("group_live_stats", {})
    sma_fast_c = trail_result.get("sma_fast", sma_fast)
    sma_slow_c = trail_result.get("sma_slow", sma_slow)
    mom_sma_c = trail_result.get("mom_sma", mom_sma)

    # Get change_Nd for every stock in snapshot
    all_live_changes: Dict[str, float] = {}
    for sym, data in snapshot.items():
        v = data.get(snapshot_key)
        if v is not None:
            try:
                all_live_changes[sym] = float(v)
            except (ValueError, TypeError):
                pass

    # SPY benchmark subtraction
    if benchmark == "spy":
        spy_live = all_live_changes.get("SPY")
        if spy_live is not None:
            all_live_changes = {s: v - spy_live for s, v in all_live_changes.items()}
            all_live_changes.pop("SPY", None)

    # Compute live RS-Ratio and RS-Momentum per group
    live_points: Dict[str, Dict[str, float]] = {}

    for gname, symbols in group_symbols.items():
        stats = group_live_stats.get(gname)
        if not stats:
            continue

        # Average change_Nd of group's stocks in snapshot
        changes = [all_live_changes[s] for s in symbols if s in all_live_changes]
        if not changes:
            continue

        live_raw = sum(changes) / len(changes)

        # Convert to ratio centered at 100
        live_ratio = 100.0 + live_raw

        # Extend ratio series and compute new SMAs
        ext_ratio = stats["last_ratio_values"] + [live_ratio]

        if len(ext_ratio) < sma_fast_c:
            continue
        sma_f_live = sum(ext_ratio[-sma_fast_c:]) / sma_fast_c

        if len(ext_ratio) < sma_slow_c:
            continue
        sma_s_live = sum(ext_ratio[-sma_slow_c:]) / sma_slow_c

        if sma_s_live <= 0:
            continue

        rs_ratio_live = 100.0 * sma_f_live / sma_s_live

        # Extend RS-Ratio series and compute momentum
        ext_rs = stats["last_rs_ratio_values"] + [rs_ratio_live]

        if len(ext_rs) < mom_sma_c:
            continue
        sma_m_live = sum(ext_rs[-mom_sma_c:]) / mom_sma_c

        if sma_m_live <= 0:
            continue

        rs_mom_live = 100.0 * rs_ratio_live / sma_m_live

        live_points[gname] = {
            "x": round(rs_ratio_live, 2),
            "y": round(rs_mom_live, 2),
        }

    # ══════════════════════════════════════════════
    # Build response
    # ══════════════════════════════════════════════
    quadrant_counts = {"leading": 0, "weakening": 0, "lagging": 0, "improving": 0}
    groups = []
    all_x: List[float] = []
    all_y: List[float] = []

    for gname in sorted(group_symbols.keys()):
        trail = group_trails.get(gname, [])
        if not trail:
            continue

        # Current point: live if available, else last trail point
        if gname in live_points:
            current = live_points[gname]
        else:
            current = {"x": trail[-1]["x"], "y": trail[-1]["y"]}

        # Collect ALL points for auto_range
        for pt in trail:
            all_x.append(pt["x"])
            all_y.append(pt["y"])
        all_x.append(current["x"])
        all_y.append(current["y"])

        # Quadrant
        if current["x"] >= 100 and current["y"] >= 100:
            q = "leading"
        elif current["x"] >= 100:
            q = "weakening"
        elif current["y"] < 100:
            q = "lagging"
        else:
            q = "improving"
        quadrant_counts[q] += 1

        groups.append({
            "name": gname,
            "count": len(group_symbols[gname]),
            "trail": trail,
            "current": current,
            "quadrant": q,
        })

    total = sum(quadrant_counts.values()) or 1

    # Auto-range: symmetric padding around 100
    if all_x and all_y:
        max_dev_x = max(abs(v - 100) for v in all_x)
        max_dev_y = max(abs(v - 100) for v in all_y)
        range_x = max(max_dev_x * 1.15, 1.0)
        range_y = max(max_dev_y * 1.15, 1.0)
        auto_range = {
            "x_min": round(100 - range_x, 2),
            "x_max": round(100 + range_x, 2),
            "y_min": round(100 - range_y, 2),
            "y_max": round(100 + range_y, 2),
        }
    else:
        auto_range = {"x_min": 96, "x_max": 104, "y_min": 96, "y_max": 104}

    return {
        "groups": groups,
        "quadrant_distribution": {k: round(v / total * 100) for k, v in quadrant_counts.items()},
        "axis_labels": {"x": "JdK RS-Ratio", "y": "JdK RS-Momentum"},
        "center": 100,
        "auto_range": auto_range,
        "rs_metric": rs_metric,
        "rs_metric_label": metric_info["label"],
        "benchmark": benchmark,
        "rs_metrics": {k: v["label"] for k, v in RS_METRICS.items()},
    }
