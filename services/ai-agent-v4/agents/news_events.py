"""
News & Events Agent - Benzinga news, market events, and earnings calendar.

MCP tools used:
  - news.get_news_by_ticker(symbol, count)  - ticker-specific Benzinga news
  - news.get_latest_news(count)             - general / broad market news
  - events.get_events_by_ticker(symbol, count) - breakouts, VWAP crosses, halts
  - earnings.get_earnings_by_ticker(ticker)  - earnings history for a ticker
  - earnings.get_today_earnings()            - today's earnings calendar
"""
from __future__ import annotations
import time
from typing import Any

from agents._mcp_tools import call_mcp_tool
from agents._ticker_utils import extract_tickers as _extract_tickers


# -- Earnings keywords --
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
    """Fetch news and events via MCP tools.

    IMPORTANT: MCP tool parameter names must match exactly:
      - news tools use 'symbol' and 'count' (NOT 'ticker' / 'limit')
      - events tools use 'symbol' and 'count'
      - earnings tools use 'ticker'
    """
    start_time = time.time()

    query = state.get("query", "")
    tickers = _extract_tickers(query)
    check_earnings = _wants_earnings(query)

    results: dict[str, Any] = {}
    errors: list[str] = []

    if tickers:
        for ticker in tickers[:5]:
            # News: uses 'symbol' and 'count' params
            try:
                news = await call_mcp_tool(
                    "news", "get_news_by_ticker",
                    {"symbol": ticker, "count": 10},
                )
                results.setdefault("ticker_news", {})[ticker] = news
            except Exception as exc:
                errors.append(f"news/{ticker}: {exc}")

            # Events: uses 'symbol' and 'count' params
            try:
                events = await call_mcp_tool(
                    "events", "get_events_by_ticker",
                    {"symbol": ticker, "count": 20},
                )
                results.setdefault("ticker_events", {})[ticker] = events
            except Exception as exc:
                errors.append(f"events/{ticker}: {exc}")
    else:
        # General / broad market news: uses 'count' param
        try:
            latest = await call_mcp_tool(
                "news", "get_latest_news", {"count": 15},
            )
            results["latest_news"] = latest
        except Exception as exc:
            errors.append(f"latest_news: {exc}")

    # Earnings
    if check_earnings:
        if tickers:
            # Per-ticker earnings history: uses 'ticker' param
            for ticker in tickers[:5]:
                try:
                    earnings = await call_mcp_tool(
                        "earnings", "get_earnings_by_ticker",
                        {"ticker": ticker},
                    )
                    results.setdefault("ticker_earnings", {})[ticker] = earnings
                except Exception as exc:
                    errors.append(f"earnings/{ticker}: {exc}")
        else:
            # Today's earnings calendar
            try:
                today_earnings = await call_mcp_tool(
                    "earnings", "get_today_earnings", {},
                )
                results["today_earnings"] = today_earnings
            except Exception as exc:
                errors.append(f"today_earnings: {exc}")

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
