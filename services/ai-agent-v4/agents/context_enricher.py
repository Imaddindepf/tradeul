"""
Context Enricher — Auto-inject sector/industry/theme context for mentioned tickers.

Runs after all agents complete and before the Synthesizer.
Adds market_pulse_context to agent_results so the Synthesizer can reference
the broader market picture without the user explicitly asking.

Lightweight: only fires when tickers are present, skips for GREETING/RANKING-only.
"""
import asyncio
import logging
import time
from typing import Any

from agents._mcp_tools import call_mcp_tool

logger = logging.getLogger(__name__)


async def context_enricher_node(state: dict) -> dict:
    """Enrich agent results with sector/industry/theme context for mentioned tickers."""
    start = time.time()

    tickers = state.get("tickers", [])
    agent_results = state.get("agent_results", {})
    plan = state.get("plan", "")

    # Skip for greetings or when there's no substance to enrich
    if not agent_results or plan == "clarification_needed":
        return state

    # Collect market regime (always useful)
    regime_task = _fetch_regime()

    # If we have tickers, get their sector/theme positioning
    positioning_task = _fetch_ticker_positioning(tickers) if tickers else _noop()

    regime, positioning = await asyncio.gather(regime_task, positioning_task, return_exceptions=True)

    context: dict[str, Any] = {}

    if isinstance(regime, dict) and "error" not in regime:
        context["market_regime"] = regime

    if isinstance(positioning, dict) and positioning:
        context["ticker_positioning"] = positioning

    if not context:
        return state

    elapsed = int((time.time() - start) * 1000)
    logger.info("Context enricher: added %s keys in %dms", list(context.keys()), elapsed)

    return {
        "agent_results": {"_market_pulse_context": context},
        "execution_metadata": {
            **(state.get("execution_metadata", {})),
            "context_enricher": {"elapsed_ms": elapsed, "keys": list(context.keys())},
        },
    }


async def _noop():
    return {}


async def _fetch_regime() -> dict:
    """Fetch market regime from market_pulse MCP tool."""
    try:
        return await call_mcp_tool("market_pulse", "get_market_regime", {})
    except Exception as e:
        logger.warning("Regime fetch failed: %s", e)
        return {"error": str(e)}


async def _fetch_ticker_positioning(tickers: list[str]) -> dict:
    """For each ticker, determine its sector/industry/theme positioning.

    Returns a dict per ticker with:
      - sector + sector performance summary
      - top themes the ticker belongs to + their performance
    """
    if not tickers or len(tickers) > 5:
        return {}

    try:
        classification = await call_mcp_tool(
            "screener", "enrich_with_classification", {"symbols": tickers}
        )
    except Exception:
        return {}

    if not isinstance(classification, dict) or not classification:
        return {}

    unique_sectors = set()
    for sym, info in classification.items():
        if isinstance(info, dict) and info.get("sector"):
            unique_sectors.add(info["sector"])

    if not unique_sectors:
        return {}

    # Fetch sector performance for the relevant sectors
    try:
        sector_perf = await call_mcp_tool("market_pulse", "analyze_market", {
            "queries": [{"group": "sectors", "limit": 15}],
            "metrics": ["weighted_change", "breadth", "avg_rvol", "avg_change_5d"],
        })
    except Exception:
        sector_perf = {}

    sector_data = {}
    for result in (sector_perf.get("results") or []):
        for entry in result.get("data", []):
            if entry.get("name") in unique_sectors:
                sector_data[entry["name"]] = entry

    positioning = {}
    for sym in tickers:
        cls = classification.get(sym, {})
        if not isinstance(cls, dict):
            continue
        sector = cls.get("sector", "")
        sp = sector_data.get(sector, {})
        positioning[sym] = {
            "sector": sector,
            "industry": cls.get("industry", ""),
            "sector_performance": {
                "weighted_change": sp.get("weighted_change"),
                "breadth": sp.get("breadth"),
                "avg_rvol": sp.get("avg_rvol"),
            } if sp else None,
        }

    return positioning
