"""
Screener Agent - Natural-language stock screening via DuckDB.

Uses Gemini Flash to convert a human query into structured filter objects,
then calls the screener MCP tool:
  - screener.run_screen → executes filters against 60+ technical indicators
"""
from __future__ import annotations
import json
import time
from typing import Any

from langchain_core.messages import SystemMessage, HumanMessage

from agents._mcp_tools import call_mcp_tool
from agents._llm_retry import llm_invoke_with_retry


# ── Data cleaning ────────────────────────────────────────────────

# Base fields always included in cleaned results
_SCREEN_BASE = {"symbol", "price", "volume", "relative_volume", "market_cap", "sector"}

# Map filter field names to result column names worth including
_FILTER_FIELD_TO_RESULT = {
    "rsi_14": "rsi_14", "adx_14": "adx_14",
    "atr_14": "atr_14", "atr_percent": "atr_percent",
    "sma_20": "sma_20", "sma_50": "sma_50", "sma_200": "sma_200",
    "bb_upper": "bb_upper", "bb_lower": "bb_lower", "bb_width": "bb_width",
    "bb_position": "bb_position", "squeeze_on": "squeeze_on",
    "change_1d": "change_1d", "change_3d": "change_3d",
    "change_5d": "change_5d", "change_10d": "change_10d", "change_20d": "change_20d",
    "high_52w": "high_52w", "low_52w": "low_52w",
    "from_52w_high": "from_52w_high", "from_52w_low": "from_52w_low",
    "free_float": "free_float", "gap_percent": "gap_percent",
}


def _clean_screen_results(raw: Any, filters: list[dict]) -> dict:
    """Clean screener results: keep base fields + filter-relevant fields only.
    40 raw fields → ~10-12 essential fields per item.
    """
    if not isinstance(raw, dict):
        return raw

    # Determine which extra fields to include based on filters used
    extra_fields = set()
    for f in filters:
        field = f.get("field", "")
        if field in _FILTER_FIELD_TO_RESULT:
            extra_fields.add(_FILTER_FIELD_TO_RESULT[field])

    keep_fields = _SCREEN_BASE | extra_fields

    items = raw.get("results", [])
    cleaned = []
    for item in items:
        if not isinstance(item, dict):
            continue
        row = {}
        for k in keep_fields:
            if k in item and item[k] is not None:
                # Round floats to 2 decimal places for readability
                v = item[k]
                if isinstance(v, float):
                    v = round(v, 2)
                row[k] = v
        if row:
            cleaned.append(row)

    return {
        "count": raw.get("count", len(cleaned)),
        "total_matched": raw.get("total_matched", len(cleaned)),
        "results": cleaned,
    }

# ── Lazy LLM singleton ──────────────────────────────────────────
_llm = None


def _get_llm():
    global _llm
    if _llm is None:
        from langchain_google_genai import ChatGoogleGenerativeAI
        _llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            temperature=0.0,
            max_output_tokens=1024,
        )
    return _llm


