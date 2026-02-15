"""
Market Data Agent - Real-time scanner snapshots and enriched ticker data.

Uses MCP tools from the scanner service:
  - scanner.get_enriched_batch   → enriched data for specific tickers
  - scanner.get_scanner_snapshot → top movers / gappers / volume leaders
  - scanner.get_market_session   → current market session info
"""
from __future__ import annotations
import re
import time
from typing import Any

from agents._mcp_tools import call_mcp_tool


# ── Ticker extraction ────────────────────────────────────────────
_TICKER_RE = re.compile(
    r'(?<!\w)\$?([A-Z]{1,5})(?:\s|$|[,;.!?\)])',
)

# Common English / Spanish words that look like tickers
_STOPWORDS = {
    "I", "A", "AM", "PM", "US", "CEO", "FDA", "SEC", "IPO", "ETF",
    "GDP", "CPI", "ATH", "DD", "EPS", "PE", "API", "AI", "IT", "IS",
    "ARE", "THE", "AND", "FOR", "TOP", "ALL", "BUY", "GET", "HAS",
    "NEW", "NOW", "HOW", "WHY", "UP", "DE", "LA", "EL", "EN", "ES",
    "LOS", "LAS", "QUE", "POR", "MAS", "CON", "UNA", "DEL", "DIA",
    "HOY", "LOW", "HIGH",
}


def _extract_tickers(query: str) -> list[str]:
    """Extract probable stock tickers from a user query."""
    # Explicit $TICKER mentions
    explicit = re.findall(r'\$([A-Z]{1,5})\b', query.upper())
    # Implicit ALL-CAPS words
    implicit = _TICKER_RE.findall(query.upper())
    combined = list(dict.fromkeys(explicit + implicit))  # dedupe, preserve order
    return [t for t in combined if t not in _STOPWORDS]


# ── Category keyword mapping ────────────────────────────────────
_CATEGORY_KEYWORDS = {
    "gappers": ["gapper", "gap up", "gap down", "premarket gap", "gapping"],
    "momentum": ["momentum", "runners", "running", "movers", "moving"],
    "volume": ["volume", "unusual volume", "high volume", "vol spike"],
    "halts": ["halt", "halted", "luld", "circuit breaker"],
    "top": ["top", "best", "biggest", "leading", "winners", "losers"],
}


def _detect_categories(query: str) -> list[str]:
    """Detect which scanner categories the user is asking about."""
    q_lower = query.lower()
    categories = []
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(kw in q_lower for kw in keywords):
            categories.append(category)
    return categories or ["top"]  # default to top movers


async def market_data_node(state: dict) -> dict:
    """Fetch market data via MCP scanner tools."""
    start_time = time.time()

    query = state.get("query", "")
    tickers = _extract_tickers(query)
    categories = _detect_categories(query)

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
                {"tickers": tickers},
            )
            results["enriched"] = enriched
        except Exception as exc:
            errors.append(f"enriched_batch: {exc}")

    # 3. Scanner snapshot for categories
    for category in categories:
        try:
            snapshot = await call_mcp_tool(
                "scanner",
                "get_scanner_snapshot",
                {"category": category, "limit": 15},
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
                **results,
            },
        },
        "execution_metadata": {
            **(state.get("execution_metadata", {})),
            "market_data": {
                "elapsed_ms": elapsed_ms,
                "tickers": tickers,
                "categories": categories,
                "error_count": len(errors),
            },
        },
    }
