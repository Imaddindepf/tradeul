"""
MCP Server: Strategy Scan Engine

Declarative event-sequence scanner over the real-time market_events store
(TimescaleDB, ~12M events/day, 240+ event types from the alert_engine).

Answers questions like:
  "which >$1B stocks crossed VWAP up after a long opening decline and
   closed above their open?"

as a single SQL execution:
  1. Build the day context per symbol from its event stream
     (open/close/low/high prices + timestamps, computed from the first/last
     events of the session — no parquet needed, works for TODAY in real time).
  2. Match a SEQUENCE of event steps, each anchored to session open, the
     opening low, or the previous step ("A happened, then B after it").
  3. Apply day-level metric conditions (close vs open, opening drop...).
  4. Return matched symbols WITH EVIDENCE: timestamp + price + VWAP of each
     step, day OHLC approximation, market cap, sector.
"""
from fastmcp import FastMCP
from clients.db_client import db_fetch
from typing import Optional
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import logging
import time

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

mcp = FastMCP(
    "Tradeul Strategy Scan",
    instructions=(
        "Event-sequence strategy scanner. Finds stocks whose intraday event "
        "stream matches a declarative setup spec (sequence of alert-engine "
        "events + day-level price conditions). Works in REAL TIME for today "
        "and historically (60-day retention)."
    ),
)

_SESSIONS = {
    "premarket": ((4, 0), (9, 30)),
    "regular": ((9, 30), (16, 0)),
    "afterhours": ((16, 0), (20, 0)),
    "all": ((4, 0), (20, 0)),
}

_DAY_METRICS = {
    # metric name -> SQL expression over the joined day/opening CTEs
    "open_price": "d.o_price",
    "close_price": "d.c_price",
    "low_price": "d.lo_price",
    "high_price": "d.hi_price",
    "close_vs_open_pct": "(d.c_price - d.o_price) / NULLIF(d.o_price, 0) * 100",
    "low_vs_open_pct": "(d.lo_price - d.o_price) / NULLIF(d.o_price, 0) * 100",
    "high_vs_open_pct": "(d.hi_price - d.o_price) / NULLIF(d.o_price, 0) * 100",
    "opening_drop_pct": "(o.olow_price - d.o_price) / NULLIF(d.o_price, 0) * 100",
    "market_cap": "d.mcap",
    "n_events": "d.n_events",
}

_OPS = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<=", "eq": "="}

# In-process cache for the dynamic event catalog (date -> (ts, rows))
_catalog_cache: dict = {}
_CATALOG_TTL = 600


def _resolve_date(date: str) -> str:
    now_et = datetime.now(ET)
    if date in ("today", "", None):
        return now_et.strftime("%Y-%m-%d")
    if date == "yesterday":
        d = now_et - timedelta(days=1)
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        return d.strftime("%Y-%m-%d")
    return date


def _session_window_utc(date_str: str, session: str) -> tuple[datetime, datetime]:
    (h1, m1), (h2, m2) = _SESSIONS.get(session, _SESSIONS["regular"])
    day = datetime.strptime(date_str, "%Y-%m-%d")
    start = datetime(day.year, day.month, day.day, h1, m1, tzinfo=ET)
    end = datetime(day.year, day.month, day.day, h2, m2, tzinfo=ET)
    return start.astimezone(UTC).replace(tzinfo=None), end.astimezone(UTC).replace(tzinfo=None)