FILTER_PROMPT = """\
You are a stock-screener filter translator for Tradeul.

Convert the user's natural-language screening request into a JSON array of filter objects.

Each filter object has exactly three keys:
  - "field"    : one of the AVAILABLE FIELDS listed below (ONLY these work)
  - "operator" : one of "gt", "lt", "gte", "lte", "eq", "neq", "between"
  - "value"    : number or [min, max] for "between"

AVAILABLE FIELDS (ONLY these fields exist — do NOT invent field names):
  # Price & Volume
  price            - Current price (NOT "close", "open", "high", "low")
  volume           - Today's trading volume
  relative_volume  - RVOL: volume vs avg. >2 = high, >5 = very high
  gap_percent      - Gap % from previous close
  
  # Technical Indicators
  rsi_14           - RSI 14-period (0-100). <30 oversold, >70 overbought
  adx_14           - ADX trend strength. >25 = trending
  atr_14           - Average True Range (absolute)
  atr_percent      - ATR as % of price (volatility measure)
  sma_20           - 20-day simple moving average
  sma_50           - 50-day simple moving average
  sma_200          - 200-day simple moving average
  bb_upper         - Bollinger Band upper
  bb_middle        - Bollinger Band middle
  bb_lower         - Bollinger Band lower
  bb_width         - BB width (squeeze detection: narrow = squeeze)
  bb_position      - Price position within BBands (0-100)
  squeeze_on       - Bollinger/Keltner squeeze active (0 or 1)
  squeeze_momentum - Squeeze momentum value
  
  # Price Changes
  change_1d        - 1-day change %
  change_3d        - 3-day change %
  change_5d        - 5-day change %
  change_10d       - 10-day change %
  change_20d       - 20-day change %
  
  # Range
  high_52w         - 52-week high price
  low_52w          - 52-week low price
  from_52w_high    - Distance from 52-week high (negative %)
  from_52w_low     - Distance from 52-week low (positive %)
  
  # Fundamentals
  market_cap       - Market capitalization in USD
  free_float       - Free float shares
  sector           - Sector name (string, use "=" operator)

NOT AVAILABLE (do NOT use): close, open, high, low, vwap, dollar_volume,
  macd_*, ema_*, stoch_*, obv, rsi_7, sma_5, sma_10, industry, float_shares

RULES:
1. Output ONLY the JSON array — no markdown, no explanation.
2. Use sensible defaults (e.g. "penny stocks" → price < 5, "oversold" → rsi_14 < 30).
3. Translate Spanish / English equally.
4. Maximum 6 filters — pick the most impactful.
5. For price use "price" NOT "close".
6. For % change: change_1d (today), change_3d, change_5d (week), change_10d, change_20d (month).
7. For volume screening use relative_volume (RVOL), not raw volume.
8. For Bollinger squeeze use squeeze_on = 1 or bb_width < small_value.
9. For sector filtering use "=" with standard sector names (e.g., "Technology", "Healthcare").

EXAMPLES:
User: "small cap stocks under $10 with high volume"
[
  {"field": "market_cap", "operator": "between", "value": [300000000, 2000000000]},
  {"field": "price", "operator": "lt", "value": 10},
  {"field": "relative_volume", "operator": "gt", "value": 2.0}
]

User: "oversold stocks bouncing"
[
  {"field": "rsi_14", "operator": "lt", "value": 30},
  {"field": "relative_volume", "operator": "gt", "value": 1.5}
]

User: "Bollinger squeeze with trending ADX"
[
  {"field": "bb_width", "operator": "lt", "value": 5},
  {"field": "adx_14", "operator": "gt", "value": 25}
]
"""


async def screener_node(state: dict) -> dict:
    """Translate natural language to screener filters and run the screen."""
    llm = _get_llm()
    start_time = time.time()

    query = state.get("query", "")
    results: dict[str, Any] = {}
    errors: list[str] = []

    # ── Step 1: Convert query → filter objects via Gemini ────────
    messages = [
        SystemMessage(content=FILTER_PROMPT),
        HumanMessage(content=query),
    ]

    response = await llm_invoke_with_retry(llm, messages)
    raw_filters = response.content.strip()

    # Strip markdown fences if the model wraps them (case-insensitive)
    if raw_filters.startswith("```"):
        raw_filters = raw_filters.split("```")[1]
        if raw_filters.lower().startswith("json"):
            raw_filters = raw_filters[4:]
        raw_filters = raw_filters.strip()

    try:
        filters = json.loads(raw_filters)
        if not isinstance(filters, list):
            raise ValueError("Expected a JSON array of filter objects")
    except (json.JSONDecodeError, ValueError) as exc:
        elapsed_ms = int((time.time() - start_time) * 1000)
        return {
            "agent_results": {
                "screener": {
                    "error": f"Failed to parse filters from LLM: {exc}",
                    "raw_output": raw_filters[:500],
                },
            },
            "execution_metadata": {
                **(state.get("execution_metadata", {})),
                "screener": {"elapsed_ms": elapsed_ms, "error": "filter_parse"},
            },
        }

    results["filters_generated"] = filters

    # ── Step 2: Call screener MCP tool ───────────────────────────
    try:
        screen_results = await call_mcp_tool(
            "screener",
            "run_screen",
            {
                "filters": filters,
                "limit": 50,
                "sort_by": "relative_volume",
                "sort_order": "desc",
            },
        )
        results["screen_results"] = _clean_screen_results(screen_results, filters)
    except Exception as exc:
        errors.append(f"screener/run_screen: {exc}")

    if errors:
        results["_errors"] = errors

    elapsed_ms = int((time.time() - start_time) * 1000)

    return {
        "agent_results": {
            "screener": {
                "query_interpreted": query,
                "filters_count": len(filters),
                **results,
            },
        },
        "execution_metadata": {
            **(state.get("execution_metadata", {})),
            "screener": {
                "elapsed_ms": elapsed_ms,
                "filters_count": len(filters),
                "error_count": len(errors),
            },
        },
    }
