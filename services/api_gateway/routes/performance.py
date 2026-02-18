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
_result_cache_ts: float = 0
RESULT_CACHE_TTL = 5


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
        total_dollar_volume += vol * price
        total_market_cap += mcap
        if rvol is not None and rvol > 0:
            rvols.append(rvol)

    n = len(tickers)
    avg_change = sum(changes) / len(changes) if changes else 0
    median_change = sorted(changes)[len(changes) // 2] if changes else 0
    breadth = advancing / n if n > 0 else 0
    avg_rvol = sum(rvols) / len(rvols) if rvols else 0

    mcap_weighted_change = 0.0
    if total_market_cap > 0:
        for t in tickers:
            chg = t.get("change_percent", 0) or 0
            mcap = t.get("market_cap", 0) or 0
            mcap_weighted_change += chg * (mcap / total_market_cap)

    return {
        "count": n,
        "advancing": advancing,
        "declining": declining,
        "unchanged": n - advancing - declining,
        "breadth": round(breadth, 4),
        "avg_change": round(avg_change, 2),
        "median_change": round(median_change, 2),
        "weighted_change": round(mcap_weighted_change, 2),
        "avg_rvol": round(avg_rvol, 2),
        "total_volume": total_volume,
        "total_dollar_volume": round(total_dollar_volume, 0),
        "total_market_cap": round(total_market_cap, 0),
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
        "change_percent": round(t.get("change_percent", 0), 2),
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
            tickers.append({
                "symbol": symbol,
                "price": t.get("price") or t.get("current_price") or (t.get("lastTrade") or {}).get("p"),
                "change_percent": t.get("change_percent") or t.get("todaysChangePerc"),
                "volume": t.get("volume") or t.get("current_volume") or (t.get("day") or {}).get("v", 0),
                "market_cap": t.get("market_cap", 0),
                "rvol": t.get("rvol"),
                "security_type": t.get("security_type"),
            })
        except Exception:
            continue

    return tickers


async def _get_performance(
    group_by: str,
    min_market_cap: Optional[int],
    include_movers: bool,
    sector_filter: Optional[str] = None,
):
    global _result_cache, _result_cache_ts

    cache_key = f"{group_by}:{min_market_cap}:{include_movers}:{sector_filter}"
    now = time.time()
    if cache_key in _result_cache and (now - _result_cache_ts) < RESULT_CACHE_TTL:
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
    _result_cache_ts = now
    return response


async def _get_theme_performance(
    min_market_cap: Optional[int],
    min_tickers: int,
    include_movers: bool,
):
    global _result_cache, _result_cache_ts

    cache_key = f"themes:{min_market_cap}:{min_tickers}:{include_movers}"
    now = time.time()
    if cache_key in _result_cache and (now - _result_cache_ts) < RESULT_CACHE_TTL:
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
    _result_cache_ts = now
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
