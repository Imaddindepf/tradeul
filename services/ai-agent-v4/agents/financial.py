"""
Financial Agent - SEC financials, dilution analysis, and risk assessment.

MCP tools used (parameter names MUST match exactly):
  - financials.get_financial_statements(symbol, period, limit)
  - dilution.get_dilution_profile(ticker)
  - dilution.get_dilution_risk_ratings(ticker)   ← NOT "get_risk_ratings"
  - dilution.get_cash_runway(ticker)
  - sec.get_recent_filings(count, ticker)        ← uses 'count' NOT 'limit'
"""
from __future__ import annotations
import re
import time
from typing import Any

from agents._mcp_tools import call_mcp_tool
from agents._ticker_utils import extract_tickers as _extract_tickers


# ── Keyword detectors ────────────────────────────────────────────
_DILUTION_KEYWORDS = [
    "dilution", "diluted", "diluting", "warrants", "warrant",
    "offering", "shelf", "atm", "at-the-market", "shares outstanding",
    "float", "authorized shares", "convertible", "pipe",
    "dilucion", "dilución", "acciones",
]

_SEC_KEYWORDS = [
    "sec", "filing", "filings", "10-k", "10-q", "8-k", "s-1", "s-3",
    "424b", "proxy", "def 14a", "annual report", "quarterly report",
    "edgar", "prospectus",
]


def _wants_dilution(query: str) -> bool:
    q_lower = query.lower()
    return any(kw in q_lower for kw in _DILUTION_KEYWORDS)


def _wants_sec(query: str) -> bool:
    q_lower = query.lower()
    return any(kw in q_lower for kw in _SEC_KEYWORDS)


async def financial_node(state: dict) -> dict:
    """Fetch financial data, dilution analysis, and SEC filings via MCP."""
    start_time = time.time()

    query = state.get("query", "")
    tickers = _extract_tickers(query)

    results: dict[str, Any] = {}
    errors: list[str] = []

    # Guard: financial agent requires at least one ticker
    if not tickers:
        elapsed_ms = int((time.time() - start_time) * 1000)
        return {
            "agent_results": {
                "financial": {
                    "error": "No ticker detected. Please specify a stock symbol (e.g. $AAPL).",
                },
            },
            "execution_metadata": {
                **(state.get("execution_metadata", {})),
                "financial": {"elapsed_ms": elapsed_ms, "tickers": [], "error": "no_ticker"},
            },
        }

    check_dilution = _wants_dilution(query)
    check_sec = _wants_sec(query)

    for ticker in tickers[:3]:  # cap to 3 tickers for performance
        ticker_data: dict[str, Any] = {}

        # 1. Core financial statements (always fetched)
        #    MCP param: symbol (NOT ticker), period, limit
        try:
            financials = await call_mcp_tool(
                "financials",
                "get_financial_statements",
                {"symbol": ticker},
            )
            ticker_data["financial_statements"] = financials
        except Exception as exc:
            errors.append(f"financials/{ticker}: {exc}")

        # 2. Dilution analysis (if keywords detected)
        if check_dilution:
            try:
                profile = await call_mcp_tool(
                    "dilution",
                    "get_dilution_profile",
                    {"ticker": ticker},
                )
                ticker_data["dilution_profile"] = profile
            except Exception as exc:
                errors.append(f"dilution_profile/{ticker}: {exc}")

            try:
                risk = await call_mcp_tool(
                    "dilution",
                    "get_dilution_risk_ratings",
                    {"ticker": ticker},
                )
                ticker_data["dilution_risk"] = risk
            except Exception as exc:
                errors.append(f"dilution_risk_ratings/{ticker}: {exc}")

            try:
                runway = await call_mcp_tool(
                    "dilution",
                    "get_cash_runway",
                    {"ticker": ticker},
                )
                ticker_data["cash_runway"] = runway
            except Exception as exc:
                errors.append(f"cash_runway/{ticker}: {exc}")

        # 3. SEC filings (if keywords detected)
        #    MCP param: count (NOT limit), ticker
        if check_sec:
            try:
                filings = await call_mcp_tool(
                    "sec",
                    "get_recent_filings",
                    {"ticker": ticker, "count": 10},
                )
                ticker_data["sec_filings"] = filings
            except Exception as exc:
                errors.append(f"sec_filings/{ticker}: {exc}")

        results[ticker] = ticker_data

    if errors:
        results["_errors"] = errors

    elapsed_ms = int((time.time() - start_time) * 1000)

    return {
        "agent_results": {
            "financial": {
                "tickers_analyzed": tickers[:3],
                "dilution_checked": check_dilution,
                "sec_checked": check_sec,
                **results,
            },
        },
        "execution_metadata": {
            **(state.get("execution_metadata", {})),
            "financial": {
                "elapsed_ms": elapsed_ms,
                "tickers": tickers[:3],
                "dilution_checked": check_dilution,
                "sec_checked": check_sec,
                "error_count": len(errors),
            },
        },
    }
