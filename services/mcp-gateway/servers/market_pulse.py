"""
MCP Server: Market Pulse
Composable analytical tool for sector, industry, and theme performance.

Exposes a single `analyze_market` tool that accepts a structured query schema,
enabling the AI agent to answer complex market questions in a single call:
  - Sector/industry/theme rankings with filters
  - Multi-segment comparison (e.g., big caps vs small caps)
  - Drilldown into specific groups
  - Conditional screening on aggregated metrics

Data source: API Gateway /api/v1/performance/* endpoints, which aggregate
the enriched Redis snapshot with GICS classification and thematic data.
"""
from fastmcp import FastMCP
from clients.http_client import service_get
from config import config
from typing import Optional
import logging

logger = logging.getLogger(__name__)

mcp = FastMCP(
    "Tradeul Market Pulse",
    instructions=(
        "Real-time market pulse analytics: sector, industry, and theme performance. "
        "Use analyze_market for composable queries comparing segments, filtering by "
        "market cap, and drilling down into specific groups. Supports multi-query "
        "execution in a single call for minimal latency."
    ),
)

# Metrics the AI agent can sort/filter on
SORTABLE_METRICS = [
    "weighted_change", "avg_change", "median_change", "breadth",
    "avg_rvol", "total_dollar_volume", "total_market_cap",
    "avg_rsi", "avg_daily_rsi", "avg_atr_pct", "avg_gap_pct",
    "avg_adx", "avg_daily_adx", "avg_dist_vwap",
    "avg_change_5d", "avg_change_10d", "avg_change_20d",
    "avg_from_52w_high", "avg_from_52w_low",
    "avg_pos_in_range", "avg_bb_position",
    "avg_dist_sma20", "avg_dist_sma50", "avg_vol_today_pct",
    "count",
]

# Cap size presets (market cap thresholds)
CAP_PRESETS = {
    "mega": 200_000_000_000,
    "large": 10_000_000_000,
    "mid": 2_000_000_000,
    "small": 300_000_000,
    "micro": 50_000_000,
}

# Compact field set returned per group to keep token count manageable
_COMPACT_FIELDS = {
    "name", "count", "advancing", "declining", "breadth",
    "avg_change", "median_change", "weighted_change",
    "avg_rvol", "total_dollar_volume", "total_market_cap",
    "avg_rsi", "avg_daily_rsi", "avg_atr_pct", "avg_gap_pct",
    "avg_adx", "avg_dist_vwap",
    "avg_change_5d", "avg_change_10d", "avg_change_20d",
    "avg_from_52w_high", "avg_from_52w_low",
    "avg_pos_in_range", "avg_bb_position",
    "avg_dist_sma20", "avg_dist_sma50",
    "movers",
}


def _compact(entry: dict) -> dict:
    """Strip an entry to the compact field set."""
    return {k: v for k, v in entry.items() if k in _COMPACT_FIELDS}


def _apply_metric_filters(data: list[dict], filters: list[dict]) -> list[dict]:
    """Filter entries by metric conditions.

    Each filter: {"metric": str, "op": "gt"|"gte"|"lt"|"lte", "value": float}
    """
    OPS = {
        "gt": lambda a, b: a > b,
        "gte": lambda a, b: a >= b,
        "lt": lambda a, b: a < b,
        "lte": lambda a, b: a <= b,
    }
    result = []
    for entry in data:
        passes = True
        for f in filters:
            metric = f.get("metric", "")
            op = f.get("op", "gt")
            value = f.get("value")
            if not metric or value is None or op not in OPS:
                continue
            actual = entry.get(metric)
            if actual is None:
                passes = False
                break
            try:
                if not OPS[op](float(actual), float(value)):
                    passes = False
                    break
            except (ValueError, TypeError):
                passes = False
                break
        if passes:
            result.append(entry)
    return result


