"""
Financial Agent - Financial statements, SEC filings, and risk assessment.

MCP tools used (parameter names MUST match exactly):
  - financials.get_financial_statements(symbol, period, limit)
  - sec.search_filings(ticker, form_type, date_from, date_to, page_size)

Data cleaning:
  - SEC filings: strip null fields, internal IDs → only metadata rows
  - Financial statements: keep key metrics, human-readable labels
  
NOTE: Dilution MCP is disabled — dilution tools are skipped gracefully.
"""
from __future__ import annotations
import asyncio
import time
from typing import Any

from agents._mcp_tools import call_mcp_tool


# ── Intent detection ────────────────────────────────────────────────

_DILUTION_KEYWORDS = [
    "dilution", "diluted", "diluting", "warrants", "warrant",
    "offering", "shelf", "atm", "at-the-market", "shares outstanding",
    "float", "authorized shares", "convertible", "pipe",
    "dilucion", "dilución", "acciones",
]

_SEC_KEYWORDS = [
    "sec", "filing", "filings", "10-k", "10-q", "8-k", "s-1", "s-3",
    "424b", "proxy", "def 14a", "annual report", "quarterly report",
    "edgar", "prospectus", "informe",
]

_FINANCIAL_KEYWORDS = [
    "financial", "financials", "fundamentals", "income", "revenue",
    "balance", "cash flow", "earnings", "profit", "margin",
    "ebitda", "debt", "ratio", "valuation", "sobrevalorada",
    "subvalorada", "fundamentales", "ingresos", "beneficio",
    "ganancias", "estados financieros", "financieros",
]

_QUARTERLY_KEYWORDS = [
    "quarter", "quarterly", "q1", "q2", "q3", "q4",
    "trimestre", "trimestres", "trimestral", "trimestrales",
    "último trimestre", "últimos trimestres",
]


def _wants_dilution(q: str) -> bool:
    return any(kw in q.lower() for kw in _DILUTION_KEYWORDS)

def _wants_sec(q: str) -> bool:
    return any(kw in q.lower() for kw in _SEC_KEYWORDS)

def _wants_financials(q: str) -> bool:
    return any(kw in q.lower() for kw in _FINANCIAL_KEYWORDS)

def _wants_quarterly(q: str) -> bool:
    return any(kw in q.lower() for kw in _QUARTERLY_KEYWORDS)


# ── Data cleaning ───────────────────────────────────────────────────

def _clean_sec_filings(raw: dict) -> list[dict]:
    """Strip SEC filings to metadata-only rows.
    The synthesizer only needs: formType, date, description, accessionNo (for links).
    No internal IDs, no null fields, no document blobs.
    """
    filings = raw.get("filings", [])
    if not filings:
        return []

    cleaned = []
    for f in filings:
        row = {
            "form_type": f.get("formType", ""),
            "filed_date": str(f.get("filedAt", ""))[:10],
            "description": f.get("description", ""),
        }
        if f.get("accessionNo"):
            row["accession_no"] = f["accessionNo"]
        if f.get("periodOfReport"):
            row["period"] = f["periodOfReport"]
        cleaned.append(row)

    return cleaned


def _humanize(n: float | int | None) -> str:
    """Convert raw numbers to human-readable: 130497000000 → '130.5B'."""
    if n is None:
        return "N/A"
    if not isinstance(n, (int, float)):
        return str(n)
    abs_n = abs(n)
    sign = "-" if n < 0 else ""
    if abs_n >= 1e12:
        return f"{sign}{abs_n/1e12:.2f}T"
    if abs_n >= 1e9:
        return f"{sign}{abs_n/1e9:.2f}B"
    if abs_n >= 1e6:
        return f"{sign}{abs_n/1e6:.1f}M"
    if abs_n >= 1e3:
        return f"{sign}{abs_n/1e3:.1f}K"
    if isinstance(n, float):
        return f"{sign}{abs_n:.2f}"
    return f"{sign}{abs_n}"


def _pct(n: float | None) -> str:
    """Format a ratio as a percentage.
    
    Values < 1 are ratios (0.25 → 25.0%), values >= 1 are already percentages (25.0 → 25.0%).
    """
    if n is None:
        return "N/A"
    if abs(n) < 1:
        return f"{n * 100:.1f}%"
    return f"{n:.1f}%"


# Key financial metrics to extract (in order of importance)
# These keys match the ACTUAL API response keys from financial-analyst service
_KEY_INCOME = [
    "revenue", "revenue_yoy", "cost_of_revenue", "gross_profit", "gross_margin",
    "sga_expenses", "rd_expenses", "total_operating_expenses",
    "operating_income", "operating_margin",
    "ebitda", "ebitda_margin",
    "net_income", "net_margin",
    "eps_basic",
]