@mcp.tool()
async def scan_day_setups(
    steps: list[dict],
    date: str = "today",
    session: str = "regular",
    day_conditions: Optional[list[dict]] = None,
    opening_minutes: int = 60,
    min_market_cap: Optional[float] = None,
    max_market_cap: Optional[float] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    sector: Optional[str] = None,
    sort_by: str = "close_vs_open_pct",
    sort_order: str = "desc",
    limit: int = 50,
) -> dict:
    """Scan the full universe for symbols whose intraday EVENT SEQUENCE and
    day-level price action match a declarative strategy spec. Real-time for
    today; historical up to 60 days.

    Args:
        steps: Ordered event-sequence steps. Each step:
            {
              "event_types": ["vwap_cross_up", ...],  # alert-engine event types (see get_event_catalog)
              "after": "session_open" | "opening_low" | "prev_step",  # anchor (default prev_step; first step defaults to session_open)
              "within_minutes": 90        # optional max minutes after the anchor
            }
            Example — "crossed VWAP up after the opening low":
            [{"event_types": ["vwap_cross_up"], "after": "opening_low"}]
        date: 'today', 'yesterday' or 'YYYY-MM-DD'
        session: 'regular' | 'premarket' | 'afterhours' | 'all'
        day_conditions: Day-level metric conditions, e.g.
            [{"metric": "opening_drop_pct", "op": "lte", "value": -2},
             {"metric": "close_vs_open_pct", "op": "gt", "value": 0}]
            Metrics: open_price, close_price, low_price, high_price,
            close_vs_open_pct, low_vs_open_pct, high_vs_open_pct,
            opening_drop_pct (low of first `opening_minutes` vs open), market_cap, n_events
        opening_minutes: Window defining the "opening" (default 60 min after session start)
        min_market_cap / max_market_cap: Market cap bounds in USD (e.g. 1e9)
        min_price / max_price: Price bounds at event time
        sector: Sector filter (partial match)
        sort_by: Any day metric (default close_vs_open_pct)
        sort_order: 'desc' | 'asc'
        limit: Max symbols returned (default 50, max 200)

    Returns matched symbols with full evidence: day open/close/low/high with
    timestamps, opening low, and the timestamp/price/vwap of every matched step.
    """
    t0 = time.time()
    limit = min(int(limit), 200)
    date_str = _resolve_date(date)
    ts_from, ts_to = _session_window_utc(date_str, session)

    if not steps or not isinstance(steps, list):
        return {"error": "steps must be a non-empty list of event-step objects"}

    params: list = [ts_from, ts_to]

    # ── Base event filters (applied to every event row scanned) ──
    ev_conds = ["ts >= $1", "ts < $2", "price > 0"]
    if min_market_cap is not None:
        params.append(float(min_market_cap))
        ev_conds.append(f"market_cap >= ${len(params)}")
    if max_market_cap is not None:
        params.append(float(max_market_cap))
        ev_conds.append(f"market_cap <= ${len(params)}")
    if min_price is not None:
        params.append(float(min_price))
        ev_conds.append(f"price >= ${len(params)}")
    if max_price is not None:
        params.append(float(max_price))
        ev_conds.append(f"price <= ${len(params)}")
    if sector:
        params.append(f"%{sector}%")
        ev_conds.append(f"sector ILIKE ${len(params)}")

    # ── Step CTEs (sequence matching) ──
    step_ctes = []
    step_joins = []
    step_selects = []
    prev_alias = None
    for i, step in enumerate(steps[:5]):
        etypes = step.get("event_types") or []
        if not etypes:
            return {"error": f"step {i}: event_types is required"}
        params.append([str(e).lower() for e in etypes])
        etypes_param = f"${len(params)}"

        after = step.get("after") or ("session_open" if i == 0 else "prev_step")
        alias = f"s{i}"

        if after == "opening_low":
            anchor_join = "JOIN opening o2 ON o2.symbol = e.symbol"
            anchor_ts = "o2.olow_ts"
        elif after == "prev_step" and prev_alias:
            anchor_join = f"JOIN {prev_alias} p ON p.symbol = e.symbol"
            anchor_ts = f"p.{prev_alias}_ts"
        else:  # session_open
            anchor_join = ""
            anchor_ts = None

        conds = [f"e.event_type = ANY({etypes_param})"]
        if anchor_ts:
            conds.append(f"e.ts > {anchor_ts}")
        within = step.get("within_minutes")
        if within and anchor_ts:
            conds.append(f"e.ts <= {anchor_ts} + interval '{int(within)} minutes'")
        elif within and not anchor_ts:
            conds.append(f"e.ts <= $1::timestamp + interval '{int(within)} minutes'")

        step_ctes.append(f"""
{alias} AS (
  SELECT DISTINCT ON (e.symbol) e.symbol,
         e.ts AS {alias}_ts, e.price AS {alias}_price,
         e.vwap AS {alias}_vwap, e.event_type AS {alias}_event
  FROM ev e
  {anchor_join}
  WHERE {' AND '.join(conds)}
  ORDER BY e.symbol, e.ts ASC
)""")
        step_joins.append(f"JOIN {alias} USING (symbol)")
        step_selects.append(
            f"{alias}.{alias}_ts, {alias}.{alias}_price, {alias}.{alias}_vwap, {alias}.{alias}_event"
        )
        prev_alias = alias

    # ── Day-condition WHERE clause ──
    having = []
    for cond in (day_conditions or []):
        metric = cond.get("metric")
        op = _OPS.get(cond.get("op", ""))
        val = cond.get("value")
        if metric not in _DAY_METRICS or op is None or val is None:
            return {"error": f"invalid day_condition: {cond}. Metrics: {list(_DAY_METRICS)}"}
        params.append(float(val))
        having.append(f"({_DAY_METRICS[metric]}) {op} ${len(params)}")

    sort_expr = _DAY_METRICS.get(sort_by, _DAY_METRICS["close_vs_open_pct"])
    order = "DESC" if sort_order.lower() != "asc" else "ASC"

    query = f"""
WITH ev AS (
  SELECT symbol, event_type, ts, price, vwap, rvol, market_cap, sector
  FROM market_events
  WHERE {' AND '.join(ev_conds)}
),
day AS (
  SELECT symbol,
    (ARRAY_AGG(price ORDER BY ts ASC))[1]  AS o_price,
    (ARRAY_AGG(price ORDER BY ts DESC))[1] AS c_price,
    MIN(price) AS lo_price,
    MAX(price) AS hi_price,
    MIN(ts) AS first_ts,
    MAX(ts) AS last_ts,
    MAX(market_cap) AS mcap,
    MAX(sector) AS sector,
    COUNT(*) AS n_events
  FROM ev
  GROUP BY symbol
  HAVING COUNT(*) >= 5
),
opening AS (
  SELECT e.symbol,
    MIN(e.price) AS olow_price,
    (ARRAY_AGG(e.ts ORDER BY e.price ASC, e.ts ASC))[1] AS olow_ts
  FROM ev e
  JOIN day d ON d.symbol = e.symbol
  WHERE e.ts <= d.first_ts + interval '{int(opening_minutes)} minutes'
  GROUP BY e.symbol
),
{','.join(step_ctes)}
SELECT d.symbol, d.o_price, d.c_price, d.lo_price, d.hi_price,
       d.first_ts, d.last_ts, d.mcap, d.sector, d.n_events,
       o.olow_price, o.olow_ts,
       ROUND(((d.c_price - d.o_price) / NULLIF(d.o_price,0) * 100)::numeric, 2) AS close_vs_open_pct,
       ROUND(((o.olow_price - d.o_price) / NULLIF(d.o_price,0) * 100)::numeric, 2) AS opening_drop_pct,
       {', '.join(step_selects)}
FROM day d
JOIN opening o USING (symbol)
{' '.join(step_joins)}
{('WHERE ' + ' AND '.join(having)) if having else ''}
ORDER BY {sort_expr} {order} NULLS LAST
LIMIT {limit}
"""

    try:
        rows = await db_fetch(query, *params, timeout=120)
    except Exception as e:
        logger.error("strategy scan failed: %s", e)
        return {"error": f"scan failed: {e}", "matches": [], "count": 0}

    matches = []
    for row in rows:
        item: dict = {}
        for k, v in row.items():
            if v is None:
                continue
            if isinstance(v, datetime):
                item[k] = v.replace(tzinfo=UTC).astimezone(ET).strftime("%H:%M:%S ET")
            elif hasattr(v, "quantize"):  # Decimal
                item[k] = float(v)
            else:
                item[k] = v
        matches.append(item)

    return {
        "date": date_str,
        "session": session,
        "spec": {
            "steps": steps,
            "day_conditions": day_conditions,
            "opening_minutes": opening_minutes,
            "min_market_cap": min_market_cap,
        },
        "matches": matches,
        "count": len(matches),
        "elapsed_ms": int((time.time() - t0) * 1000),
        "note": (
            "Prices are event-stream approximations (first/last/min/max event price "
            "in session). Step timestamps are exact alert-engine detections."
        ),
    }


