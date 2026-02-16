"""
News & Events Agent - Benzinga news, market events, and earnings calendar.

MCP tools used:
  - news.get_news_by_ticker(symbol, count)        - ticker-specific Benzinga news
  - news.get_latest_news(count)                    - general / broad market news
  - events.get_events_by_ticker(symbol, count)     - breakouts, VWAP crosses, halts
  - earnings.get_earnings_by_ticker(ticker)        - earnings history for a ticker
  - earnings.get_today_earnings()                  - today's earnings calendar
  - earnings.get_upcoming_earnings(days)           - earnings next N days
  - earnings.get_earnings_by_date(date)            - earnings on a specific date

Data cleaning:
  - News: strip body (full article text), keep only metadata + teaser
  - Upcoming earnings: filter importance>=3, keep key fields only
  - Events: keep all (already small)
  - Earnings history: keep all (already small)
"""
from __future__ import annotations
import re
import time
from typing import Any

from agents._mcp_tools import call_mcp_tool


# -- Intent detection --

_EARNINGS_KEYWORDS = [
    "earnings", "earning", "er ", "eps", "revenue",
    "quarterly", "quarter", "q1", "q2", "q3", "q4",
    "beat", "miss", "guidance", "forecast",
    "resultados", "ganancias", "trimestral", "reportan", "reporta",
    "reportes", "reporte",
]

_NEWS_KEYWORDS = [
    "news", "noticias", "noticia", "headlines", "article",
    "happened", "paso", "pasado", "recientes",
]

_UPCOMING_KEYWORDS = [
    "upcoming", "next", "this week", "esta semana",
    "proxima", "siguiente", "tomorrow", "week",
    "semana", "proximos", "pronto",
]

_TODAY_KEYWORDS = [
    "today", "hoy", "today's",
]


def _wants_earnings(q: str) -> bool:
    return any(kw in q.lower() for kw in _EARNINGS_KEYWORDS)

def _wants_news(q: str) -> bool:
    return any(kw in q.lower() for kw in _NEWS_KEYWORDS)

def _earnings_timeframe(q: str) -> str:
    ql = q.lower()
    if any(kw in ql for kw in _UPCOMING_KEYWORDS):
        return "upcoming"
    if any(kw in ql for kw in _TODAY_KEYWORDS):
        return "today"
    return "general"

def _extract_days(q: str) -> int:
    match = re.search(r'(\d+)\s*(?:days?|dias?)', q.lower())
    if match:
        return min(max(int(match.group(1)), 1), 30)
    return 7


# -- Data cleaning --

_NEWS_KEEP_FIELDS = {"title", "author", "published", "url", "teaser", "tickers"}


def _clean_news(raw: Any) -> list[dict]:
    """Strip news articles to metadata-only."""
    items = raw
    if isinstance(raw, dict):
        items = raw.get("news", raw.get("articles", raw.get("data", [])))
    if not isinstance(items, list):
        return []

    cleaned = []
    for item in items:
        if not isinstance(item, dict):
            continue
        row = {}
        for k in _NEWS_KEEP_FIELDS:
            if k in item and item[k] is not None:
                row[k] = item[k]
        if row:
            cleaned.append(row)
    return cleaned


def _clean_events(raw: Any) -> list[dict]:
    """Clean events -- already small, just ensure it's a list."""
    if isinstance(raw, dict):
        items = raw.get("events", raw.get("data", []))
        return items if isinstance(items, list) else []
    if isinstance(raw, list):
        return raw
    return []


def _clean_earnings(raw: Any) -> Any:
    """Clean earnings -- already small, just pass through."""
    return raw


_UPCOMING_KEEP = {
    "ticker", "company_name", "date", "time", "fiscal_year", "fiscal_period",
    "estimated_eps", "actual_eps", "eps_surprise_percent",
    "estimated_revenue", "actual_revenue", "revenue_surprise_percent",
    "importance", "date_status",
}


