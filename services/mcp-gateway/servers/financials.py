"""
MCP Server: Financial Statements
SEC XBRL extraction with income statements, balance sheets, cash flow, and ratios.
"""
from fastmcp import FastMCP
from clients.http_client import service_get
from config import config
from typing import Optional

mcp = FastMCP(
    "TradeUL Financials",
    instructions="Financial statements extraction from SEC XBRL filings. "
    "Provides income statements, balance sheets, cash flow statements, "
    "segment breakdowns, financial ratios, margins, and YoY growth metrics.",
)


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
    calculated metrics (margins, growth rates, FCF), and split-adjusted values.
    """
    try:
        return await service_get(
            config.financials_url,
            f"/api/v1/financials/{symbol.upper()}",
            params={"period": period, "limit": limit},
        )
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def get_income_statement(symbol: str, period: str = "annual") -> dict:
    """Get income statement with revenue, expenses, margins, and growth rates."""
    try:
        return await service_get(
            config.financials_url, f"/api/v1/financials/{symbol.upper()}/income",
            params={"period": period},
        )
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def get_balance_sheet(symbol: str, period: str = "annual") -> dict:
    """Get balance sheet with assets, liabilities, equity, and key ratios."""
    try:
        return await service_get(
            config.financials_url, f"/api/v1/financials/{symbol.upper()}/balance",
            params={"period": period},
        )
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def get_cash_flow(symbol: str, period: str = "annual") -> dict:
    """Get cash flow statement with operating, investing, and financing activities."""
    try:
        return await service_get(
            config.financials_url, f"/api/v1/financials/{symbol.upper()}/cashflow",
            params={"period": period},
        )
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def get_segments(symbol: str) -> dict:
    """Get business segment breakdown - revenue and profit by segment/geography/product."""
    try:
        return await service_get(
            config.financials_url, f"/api/v1/financials/{symbol.upper()}/segments"
        )
    except Exception as e:
        return {"error": str(e)}