async def _fetch_performance(
    group: str,
    min_market_cap: Optional[int] = None,
    sector: Optional[str] = None,
    include_movers: bool = False,
    min_tickers: int = 3,
) -> dict:
    """Fetch performance data from the API Gateway."""
    params = {}
    if min_market_cap:
        params["min_market_cap"] = str(min_market_cap)
    if include_movers:
        params["include_movers"] = "true"

    if group == "sectors":
        path = "/api/v1/performance/sectors"
    elif group == "industries":
        path = "/api/v1/performance/industries"
        if sector:
            params["sector"] = sector
    elif group == "themes":
        path = "/api/v1/performance/themes"
        params["min_tickers"] = str(min_tickers)
    else:
        return {"error": f"Invalid group: {group}. Use: sectors, industries, themes"}

    try:
        return await service_get(config.api_gateway_url, path, params=params)
    except Exception as e:
        logger.error("Market Pulse fetch error for %s: %s", group, e)
        return {"error": str(e), "data": []}


async def _fetch_drilldown(
    group_type: str,
    group_name: str,
    min_market_cap: Optional[int] = None,
    sort_by: str = "change_percent",
    limit: int = 20,
) -> dict:
    """Fetch drilldown data for a specific group."""
    params = {"sort_by": sort_by, "limit": str(limit)}
    if min_market_cap:
        params["min_market_cap"] = str(min_market_cap)

    import urllib.parse
    encoded = urllib.parse.quote(group_name, safe="")
    path = f"/api/v1/performance/drilldown/{group_type}/{encoded}"

    try:
        return await service_get(config.api_gateway_url, path, params=params)
    except Exception as e:
        logger.error("Drilldown fetch error for %s/%s: %s", group_type, group_name, e)
        return {"error": str(e), "data": []}