@mcp.tool()
async def get_event_catalog(date: str = "today", min_count: int = 50) -> dict:
    """Get the LIVE catalog of event types actually firing on a given date,
    with occurrence counts and unique symbols. Use this to discover which
    event types are available for scan_day_setups (240+ types: VWAP crosses,
    ORB breakouts, candle patterns, SMA/MACD/stochastic crosses, halts,
    volume spikes, consolidations, double tops/bottoms, trailing stops...).

    Args:
        date: 'today', 'yesterday' or 'YYYY-MM-DD'
        min_count: Hide event types with fewer occurrences (default 50)
    """
    date_str = _resolve_date(date)
    cached = _catalog_cache.get(date_str)
    if cached and time.time() - cached[0] < _CATALOG_TTL:
        rows = cached[1]
    else:
        ts_from = datetime.strptime(date_str, "%Y-%m-%d")
        ts_to = ts_from + timedelta(days=1)
        try:
            rows = await db_fetch(
                """
                SELECT event_type, COUNT(*) AS occurrences, COUNT(DISTINCT symbol) AS symbols
                FROM market_events
                WHERE ts >= $1 AND ts < $2
                GROUP BY event_type
                ORDER BY occurrences DESC
                """,
                ts_from, ts_to, timeout=60,
            )
        except Exception as e:
            return {"error": f"catalog query failed: {e}"}
        _catalog_cache[date_str] = (time.time(), rows)

    # Merge human descriptions where we have them
    try:
        from servers.events import EVENT_TYPES as _DESC
    except Exception:
        _DESC = {}

    catalog = []
    for r in rows:
        if r["occurrences"] < min_count:
            continue
        entry = {
            "event_type": r["event_type"],
            "occurrences": r["occurrences"],
            "symbols": r["symbols"],
        }
        if r["event_type"] in _DESC:
            entry["description"] = _DESC[r["event_type"]]
        catalog.append(entry)

    return {"date": date_str, "event_types": catalog, "count": len(catalog)}
