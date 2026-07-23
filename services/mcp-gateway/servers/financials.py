"""
MCP Server: Financial Statements
Consolidated company fundamentals: income statements, balance sheets, cash
flow, segments, ratios, adjusted metrics and key statistics — served through
the API gateway (same dataset the frontend renders).
"""
from fastmcp import FastMCP
from clients.http_client import service_get
from config import config
from typing import Any

mcp = FastMCP(
    "Tradeul Financials",
    instructions="Company fundamentals: income statements, balance sheets, "
    "cash flow statements, segment breakdowns, financial ratios, adjusted "
    "(non-GAAP) metrics, key statistics with analyst estimates, margins "
    "and growth metrics.",
)

# Internal plumbing fields stripped from responses before they reach agents.
_INTERNAL_KEYS = {"source", "symbiotic"}


def _sanitize(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {k: _sanitize(v) for k, v in payload.items() if k not in _INTERNAL_KEYS}
    if isinstance(payload, list):
        return [_sanitize(v) for v in payload]
    return payload


@mcp.tool()
async def get_financial_statements(
    symbol: str,
    period: str = "annual",
    limit: int = 5,
) -> dict:
    """Get full financial statements for a company.

    Args:
        symbol: Ticker symbol
        period: 'annual' or 'quarter'
        limit: Number of periods to return

    Returns: income_statement, balance_sheet, cash_flow with line items,
    margins and per-period values.
    """
    try:
        return _sanitize(await service_get(
            config.api_gateway_url,
            f"/api/v1/financials/{symbol.upper()}",
            params={"period": period, "limit": limit},
        ))
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def get_income_statement(
    symbol: str, period: str = "annual", limit: int = 10
) -> dict:
    """Get income statement with revenue, expenses, margins and EPS."""
    try:
        return _sanitize(await service_get(
            config.api_gateway_url,
            f"/api/v1/financials/{symbol.upper()}/income",
            params={"period": period, "limit": limit},
        ))
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def get_balance_sheet(
    symbol: str, period: str = "annual", limit: int = 10
) -> dict:
    """Get balance sheet with assets, liabilities, equity and debt breakdown."""
    try:
        return _sanitize(await service_get(
            config.api_gateway_url,
            f"/api/v1/financials/{symbol.upper()}/balance",
            params={"period": period, "limit": limit},
        ))
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def get_cash_flow(
    symbol: str, period: str = "annual", limit: int = 10
) -> dict:
    """Get cash flow statement with operating, investing, and financing activities."""
    try:
        return _sanitize(await service_get(
            config.api_gateway_url,
            f"/api/v1/financials/{symbol.upper()}/cashflow",
            params={"period": period, "limit": limit},
        ))
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def get_segments(symbol: str, period: str = "annual") -> dict:
    """Get business segment breakdown - revenue and profit by segment/geography/product,
    plus company-specific KPIs when available."""
    try:
        return _sanitize(await service_get(
            config.api_gateway_url,
            f"/api/v1/financials/{symbol.upper()}/segments",
            params={"period": period},
        ))
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def get_financial_ratios(
    symbol: str, period: str = "annual", limit: int = 12
) -> dict:
    """Get financial ratios by period: valuation, profitability margins,
    efficiency, financial health and growth rates.

    Args:
        symbol: Ticker symbol
        period: 'annual', 'quarter' or 'ttm'
        limit: Number of periods to return
    """
    try:
        return _sanitize(await service_get(
            config.api_gateway_url,
            f"/api/v1/financials/{symbol.upper()}/ratios",
            params={"period": period, "limit": limit},
        ))
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def get_key_stats(
    symbol: str, period: str = "annual", limit: int = 12
) -> dict:
    """Get key statistics per period, including forward analyst estimates
    (revenue/EPS) when available.

    Args:
        symbol: Ticker symbol
        period: 'annual', 'quarter' or 'ttm'
        limit: Number of periods to return
    """
    try:
        return _sanitize(await service_get(
            config.api_gateway_url,
            f"/api/v1/financials/{symbol.upper()}/key-stats",
            params={"period": period, "limit": limit},
        ))
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def get_adjusted_metrics(
    symbol: str, period: str = "annual", limit: int = 12
) -> dict:
    """Get adjusted (non-GAAP) metrics as reported by the company:
    adjusted EPS, adjusted EBITDA and similar.

    Args:
        symbol: Ticker symbol
        period: 'annual', 'quarter' or 'ttm'
        limit: Number of periods to return
    """
    try:
        return _sanitize(await service_get(
            config.api_gateway_url,
            f"/api/v1/financials/{symbol.upper()}/adjusted",
            params={"period": period, "limit": limit},
        ))
    except Exception as e:
        return {"error": str(e)}
