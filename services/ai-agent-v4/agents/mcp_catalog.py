"""
MCP Tool Catalog — Single source of truth for every MCP Gateway endpoint.

All (server, tool) pairs the agent can call live here. Agents import the
`MCP` namespace and invoke tools directly:

    from agents.mcp_catalog import MCP
    raw = await MCP.scanner.get_enriched_batch({"symbols": ["AAPL"]})

Benefits over scattering string literals across agent files:
  - One place to audit/rename endpoints when the gateway changes.
  - Typos become AttributeError at import time instead of silent 404s
    at request time (e.g. the old "sec_filings" vs "sec" prefix bug).
  - `validate_catalog()` cross-checks this catalog against the gateway's
    live /api/tools listing at startup and logs any drift.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from agents._mcp_tools import call_mcp_tool, _get_client

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MCPTool:
    """A callable handle for one MCP Gateway tool."""
    server: str
    name: str

    @property
    def full_name(self) -> str:
        return f"{self.server}_{self.name}"

    async def __call__(self, arguments: dict | None = None, **kwargs) -> Any:
        return await call_mcp_tool(self.server, self.name, arguments, **kwargs)


class _Scanner:
    get_market_session = MCPTool("scanner", "get_market_session")
    get_scanner_snapshot = MCPTool("scanner", "get_scanner_snapshot")
    get_enriched_ticker = MCPTool("scanner", "get_enriched_ticker")
    get_enriched_batch = MCPTool("scanner", "get_enriched_batch")
    get_all_categories = MCPTool("scanner", "get_all_categories")
    search_scanner = MCPTool("scanner", "search_scanner")
    apply_dynamic_filter = MCPTool("scanner", "apply_dynamic_filter")


class _Events:
    get_recent_events = MCPTool("events", "get_recent_events")
    get_events_by_ticker = MCPTool("events", "get_events_by_ticker")
    query_historical_events = MCPTool("events", "query_historical_events")
    get_event_stats = MCPTool("events", "get_event_stats")
    get_available_event_types = MCPTool("events", "get_available_event_types")


class _News:
    get_latest_news = MCPTool("news", "get_latest_news")
    get_news_by_ticker = MCPTool("news", "get_news_by_ticker")
    get_catalyst_alerts = MCPTool("news", "get_catalyst_alerts")


class _Earnings:
    get_today_earnings = MCPTool("earnings", "get_today_earnings")
    get_upcoming_earnings = MCPTool("earnings", "get_upcoming_earnings")
    get_earnings_by_ticker = MCPTool("earnings", "get_earnings_by_ticker")
    get_earnings_by_date = MCPTool("earnings", "get_earnings_by_date")


class _Sec:
    # NOTE: the gateway mounts this server with prefix "sec" (not "sec_filings").
    get_recent_filings = MCPTool("sec", "get_recent_filings")
    search_filings = MCPTool("sec", "search_filings")
    get_filing_detail = MCPTool("sec", "get_filing_detail")


class _Financials:
    get_financial_statements = MCPTool("financials", "get_financial_statements")
    get_income_statement = MCPTool("financials", "get_income_statement")
    get_balance_sheet = MCPTool("financials", "get_balance_sheet")
    get_cash_flow = MCPTool("financials", "get_cash_flow")
    get_segments = MCPTool("financials", "get_segments")


class _Dilution:
    get_sec_dilution_profile = MCPTool("dilution", "get_sec_dilution_profile")
    get_enhanced_profile = MCPTool("dilution", "get_enhanced_profile")
    get_instrument_context = MCPTool("dilution", "get_instrument_context")
    get_dilution_risk_ratings = MCPTool("dilution", "get_dilution_risk_ratings")
    get_dilution_analysis = MCPTool("dilution", "get_dilution_analysis")
    get_cash_position = MCPTool("dilution", "get_cash_position")
    get_cash_runway = MCPTool("dilution", "get_cash_runway")
    get_warrants = MCPTool("dilution", "get_warrants")
    get_shares_history = MCPTool("dilution", "get_shares_history")
    get_completed_offerings = MCPTool("dilution", "get_completed_offerings")
    get_atm_offerings = MCPTool("dilution", "get_atm_offerings")
    get_shelf_registrations = MCPTool("dilution", "get_shelf_registrations")
    get_trending_dilution = MCPTool("dilution", "get_trending_dilution")
    get_sec_filings = MCPTool("dilution", "get_sec_filings")


class _Screener:
    run_screen = MCPTool("screener", "run_screen")
    search_by_theme = MCPTool("screener", "search_by_theme")
    enrich_with_classification = MCPTool("screener", "enrich_with_classification")
    get_available_filters = MCPTool("screener", "get_available_filters")
    get_daily_indicators = MCPTool("screener", "get_daily_indicators")
    list_available_themes = MCPTool("screener", "list_available_themes")


class _Historical:
    get_day_bars = MCPTool("historical", "get_day_bars")
    get_minute_bars = MCPTool("historical", "get_minute_bars")
    get_top_movers = MCPTool("historical", "get_top_movers")
    available_dates = MCPTool("historical", "available_dates")


class _Analytics:
    get_rvol = MCPTool("analytics", "get_rvol")
    get_rvol_batch = MCPTool("analytics", "get_rvol_batch")
    get_technical_snapshot = MCPTool("analytics", "get_technical_snapshot")
    get_price_windows = MCPTool("analytics", "get_price_windows")
    get_volume_windows = MCPTool("analytics", "get_volume_windows")


class _Patterns:
    find_similar_patterns = MCPTool("patterns", "find_similar_patterns")


class _Predictions:
    get_prediction_events = MCPTool("predictions", "get_prediction_events")
    get_prediction_price_history = MCPTool("predictions", "get_prediction_price_history")


class _MarketPulse:
    analyze_market = MCPTool("market_pulse", "analyze_market")
    get_market_regime = MCPTool("market_pulse", "get_market_regime")


class MCP:
    """Namespace with every MCP Gateway tool, grouped by domain server."""
    scanner = _Scanner
    events = _Events
    news = _News
    earnings = _Earnings
    sec = _Sec
    financials = _Financials
    dilution = _Dilution
    screener = _Screener
    historical = _Historical
    analytics = _Analytics
    patterns = _Patterns
    predictions = _Predictions
    market_pulse = _MarketPulse


def all_catalog_tools() -> list[MCPTool]:
    """Return every MCPTool declared in the catalog."""
    tools: list[MCPTool] = []
    for group in vars(MCP).values():
        if not isinstance(group, type):
            continue
        for value in vars(group).values():
            if isinstance(value, MCPTool):
                tools.append(value)
    return tools


async def validate_catalog() -> None:
    """Cross-check the catalog against the gateway's live tool listing.

    Non-fatal: logs a warning for catalog entries missing on the gateway
    (broken calls waiting to happen) and an info line for gateway tools
    not declared here (new capabilities to adopt).
    """
    try:
        client = await _get_client()
        resp = await client.get("/api/tools")
        data = resp.json()
        live = {t["name"] for t in data.get("tools", [])}
    except Exception as exc:
        logger.warning("MCP catalog validation skipped (gateway unreachable): %s", exc)
        return

    if not live:
        logger.warning("MCP catalog validation skipped: gateway returned an empty tool list")
        return

    declared = {t.full_name for t in all_catalog_tools()}
    missing = sorted(declared - live)
    undeclared = sorted(live - declared)

    if missing:
        logger.warning("MCP catalog: %d tools NOT on gateway (calls will 404): %s", len(missing), missing)
    if undeclared:
        logger.info("MCP catalog: %d gateway tools not in catalog: %s", len(undeclared), undeclared)
    if not missing:
        logger.info("MCP catalog validated: %d/%d tools present on gateway", len(declared), len(declared))