@mcp.tool()
async def analyze_market(
    queries: list[dict],
    compare: bool = False,
    metrics: list[str] | None = None,
    drilldown: dict | None = None,
) -> dict:
    """Composable market analysis tool. Execute multiple analytical queries in one call.

    Each query in the `queries` array is a dict with:
      - group: "sectors" | "industries" | "themes"
      - sort_by: metric to sort by (default: "weighted_change")
      - limit: max results (default: 15)
      - min_market_cap: minimum market cap filter (int, e.g. 10000000000 for 10B)
      - cap_size: shorthand for min_market_cap ("mega", "large", "mid", "small", "micro")
      - sector: filter industries by sector name (only for group="industries")
      - include_movers: include top gainers/losers per group (default: false)
      - min_tickers: minimum tickers per theme (default: 3, only for themes)
      - metric_filters: conditional filters on aggregated metrics, list of:
          {"metric": str, "op": "gt"|"gte"|"lt"|"lte", "value": float}
          Example: [{"metric": "breadth", "op": "gt", "value": 0.6},
                    {"metric": "avg_rvol", "op": "gt", "value": 1.5}]
      - label: optional label for this query (used in compare mode)

    Set compare=true to return results side-by-side (useful for big-cap vs small-cap).

    Set metrics to limit which fields are returned per entry (reduces token count).
    Available: weighted_change, avg_change, median_change, breadth, avg_rvol,
    total_dollar_volume, total_market_cap, avg_rsi, avg_daily_rsi, avg_atr_pct,
    avg_gap_pct, avg_adx, avg_dist_vwap, avg_change_5d, avg_change_10d,
    avg_change_20d, avg_from_52w_high, avg_from_52w_low, avg_pos_in_range,
    avg_bb_position, avg_dist_sma20, avg_dist_sma50, avg_vol_today_pct, count.

    Set drilldown to dig into a specific result:
      - from_query: index of the query to drill into (0-based)
      - rank: which result to drill into (1 = top result)
      - sort_by: metric to sort tickers by (default: "change_percent")
      - limit: max tickers (default: 10)

    Examples:
      1) Top 10 themes by weighted change in big caps:
         queries=[{"group":"themes","min_market_cap":10000000000,"limit":10}]

      2) Compare themes in big-caps vs small-caps:
         queries=[
           {"group":"themes","cap_size":"large","limit":10,"label":"big_caps"},
           {"group":"themes","cap_size":"small","limit":10,"label":"small_caps"}
         ], compare=true

      3) Sectors with breadth > 60% and RVOL > 1.5:
         queries=[{"group":"sectors","metric_filters":[
           {"metric":"breadth","op":"gt","value":0.6},
           {"metric":"avg_rvol","op":"gt","value":1.5}
         ]}]

      4) Top theme + drilldown to its best RSI stocks:
         queries=[{"group":"themes","cap_size":"large","limit":5}],
         drilldown={"from_query":0,"rank":1,"sort_by":"daily_rsi","limit":5}
    """
    import asyncio

    if not queries:
        return {"error": "At least one query is required"}

    if len(queries) > 5:
        return {"error": "Maximum 5 queries per call"}

    selected_metrics = set(metrics) if metrics else None

    # Execute all queries in parallel
    async def _exec_query(idx: int, q: dict) -> dict:
        group = q.get("group", "sectors")
        sort_by = q.get("sort_by", "weighted_change")
        limit = q.get("limit", 15)
        label = q.get("label", f"query_{idx}")
        include_movers = q.get("include_movers", False)
        min_tickers = q.get("min_tickers", 3)
        sector = q.get("sector")
        metric_filters = q.get("metric_filters", [])

        min_market_cap = q.get("min_market_cap")
        cap_size = q.get("cap_size")
        if cap_size and cap_size in CAP_PRESETS and not min_market_cap:
            min_market_cap = CAP_PRESETS[cap_size]

        raw = await _fetch_performance(
            group=group,
            min_market_cap=min_market_cap,
            sector=sector,
            include_movers=include_movers,
            min_tickers=min_tickers,
        )

        data = raw.get("data", [])

        if metric_filters:
            data = _apply_metric_filters(data, metric_filters)

        reverse = sort_by not in ("avg_from_52w_high",)
        data.sort(key=lambda x: x.get(sort_by, 0) or 0, reverse=reverse)
        data = data[:limit]

        compacted = []
        for entry in data:
            c = _compact(entry)
            if selected_metrics:
                c = {k: v for k, v in c.items() if k in selected_metrics or k == "name"}
            compacted.append(c)

        return {
            "label": label,
            "group": group,
            "sort_by": sort_by,
            "cap_filter": cap_size or (f"min_{min_market_cap}" if min_market_cap else "all"),
            "count": len(compacted),
            "total_available": len(raw.get("data", [])),
            "data": compacted,
        }

    results = await asyncio.gather(*[_exec_query(i, q) for i, q in enumerate(queries)])
    results = list(results)

    # Drilldown
    drilldown_result = None
    if drilldown:
        from_query = drilldown.get("from_query", 0)
        rank = drilldown.get("rank", 1)
        dd_sort = drilldown.get("sort_by", "change_percent")
        dd_limit = drilldown.get("limit", 10)

        if 0 <= from_query < len(results):
            source = results[from_query]
            source_data = source.get("data", [])
            if 0 < rank <= len(source_data):
                target_name = source_data[rank - 1].get("name", "")
                target_group = source.get("group", "sectors")
                group_type_map = {"sectors": "sector", "industries": "industry", "themes": "theme"}
                dd_group_type = group_type_map.get(target_group, target_group)

                dd_min_cap = None
                for q in queries:
                    if q.get("cap_size") and q["cap_size"] in CAP_PRESETS:
                        dd_min_cap = CAP_PRESETS[q["cap_size"]]
                    elif q.get("min_market_cap"):
                        dd_min_cap = q["min_market_cap"]

                dd_raw = await _fetch_drilldown(
                    group_type=dd_group_type,
                    group_name=target_name,
                    min_market_cap=dd_min_cap,
                    sort_by=dd_sort,
                    limit=dd_limit,
                )

                dd_data = dd_raw.get("data", [])
                dd_compact = []
                for t in dd_data:
                    dd_compact.append({
                        "symbol": t.get("symbol"),
                        "price": t.get("price"),
                        "change_percent": t.get("change_percent"),
                        "volume": t.get("volume"),
                        "market_cap": t.get("market_cap"),
                        "rvol": t.get("rvol"),
                        "sector": t.get("sector"),
                        "industry": t.get("industry"),
                        dd_sort: t.get(dd_sort),
                    })

                drilldown_result = {
                    "group_type": dd_group_type,
                    "group_name": target_name,
                    "sort_by": dd_sort,
                    "total": dd_raw.get("total", 0),
                    "tickers": dd_compact,
                }

    response: dict = {"results": results}

    if compare and len(results) >= 2:
        all_names = set()
        for r in results:
            for entry in r.get("data", []):
                all_names.add(entry.get("name"))

        comparison = {}
        for name in all_names:
            comparison[name] = {}
            for r in results:
                label = r.get("label", "?")
                match = next((e for e in r.get("data", []) if e.get("name") == name), None)
                if match:
                    comparison[name][label] = {
                        k: v for k, v in match.items()
                        if k != "name" and k != "movers"
                    }

        response["comparison"] = comparison

    if drilldown_result:
        response["drilldown"] = drilldown_result

    return response


