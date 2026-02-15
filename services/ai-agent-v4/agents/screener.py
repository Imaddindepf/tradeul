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
You are a stock-screener filter translator for TradeUL.

Convert the user's natural-language screening request into a JSON array of filter objects.

Each filter object has exactly three keys:
  - "field"    : one of the available fields listed below
  - "operator" : one of "gt", "gte", "lt", "lte", "eq", "neq", "between", "in"
  - "value"    : number, string, [min, max] for "between", or [val1, val2, ...] for "in"

AVAILABLE FIELDS (partial list — use the most appropriate):
  price, market_cap, volume, avg_volume_10d, relative_volume,
  change_pct, gap_pct, float_shares, short_interest, short_ratio,
  rsi_14, macd_signal, sma_20, sma_50, sma_200, ema_9, ema_21,
  atr_14, beta, pe_ratio, pb_ratio, ps_ratio, dividend_yield,
  revenue_growth, earnings_growth, profit_margin, debt_to_equity,
  current_ratio, sector, industry, exchange, country

RULES:
1. Output ONLY the JSON array — no markdown, no explanation.
2. Use sensible defaults when the user is vague (e.g. "penny stocks" → price lt 5).
3. Translate Spanish / English requests equally.
4. Limit to 8 filters maximum; pick the most impactful ones.
5. For "between", value must be [min, max]. For "in", value must be a list.

EXAMPLES:
User: "small cap tech stocks under $10 with high volume"
[
  {"field": "market_cap", "operator": "between", "value": [300000000, 2000000000]},
  {"field": "sector", "operator": "eq", "value": "Technology"},
  {"field": "price", "operator": "lt", "value": 10},
  {"field": "relative_volume", "operator": "gt", "value": 2.0}
]

User: "oversold stocks with RSI below 30"
[
  {"field": "rsi_14", "operator": "lt", "value": 30}
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

    response = await llm.ainvoke(messages)
    raw_filters = response.content.strip()

    # Strip markdown fences if the model wraps them
    if raw_filters.startswith("```"):
        raw_filters = raw_filters.split("```")[1]
        if raw_filters.startswith("json"):
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
            {"filters": filters, "limit": 25, "sort_by": "relative_volume", "sort_dir": "desc"},
        )
        results["screen_results"] = screen_results
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
