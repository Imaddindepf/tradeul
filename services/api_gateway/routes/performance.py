"""
Market Performance API
Real-time sector, industry, and theme performance aggregation.

Reads snapshot:enriched:latest from Redis, joins with ticker_classification
and ticker_themes from TimescaleDB, aggregates performance metrics.
Results are cached in-memory with a short TTL for fast reads.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, Dict, Any, List
from collections import defaultdict
import time
import asyncio
from shared.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/performance", tags=["performance"])

_redis_client = None
_timescale_client = None

_classification_cache: Dict[str, Dict] = {}
_classification_cache_ts: float = 0
CLASSIFICATION_CACHE_TTL = 300

_themes_cache: Dict[str, List[Dict]] = {}
_themes_cache_ts: float = 0
THEMES_CACHE_TTL = 300

_result_cache: Dict[str, Any] = {}
_result_cache_ts: Dict[str, float] = {}
RESULT_CACHE_TTL = 2

_snapshot_cache: List[Dict] = []
_snapshot_cache_ts: float = 0
SNAPSHOT_CACHE_TTL = 2


def set_redis_client(client):
    global _redis_client
    _redis_client = client


def set_timescale_client(client):
    global _timescale_client
    _timescale_client = client


async def _load_classifications() -> Dict[str, Dict]:
    global _classification_cache, _classification_cache_ts

    now = time.time()
    if _classification_cache and (now - _classification_cache_ts) < CLASSIFICATION_CACHE_TTL:
        return _classification_cache

    if not _timescale_client:
        return _classification_cache

    try:
        rows = await _timescale_client.fetch(
            """SELECT symbol, sector, industry_group, industry, sub_industry, is_operating
               FROM ticker_classification
               WHERE is_operating = TRUE"""
        )
        result = {}
        for r in rows:
            result[r["symbol"]] = {
                "sector": r["sector"],
                "industry_group": r["industry_group"],
                "industry": r["industry"],
                "sub_industry": r["sub_industry"],
            }
        _classification_cache = result
        _classification_cache_ts = now
        logger.info("classification_cache_loaded", count=len(result))
    except Exception as e:
        logger.error("classification_cache_error", error=str(e))

    return _classification_cache


async def _load_themes() -> Dict[str, List[Dict]]:
    global _themes_cache, _themes_cache_ts

    now = time.time()
    if _themes_cache and (now - _themes_cache_ts) < THEMES_CACHE_TTL:
        return _themes_cache

    if not _timescale_client:
        return _themes_cache

    try:
        rows = await _timescale_client.fetch(
            """SELECT symbol, theme, relevance
               FROM ticker_themes
               WHERE relevance >= 0.6
               ORDER BY symbol, relevance DESC"""
        )
        result: Dict[str, List[Dict]] = defaultdict(list)
        for r in rows:
            result[r["symbol"]].append({
                "theme": r["theme"],
                "relevance": float(r["relevance"]),
            })
        _themes_cache = dict(result)
        _themes_cache_ts = now
        logger.info("themes_cache_loaded", symbols=len(result))
    except Exception as e:
        logger.error("themes_cache_error", error=str(e))

    return _themes_cache


def _safe_avg(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0

def _safe_median(values: List[float]) -> float:
    if not values:
        return 0
    s = sorted(values)
    return s[len(s) // 2]

def _collect(tickers: List[Dict], key: str) -> List[float]:
    return [v for t in tickers if (v := t.get(key)) is not None]


def _aggregate_group(tickers: List[Dict]) -> Dict:
    if not tickers:
        return {}

    changes = []
    advancing = 0
    declining = 0
    total_volume = 0
    total_dollar_volume = 0.0
    total_market_cap = 0.0
    rvols = []

    for t in tickers:
        chg = t.get("change_percent")
        if chg is not None:
            changes.append(chg)
            if chg > 0:
                advancing += 1
            elif chg < 0:
                declining += 1

        vol = t.get("volume") or 0
        price = t.get("price") or 0
        mcap = t.get("market_cap") or 0
        rvol = t.get("rvol")

        total_volume += vol
        total_dollar_volume += t.get("dollar_volume") or (vol * price)
        total_market_cap += mcap
        if rvol is not None and rvol > 0:
            rvols.append(rvol)

    n = len(tickers)
    avg_change = _safe_avg(changes)
    median_change = _safe_median(changes)
    breadth = advancing / n if n > 0 else 0
    avg_rvol = _safe_avg(rvols)

    mcap_weighted_change = 0.0
    if total_market_cap > 0:
        for t in tickers:
            chg = t.get("change_percent", 0) or 0
            mcap = t.get("market_cap", 0) or 0
            mcap_weighted_change += chg * (mcap / total_market_cap)

    r = lambda v, d=4: round(v, d)

    return {
        "count": n,
        "advancing": advancing,
        "declining": declining,
        "unchanged": n - advancing - declining,
        "breadth": r(breadth),
        "avg_change": r(avg_change),
        "median_change": r(median_change),
        "weighted_change": r(mcap_weighted_change),
        "avg_rvol": r(avg_rvol, 2),
        "total_volume": total_volume,
        "total_dollar_volume": r(total_dollar_volume, 0),
        "total_market_cap": r(total_market_cap, 0),
        "avg_rsi": r(_safe_avg(_collect(tickers, "rsi_14")), 2),
        "avg_daily_rsi": r(_safe_avg(_collect(tickers, "daily_rsi")), 2),
        "avg_atr_pct": r(_safe_avg(_collect(tickers, "atr_percent")), 2),
        "avg_daily_atr_pct": r(_safe_avg(_collect(tickers, "daily_atr_percent")), 2),
        "avg_gap_pct": r(_safe_avg(_collect(tickers, "gap_percent")), 2),
        "avg_adx": r(_safe_avg(_collect(tickers, "adx_14")), 2),
        "avg_daily_adx": r(_safe_avg(_collect(tickers, "daily_adx_14")), 2),
        "avg_dist_vwap": r(_safe_avg(_collect(tickers, "dist_from_vwap")), 2),
        "avg_change_5d": r(_safe_avg(_collect(tickers, "change_5d")), 2),
        "avg_change_10d": r(_safe_avg(_collect(tickers, "change_10d")), 2),
        "avg_change_20d": r(_safe_avg(_collect(tickers, "change_20d")), 2),
        "avg_from_52w_high": r(_safe_avg(_collect(tickers, "from_52w_high")), 2),
        "avg_from_52w_low": r(_safe_avg(_collect(tickers, "from_52w_low")), 2),
        "avg_float_turnover": r(_safe_avg(_collect(tickers, "float_turnover")), 4),
        "avg_bid_ask_ratio": r(_safe_avg(_collect(tickers, "bid_ask_ratio")), 2),
        "avg_pos_in_range": r(_safe_avg(_collect(tickers, "pos_in_range")), 2),
        "avg_bb_position": r(_safe_avg(_collect(tickers, "daily_bb_position")), 2),
        "avg_trades_z": r(_safe_avg(_collect(tickers, "trades_z_score")), 2),
        "avg_range_pct": r(_safe_avg(_collect(tickers, "todays_range_pct")), 2),
        "avg_dist_sma20": r(_safe_avg(_collect(tickers, "dist_daily_sma_20")), 2),
        "avg_dist_sma50": r(_safe_avg(_collect(tickers, "dist_daily_sma_50")), 2),
        "avg_vol_today_pct": r(_safe_avg(_collect(tickers, "volume_today_pct")), 2),
    }


def _top_movers(tickers: List[Dict], n: int = 5) -> Dict:
    sorted_by_change = sorted(
        [t for t in tickers if t.get("change_percent") is not None],
        key=lambda t: t["change_percent"],
        reverse=True,
    )
    fmt = lambda t: {
        "symbol": t["symbol"],
        "price": t.get("price"),
        "change_percent": round(t.get("change_percent", 0), 4),
        "volume": t.get("volume"),
        "market_cap": t.get("market_cap"),
    }
    return {
        "gainers": [fmt(t) for t in sorted_by_change[:n]],
        "losers": [fmt(t) for t in sorted_by_change[-n:]],
    }


@router.get("/sectors")
async def get_sector_performance(
    min_market_cap: Optional[int] = Query(None),
    include_movers: bool = Query(False),
):
    return await _get_performance("sector", min_market_cap, include_movers)


@router.get("/industries")
async def get_industry_performance(
    sector: Optional[str] = Query(None),
    min_market_cap: Optional[int] = Query(None),
    include_movers: bool = Query(False),
):
    return await _get_performance("industry", min_market_cap, include_movers, sector_filter=sector)


@router.get("/themes")
async def get_theme_performance(
    min_market_cap: Optional[int] = Query(None),
    min_tickers: int = Query(3),
    include_movers: bool = Query(False),
):
    return await _get_theme_performance(min_market_cap, min_tickers, include_movers)


@router.get("/drilldown/{group_type}/{group_name}")
async def get_drilldown(
    group_type: str,
    group_name: str,
    min_market_cap: Optional[int] = Query(None),
    sort_by: str = Query("change_percent"),
    limit: int = Query(50, ge=1, le=200),
):
    return await _get_drilldown(group_type, group_name, min_market_cap, sort_by, limit)


async def _load_snapshot() -> List[Dict]:
    global _snapshot_cache, _snapshot_cache_ts

    now = time.time()
    if _snapshot_cache and (now - _snapshot_cache_ts) < SNAPSHOT_CACHE_TTL:
        return _snapshot_cache

    if not _redis_client:
        raise HTTPException(status_code=503, detail="Redis not available")

    import orjson

    all_data = await _redis_client.client.hgetall("snapshot:enriched:latest")
    if not all_data:
        all_data = await _redis_client.client.hgetall("snapshot:enriched:last_close")
        if not all_data:
            raise HTTPException(status_code=404, detail="No market data available")

    all_data.pop("__meta__", None)

    tickers = []
    for sym, raw in all_data.items():
        try:
            t = orjson.loads(raw)
            symbol = t.get("ticker") or t.get("symbol")
            if not symbol:
                continue
            price = t.get("price") or t.get("current_price") or (t.get("lastTrade") or {}).get("p")
            vol = t.get("volume") or t.get("current_volume") or (t.get("day") or {}).get("v", 0)
            tickers.append({
                "symbol": symbol,
                "price": price,
                "change_percent": t.get("change_percent") or t.get("todaysChangePerc"),
                "volume": vol,
                "market_cap": t.get("market_cap", 0),
                "rvol": t.get("rvol"),
                "security_type": t.get("security_type"),
                "dollar_volume": t.get("dollar_volume") or ((vol or 0) * (price or 0)),
                "gap_percent": t.get("gap_percent"),
                "atr_percent": t.get("atr_percent"),
                "rsi_14": t.get("rsi_14"),
                "daily_rsi": t.get("daily_rsi"),
                "daily_atr_percent": t.get("daily_atr_percent"),
                "adx_14": t.get("adx_14"),
                "daily_adx_14": t.get("daily_adx_14"),
                "vwap": t.get("vwap"),
                "dist_from_vwap": t.get("dist_from_vwap"),
                "change_5d": t.get("change_5d"),
                "change_10d": t.get("change_10d"),
                "change_20d": t.get("change_20d"),
                "from_52w_high": t.get("from_52w_high"),
                "from_52w_low": t.get("from_52w_low"),
                "float_turnover": t.get("float_turnover"),
                "bid_ask_ratio": t.get("bid_ask_ratio"),
                "pos_in_range": t.get("pos_in_range"),
                "daily_bb_position": t.get("daily_bb_position"),
                "trades_z_score": t.get("trades_z_score"),
                "avg_volume_20d": t.get("avg_volume_20d"),
                "todays_range_pct": t.get("todays_range_pct"),
                "dist_daily_sma_20": t.get("dist_daily_sma_20"),
                "dist_daily_sma_50": t.get("dist_daily_sma_50"),
                "volume_today_pct": t.get("volume_today_pct"),
            })
        except Exception:
            continue

    _snapshot_cache = tickers
    _snapshot_cache_ts = now
    return tickers


async def _get_performance(
    group_by: str,
    min_market_cap: Optional[int],
    include_movers: bool,
    sector_filter: Optional[str] = None,
):
    cache_key = f"{group_by}:{min_market_cap}:{include_movers}:{sector_filter}"
    now = time.time()
    cached_ts = _result_cache_ts.get(cache_key, 0)
    if cache_key in _result_cache and (now - cached_ts) < RESULT_CACHE_TTL:
        return _result_cache[cache_key]

    snapshot, classifications = await asyncio.gather(
        _load_snapshot(),
        _load_classifications(),
    )

    groups: Dict[str, List[Dict]] = defaultdict(list)

    for t in snapshot:
        sym = t["symbol"]
        cls = classifications.get(sym)
        if not cls:
            continue
        if t.get("security_type") in ("ETF", "ETN"):
            continue
        if min_market_cap and (t.get("market_cap") or 0) < min_market_cap:
            continue

        key = cls.get(group_by) or cls.get("sector") or "Other"

        if sector_filter and group_by == "industry":
            if cls.get("sector") != sector_filter:
                continue

        groups[key].append(t)

    results = []
    for name, tickers in groups.items():
        entry = {
            "name": name,
            **_aggregate_group(tickers),
        }
        if include_movers:
            entry["movers"] = _top_movers(tickers)
        results.append(entry)

    results.sort(key=lambda x: x.get("weighted_change", 0), reverse=True)

    response = {
        "group_by": group_by,
        "data": results,
        "timestamp": time.time(),
        "total_tickers": sum(r["count"] for r in results),
    }

    _result_cache[cache_key] = response
    _result_cache_ts[cache_key] = now
    return response


async def _get_theme_performance(
    min_market_cap: Optional[int],
    min_tickers: int,
    include_movers: bool,
):
    cache_key = f"themes:{min_market_cap}:{min_tickers}:{include_movers}"
    now = time.time()
    cached_ts = _result_cache_ts.get(cache_key, 0)
    if cache_key in _result_cache and (now - cached_ts) < RESULT_CACHE_TTL:
        return _result_cache[cache_key]

    snapshot, themes_map = await asyncio.gather(
        _load_snapshot(),
        _load_themes(),
    )

    ticker_lookup = {t["symbol"]: t for t in snapshot}
    groups: Dict[str, List[Dict]] = defaultdict(list)

    for sym, theme_list in themes_map.items():
        t = ticker_lookup.get(sym)
        if not t:
            continue
        if t.get("security_type") in ("ETF", "ETN"):
            continue
        if min_market_cap and (t.get("market_cap") or 0) < min_market_cap:
            continue

        for th in theme_list:
            groups[th["theme"]].append(t)

    results = []
    for name, tickers in groups.items():
        if len(tickers) < min_tickers:
            continue
        entry = {
            "name": name,
            **_aggregate_group(tickers),
        }
        if include_movers:
            entry["movers"] = _top_movers(tickers)
        results.append(entry)

    results.sort(key=lambda x: x.get("weighted_change", 0), reverse=True)

    response = {
        "group_by": "theme",
        "data": results,
        "timestamp": time.time(),
        "total_tickers": len(ticker_lookup),
    }

    _result_cache[cache_key] = response
    _result_cache_ts[cache_key] = now
    return response


async def _get_drilldown(
    group_type: str,
    group_name: str,
    min_market_cap: Optional[int],
    sort_by: str,
    limit: int,
):
    snapshot = await _load_snapshot()
    classifications = await _load_classifications()
    themes_map = await _load_themes()

    matched = []

    for t in snapshot:
        sym = t["symbol"]
        if t.get("security_type") in ("ETF", "ETN"):
            continue
        if min_market_cap and (t.get("market_cap") or 0) < min_market_cap:
            continue

        if group_type == "theme":
            sym_themes = themes_map.get(sym, [])
            if any(th["theme"] == group_name for th in sym_themes):
                cls = classifications.get(sym, {})
                t["sector"] = cls.get("sector", "")
                t["industry"] = cls.get("industry", "")
                matched.append(t)
        else:
            cls = classifications.get(sym)
            if not cls:
                continue
            if cls.get(group_type) == group_name or cls.get("sector") == group_name:
                t["sector"] = cls.get("sector", "")
                t["industry"] = cls.get("industry", "")
                matched.append(t)

    reverse = sort_by != "symbol"
    matched.sort(key=lambda x: x.get(sort_by, 0) or 0, reverse=reverse)

    return {
        "group_type": group_type,
        "group_name": group_name,
        "data": matched[:limit],
        "total": len(matched),
    }