def _clean_upcoming_earnings(raw: Any) -> dict:
    """Clean upcoming earnings: keep summary + trimmed results (key fields only)."""
    if not isinstance(raw, dict):
        return raw

    results = raw.get("results", [])
    cleaned = []
    for item in results:
        if not isinstance(item, dict):
            continue
        row = {k: v for k, v in item.items() if k in _UPCOMING_KEEP and v is not None}
        if row:
            cleaned.append(row)

    return {
        "count": raw.get("count", len(cleaned)),
        "start_date": raw.get("start_date"),
        "end_date": raw.get("end_date"),
        "by_date": raw.get("by_date", {}),
        "results": cleaned,
    }


# -- Main node --

async def news_events_node(state: dict) -> dict:
    """Fetch news, events, and earnings via MCP tools.

    Strategy:
      - Tickers present: fetch per-ticker news + events + earnings (if wanted)
      - No tickers, earnings wanted: use appropriate earnings calendar tool
      - No tickers, news wanted: fetch latest market news
      - Only fetch what the user actually asked for (don't mix irrelevant data)
    """
    start_time = time.time()

    query = state.get("query", "")
    tickers = state.get("tickers", [])
    wants_earn = _wants_earnings(query)
    wants_nws = _wants_news(query)

    results: dict[str, Any] = {}
    errors: list[str] = []

    # -- Per-ticker data --
    if tickers:
        for ticker in tickers[:5]:
            try:
                raw = await call_mcp_tool("news", "get_news_by_ticker", {"symbol": ticker, "count": 10})
                results.setdefault("ticker_news", {})[ticker] = _clean_news(raw)
            except Exception as exc:
                errors.append(f"news/{ticker}: {exc}")

            try:
                raw = await call_mcp_tool("events", "get_events_by_ticker", {"symbol": ticker, "count": 20})
                results.setdefault("ticker_events", {})[ticker] = _clean_events(raw)
            except Exception as exc:
                errors.append(f"events/{ticker}: {exc}")

        if wants_earn:
            for ticker in tickers[:5]:
                try:
                    raw = await call_mcp_tool("earnings", "get_earnings_by_ticker", {"ticker": ticker})
                    results.setdefault("ticker_earnings", {})[ticker] = _clean_earnings(raw)
                except Exception as exc:
                    errors.append(f"earnings/{ticker}: {exc}")

    # -- No tickers: calendar / general queries --
    else:
        if wants_earn:
            timeframe = _earnings_timeframe(query)

            if timeframe in ("upcoming", "general"):
                days = _extract_days(query)
                try:
                    raw = await call_mcp_tool(
                        "earnings",
                        "get_upcoming_earnings",
                        {"days": days, "min_importance": 3, "limit": 100},
                    )
                    results["upcoming_earnings"] = _clean_upcoming_earnings(raw)
                except Exception as exc:
                    errors.append(f"upcoming_earnings: {exc}")

            if timeframe == "today":
                try:
                    raw = await call_mcp_tool("earnings", "get_today_earnings", {})
                    results["today_earnings"] = raw
                except Exception as exc:
                    errors.append(f"today_earnings: {exc}")

        if wants_nws or not wants_earn:
            try:
                raw = await call_mcp_tool("news", "get_latest_news", {"count": 15})
                results["latest_news"] = _clean_news(raw)
            except Exception as exc:
                errors.append(f"latest_news: {exc}")

    if errors:
        results["_errors"] = errors

    elapsed_ms = int((time.time() - start_time) * 1000)

    return {
        "agent_results": {
            "news_events": {
                "tickers_detected": tickers,
                "earnings_checked": wants_earn,
                **results,
            },
        },
        "execution_metadata": {
            **(state.get("execution_metadata", {})),
            "news_events": {
                "elapsed_ms": elapsed_ms,
                "tickers": tickers,
                "earnings_checked": wants_earn,
                "error_count": len(errors),
            },
        },
    }