_KEY_BALANCE = [
    "total_cash_st_investments", "total_receivables", "inventory",
    "current_assets", "ppe", "total_assets",
    "current_liabilities", "long_term_debt", "total_liabilities",
    "total_equity",
]

_KEY_CASHFLOW = [
    "operating_cf", "capex", "free_cf",
    "acquisitions", "dividends_paid",
    "financing_cf", "net_change_cash",
]

_PCT_KEYS = {
    "revenue_yoy", "gross_margin", "operating_margin", "ebitda_margin",
    "net_margin", "effective_tax_rate",
}


def _clean_financial_statements(raw: dict) -> dict:
    """Extract key financial metrics from raw API response.
    
    Transforms 108K chars of raw data (219 items × 15 fields each) into
    ~40 key metrics with human-readable values (~3K chars).
    """
    if not isinstance(raw, dict) or "periods" not in raw:
        return raw

    periods = raw.get("periods", [])
    symbol = raw.get("symbol", "")
    currency = raw.get("currency", "USD")

    # Build a lookup: metric_key → {label, values}
    metric_lookup: dict[str, dict] = {}
    for section_key in ("income_statement", "balance_sheet", "cash_flow"):
        section = raw.get(section_key, [])
        if not isinstance(section, list):
            continue
        for item in section:
            key = item.get("key", "")
            label = item.get("label", key)
            values = item.get("values", [])
            if key and values:
                metric_lookup[key] = {"label": label, "values": values}

    def _extract_section(key_list: list[str]) -> list[dict]:
        rows = []
        for key in key_list:
            entry = metric_lookup.get(key)
            if not entry:
                continue
            is_pct = key in _PCT_KEYS
            fmt_values = [_pct(v) if is_pct else _humanize(v) for v in entry["values"]]
            rows.append({"metric": entry["label"], "values": fmt_values})
        return rows

    return {
        "symbol": symbol,
        "currency": currency,
        "periods": periods,
        "income_statement": _extract_section(_KEY_INCOME),
        "balance_sheet": _extract_section(_KEY_BALANCE),
        "cash_flow": _extract_section(_KEY_CASHFLOW),
    }


# ── Main node ───────────────────────────────────────────────────────

async def financial_node(state: dict) -> dict:
    """Fetch financial data and/or SEC filings based on user intent."""
    start_time = time.time()

    query = state.get("query", "")
    tickers = state.get("tickers", [])

    results: dict[str, Any] = {}
    errors: list[str] = []

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

    wants_sec = _wants_sec(query)
    wants_fin = _wants_financials(query)
    wants_dil = _wants_dilution(query)
    quarterly = _wants_quarterly(query)

    fetch_financials = wants_fin or not wants_sec
    fetch_sec = wants_sec

    async def _fetch_financials_for_ticker(ticker: str) -> tuple[str, dict[str, Any], list[str]]:
        ticker_data: dict[str, Any] = {}
        ticker_errors: list[str] = []

        # 1. Financial statements — cleaned to key metrics only
        if fetch_financials:
            try:
                params: dict[str, Any] = {"symbol": ticker}
                if quarterly:
                    params["period"] = "quarter"
                    params["limit"] = 8
                raw = await call_mcp_tool("financials", "get_financial_statements", params)
                ticker_data["financials"] = _clean_financial_statements(raw)
            except Exception as exc:
                ticker_errors.append(f"financials/{ticker}: {exc}")

        # 2. SEC filings — cleaned to metadata rows only
        if fetch_sec:
            try:
                raw = await call_mcp_tool("sec", "search_filings", {"ticker": ticker, "page_size": 10})
                ticker_data["sec_filings"] = _clean_sec_filings(raw)
            except Exception as exc:
                ticker_errors.append(f"sec_filings/{ticker}: {exc}")

        # 3. Dilution — DISABLED
        if wants_dil:
            ticker_data["dilution_note"] = "Dilution analysis is temporarily unavailable."

        return ticker, ticker_data, ticker_errors

    ticker_results = await asyncio.gather(*[
        _fetch_financials_for_ticker(t) for t in tickers[:3]
    ])
    for ticker, ticker_data, ticker_errors in ticker_results:
        results[ticker] = ticker_data
        errors.extend(ticker_errors)

    if errors:
        results["_errors"] = errors

    elapsed_ms = int((time.time() - start_time) * 1000)

    return {
        "agent_results": {
            "financial": {
                "tickers_analyzed": tickers[:3],
                "sec_checked": fetch_sec,
                "financials_checked": fetch_financials,
                "quarterly": quarterly,
                **results,
            },
        },
        "execution_metadata": {
            **(state.get("execution_metadata", {})),
            "financial": {
                "elapsed_ms": elapsed_ms,
                "tickers": tickers[:3],
                "error_count": len(errors),
            },
        },
    }
