"""
Market Data Agent - Real-time scanner snapshots and enriched ticker data.

Uses MCP tools from the scanner service:
  - scanner.get_enriched_batch   → enriched data for specific tickers
  - scanner.get_scanner_snapshot → top movers / gappers / volume leaders
  - scanner.get_market_session   → current market session info
  - scanner.get_enriched_ticker  → full 100+ indicator snapshot for one ticker
"""
from __future__ import annotations
import re
import time
from typing import Any

from agents._mcp_tools import call_mcp_tool
from agents._ticker_utils import extract_tickers as _extract_tickers


# ── Category mapping ─────────────────────────────────────────────
# Maps user intent keywords → actual scanner categories
_CATEGORY_MAP: dict[str, list[str]] = {
    # Gainers / Winners
    "winners":    ["winners"],
    "gainers":    ["winners"],
    "ganadoras":  ["winners"],
    "mejores":    ["winners"],
    "top":        ["winners"],
    "best":       ["winners"],
    "subiendo":   ["winners"],
    # Losers
    "losers":     ["losers"],
    "perdedoras": ["losers"],
    "peores":     ["losers"],
    "worst":      ["losers"],
    "bajando":    ["losers"],
    "caidas":     ["losers"],
    # Gappers
    "gapper":     ["gappers_up", "gappers_down"],
    "gap up":     ["gappers_up"],
    "gap down":   ["gappers_down"],
    "gappers":    ["gappers_up"],
    "premarket":  ["gappers_up", "gappers_down"],
    # Momentum
    "momentum":   ["momentum_up"],
    "runners":    ["momentum_up"],
    "running":    ["momentum_up"],
    "movers":     ["momentum_up", "momentum_down"],
    # Volume
    "volume":     ["high_volume"],
    "volumen":    ["high_volume"],
    "vol":        ["high_volume"],
    # Halts
    "halt":       ["halts"],
    "halted":     ["halts"],
    "halts":      ["halts"],
    # Other
    "reversals":  ["reversals"],
    "anomalies":  ["anomalies"],
    "new highs":  ["new_highs"],
    "new lows":   ["new_lows"],
    "post market": ["post_market"],
    "after hours": ["post_market"],
}


def _detect_categories(query: str) -> list[str]:
    """Detect which scanner categories the user is asking about.
    Returns actual category names valid for the scanner."""
    q_lower = query.lower()
    categories: list[str] = []

    for keyword, cats in _CATEGORY_MAP.items():
        if keyword in q_lower:
            for c in cats:
                if c not in categories:
                    categories.append(c)

    return categories or ["winners"]  # default to winners


def _extract_limit(query: str) -> int:
    """Extract the requested limit from the query (e.g., 'top 50' → 50)."""
    match = re.search(r'\b(\d{1,3})\b', query)
    if match:
        n = int(match.group(1))
        if 1 <= n <= 200:
            return n
    return 25  # sensible default


async def market_data_node(state: dict) -> dict:
    """Fetch market data via MCP scanner tools."""
    start_time = time.time()

    query = state.get("query", "")
    tickers = _extract_tickers(query)
    categories = _detect_categories(query)
    limit = _extract_limit(query)

    results: dict[str, Any] = {}
    errors: list[str] = []

    # 1. Always get market session context
    try:
        session = await call_mcp_tool("scanner", "get_market_session", {})
        results["market_session"] = session
    except Exception as exc:
        errors.append(f"market_session: {exc}")

    # 2. If specific tickers requested → enriched batch
    if tickers:
        try:
            enriched = await call_mcp_tool(
                "scanner",
                "get_enriched_batch",
                {"symbols": tickers},
            )
            results["enriched"] = enriched
        except Exception as exc:
            errors.append(f"enriched_batch: {exc}")

    # 3. Scanner snapshot for each detected category
    for category in categories:
        try:
            snapshot = await call_mcp_tool(
                "scanner",
                "get_scanner_snapshot",
                {"category": category, "limit": limit},
            )
            results[f"snapshot_{category}"] = snapshot
        except Exception as exc:
            errors.append(f"snapshot_{category}: {exc}")

    if errors:
        results["_errors"] = errors

    elapsed_ms = int((time.time() - start_time) * 1000)

    return {
        "agent_results": {
            "market_data": {
                "tickers_detected": tickers,
                "categories": categories,
                "limit": limit,
                **results,
            },
        },
        "execution_metadata": {
            **(state.get("execution_metadata", {})),
            "market_data": {
                "elapsed_ms": elapsed_ms,
                "tickers": tickers,
                "categories": categories,
                "limit": limit,
                "error_count": len(errors),
            },
        },
    }
