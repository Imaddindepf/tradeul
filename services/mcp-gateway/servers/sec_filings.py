"""
MCP Server: SEC Filings
Real-time and historical SEC EDGAR filings from sec-filings service.
"""
from fastmcp import FastMCP
from clients.http_client import service_get
from clients.redis_client import redis_zrevrange_parsed
from config import config
from typing import Optional

mcp = FastMCP(
    "TradeUL SEC Filings",
    instructions="SEC EDGAR filings service with real-time streaming and historical queries. "
    "Covers 8-K, 10-K, 10-Q, S-1, 424B, SC 13D/G, and all other SEC form types.",
)


@mcp.tool()
async def get_recent_filings(count: int = 50, ticker: Optional[str] = None) -> dict:
    """Get the most recent SEC filings from the real-time cache.
    Optionally filter by ticker symbol.
    Returns: form_type, ticker, company_name, filed_at, accession_number, description."""
    if ticker:
        articles = await redis_zrevrange_parsed(
            f"cache:sec:filings:ticker:{ticker.upper()}", 0, count - 1
        )
    else:
        articles = await redis_zrevrange_parsed("cache:sec:filings:latest", 0, count - 1)
    return {"filings": articles, "count": len(articles)}


@mcp.tool()
async def search_filings(
    ticker: Optional[str] = None,
    form_type: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    page_size: int = 50,
) -> dict:
    """Search SEC filings with filters. Queries the full TimescaleDB database.

    Args:
        ticker: Filter by ticker symbol
        form_type: Filter by form type (e.g., '8-K', '10-K', '10-Q', 'S-1', 'SC 13D')
        date_from: Start date (YYYY-MM-DD)
        date_to: End date (YYYY-MM-DD)
        page_size: Results per page (max 100)
    """
    params = {"page_size": min(page_size, 100)}
    if ticker:
        params["ticker"] = ticker.upper()
    if form_type:
        params["form_type"] = form_type
    if date_from:
        params["date_from"] = date_from
    if date_to:
        params["date_to"] = date_to
    try:
        return await service_get(config.sec_filings_url, "/api/v1/filings", params=params)
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def get_filing_detail(accession_number: str) -> dict:
    """Get detailed information about a specific SEC filing by its accession number."""
    try:
        return await service_get(
            config.sec_filings_url, f"/api/v1/filings/{accession_number}"
        )
    except Exception as e:
        return {"error": str(e)}