@mcp.tool()
async def get_market_regime() -> dict:
    """Detect current market regime based on sector rotation patterns.

    Returns regime classification (risk_on, risk_off, mixed, rotational)
    with supporting evidence from sector performance data.

    Uses sector breadth, leadership patterns, and defensive vs cyclical
    sector performance to classify the current market environment.
    """
    raw = await _fetch_performance("sectors", include_movers=False)
    data = raw.get("data", [])
    if not data:
        return {"regime": "unknown", "reason": "No sector data available"}

    cyclical = {"Information Technology", "Consumer Discretionary", "Industrials",
                "Communication Services", "Financials", "Materials"}
    defensive = {"Utilities", "Consumer Staples", "Health Care", "Real Estate", "Energy"}

    cyc_changes = []
    def_changes = []
    breadths = []
    total_advancing = 0
    total_count = 0

    sector_summary = []
    for s in data:
        name = s.get("name", "")
        wc = s.get("weighted_change", 0) or 0
        br = s.get("breadth", 0) or 0
        adv = s.get("advancing", 0)
        cnt = s.get("count", 0)

        sector_summary.append({
            "sector": name,
            "weighted_change": round(wc, 4),
            "breadth": round(br, 4),
            "avg_rvol": round(s.get("avg_rvol", 0) or 0, 2),
        })

        if name in cyclical:
            cyc_changes.append(wc)
        elif name in defensive:
            def_changes.append(wc)

        breadths.append(br)
        total_advancing += adv
        total_count += cnt

    avg_cyc = sum(cyc_changes) / max(len(cyc_changes), 1)
    avg_def = sum(def_changes) / max(len(def_changes), 1)
    overall_breadth = total_advancing / max(total_count, 1)
    avg_breadth = sum(breadths) / max(len(breadths), 1)

    spread = avg_cyc - avg_def

    if spread > 0.5 and overall_breadth > 0.55:
        regime = "risk_on"
        desc = "Cyclical sectors leading with broad participation"
    elif spread < -0.5 and overall_breadth < 0.45:
        regime = "risk_off"
        desc = "Defensive sectors leading, narrow breadth"
    elif abs(spread) < 0.3 and avg_breadth > 0.45:
        regime = "mixed"
        desc = "No clear rotation direction, balanced participation"
    else:
        regime = "rotational"
        desc = "Active sector rotation, selective participation"

    return {
        "regime": regime,
        "description": desc,
        "overall_breadth": round(overall_breadth, 4),
        "cyclical_avg_change": round(avg_cyc, 4),
        "defensive_avg_change": round(avg_def, 4),
        "spread_cyc_vs_def": round(spread, 4),
        "sectors": sorted(sector_summary, key=lambda x: x["weighted_change"], reverse=True),
    }
