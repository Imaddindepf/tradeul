"""
News & Events Agent - Benzinga news, market events, and earnings calendar.

MCP tools used:
  - news.get_news_by_ticker      → ticker-specific Benzinga news
  - news.get_latest_news          → general / broad market news
  - events.get_events_by_ticker   → breakouts, VWAP crosses, halts for a ticker
  - events.get_earnings_calendar  → upcoming / recent earnings
"""
from __future__ import annotations
import re
import time
from typing import Any

from agents._mcp_tools import call_mcp_tool


# ── Ticker extraction (shared pattern) ──────────────────────────
_TICKER_RE = re.compile(r'(?<!\w)\$?([A-Z]{1,5})(?:\s|$|[,;.!?\)])')

_STOPWORDS = {
    "I", "A", "AM", "PM", "US", "CEO", "FDA", "SEC", "IPO", "ETF",
    "GDP", "CPI", "ATH", "DD", "EPS", "PE", "API", "AI", "IT", "IS",
    "ARE", "THE", "AND", "FOR", "TOP", "ALL", "BUY", "GET", "HAS",
    "NEW", "NOW", "HOW", "WHY", "UP", "DE", "LA", "EL", "EN", "ES",
    "LOS", "LAS", "QUE", "POR", "MAS", "CON", "UNA", "DEL", "DIA",
    "HOY", "LOW", "HIGH", "NEWS",
}


def _extract_tickers(query: str) -> list[str]:
    explicit = re.findall(r'\$([A-Z]{1,5})\b', query.upper())
    implicit = _TICKER_RE.findall(query.upper())
    combined = list(dict.fromkeys(explicit + implicit))
    return [t for t in combined if t not in _STOPWORDS]


# ── Earnings keywords ───────────────────────────────────────────
_EARNINGS_KEYWORDS = [
    "earnings", "earning", "er ", "eps", "revenue",
    "quarterly", "quarter", "q1", "q2", "q3", "q4",
    "beat", "miss", "guidance", "forecast",
    "resultados", "ganancias", "trimestral",
]


def _wants_earnings(query: str) -> bool:
    q_lower = query.lower()
    return any(kw in q_lower for kw in _EARNINGS_KEYWORDS)


async def news_events_node(state: dict) -> dict:
    """Fetch news and events via MCP tools."""
    start_time = time.time()

    query = state.get("query", "")
    tickers = _extract_tickers(query)
    check_earnings = _wants_earnings(query)

    results: dict[str, Any] = {}
    errors: list[str] = []

    if tickers:
        # ── Ticker-specific news & events ───────────────────────
        for ticker in tickers[:5]:  # cap to 5 tickers
            try:
                news = await call_mcp_tool(
                    "news",
                    "get_news_by_ticker",
                    {"ticker": ticker, "limit": 10},
                )
                results.setdefault("ticker_news", {})[ticker] = news
            except Exception as exc:
                errors.append(f"news/{ticker}: {exc}")

            try:
                events = await call_mcp_tool(
                    "events",
                    "get_events_by_ticker",
                    {"ticker": ticker, "limit": 10},
                )
                results.setdefault("ticker_events", {})[ticker] = events
            except Exception as exc:
                errors.append(f"events/{ticker}: {exc}")
    else:
        # ── General / broad market news ─────────────────────────
        try:
            latest = await call_mcp_tool(
                "news",
                "get_latest_news",
                {"limit": 15},
            )
            results["latest_news"] = latest
        except Exception as exc:
            errors.append(f"latest_news: {exc}")

    # ── Earnings calendar (if keywords detected) ────────────────
    if check_earnings:
        try:
            params: dict[str, Any] = {"limit": 20}
            if tickers:
                params["tickers"] = tickers[:5]
            earnings = await call_mcp_tool(
                "events",
                "get_earnings_calendar",
                params,
            )
            results["earnings"] = earnings
        except Exception as exc:
            errors.append(f"earnings: {exc}")

    if errors:
        results["_errors"] = errors

    elapsed_ms = int((time.time() - start_time) * 1000)

    return {
        "agent_results": {
            "news_events": {
                "tickers_detected": tickers,
                "earnings_checked": check_earnings,
                **results,
            },
        },
        "execution_metadata": {
            **(state.get("execution_metadata", {})),
            "news_events": {
                "elapsed_ms": elapsed_ms,
                "tickers": tickers,
                "earnings_checked": check_earnings,
                "error_count": len(errors),
            },
        },
    }
