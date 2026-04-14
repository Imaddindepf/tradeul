"""
EDGAR RAG Client — structured data extraction without reading full filings.

Philosophy (CS230 RAG):
  Instead of: 30 full filings → LLM → "find the important bits"
  We do:      XBRL structured data (no LLM) + cover pages only (~600 tokens each)
              → LLM reads 10x less, costs 10x less, is 5x faster

Three data tiers (cheapest to most expensive):
  1. XBRL company facts   → shares outstanding, cash position (100% structured, 0 tokens)
  2. Submissions JSON     → filing list with dates, types, doc URLs (structured, 0 tokens)
  3. Cover pages          → first 3 KB of S-3/424B5/8-K text (~600 tokens per filing)

EDGAR API endpoints (all public, no auth required):
  - Company tickers:   https://www.sec.gov/files/company_tickers.json
  - Submissions:       https://data.sec.gov/submissions/CIK{cik:010d}.json
  - Company facts:     https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json
  - Filing document:   https://www.sec.gov/Archives/edgar/data/{cik}/{accn}/{doc}
"""
from __future__ import annotations
import asyncio
import logging
import re
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_EDGAR_HEADERS = {
    "User-Agent": "Tradeul research@tradeul.com",
    "Accept-Encoding": "gzip, deflate",
}
_TIMEOUT = 10.0  # seconds

# Filing types that indicate potential dilution.
# S-4/S-4/A = business combination (M&A share issuances) — must be included.
_DILUTIVE_FORMS = {
    "S-1", "S-1/A",          # IPO / primary offering
    "S-3", "S-3/A",          # Shelf registration
    "F-1", "F-3",            # Foreign private issuer equivalents
    "S-4", "S-4/A",          # Business combination / M&A share issuances  ← Bug 1 fix
    "424B4", "424B5",        # Prospectus (final)
    "8-K",                   # Material events (PIPE, warrant, convertible)
}

# EDGAR cover page: only these characters of the filing body (HTML → stripped text)
_COVER_PAGE_CHARS = 4000


async def get_cik(ticker: str) -> Optional[str]:
    """
    Resolve ticker symbol to EDGAR CIK.
    Uses the static company_tickers.json (cached by EDGAR, very fast).
    Returns zero-padded 10-digit CIK string, or None if not found.
    """
    url = "https://www.sec.gov/files/company_tickers.json"
    try:
        async with httpx.AsyncClient(headers=_EDGAR_HEADERS, timeout=_TIMEOUT) as client:
            r = await client.get(url)
            r.raise_for_status()
            data = r.json()
        ticker_upper = ticker.upper()
        for entry in data.values():
            if entry.get("ticker", "").upper() == ticker_upper:
                cik_int = entry["cik_str"]
                return str(cik_int).zfill(10)
        logger.warning("edgar_cik_not_found ticker=%s", ticker)
        return None
    except Exception as exc:
        logger.warning("edgar_cik_error ticker=%s error=%s", ticker, exc)
        return None


async def get_submissions(cik: str) -> dict:
    """
    Get recent SEC filings list for a company.
    Returns dict with 'name', 'tickers', and 'filings' (list of dicts with
    keys: date, form, accn, primaryDoc, description).
    Only returns dilutive filing types from the last 24 months.
    """
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    try:
        async with httpx.AsyncClient(headers=_EDGAR_HEADERS, timeout=_TIMEOUT) as client:
            r = await client.get(url)
            r.raise_for_status()
            data = r.json()
    except Exception as exc:
        logger.warning("edgar_submissions_error cik=%s error=%s", cik, exc)
        return {}

    name = data.get("name", "")
    tickers = data.get("tickers", [])
    recent = data.get("filings", {}).get("recent", {})

    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accns = recent.get("accessionNumber", [])
    docs = recent.get("primaryDocument", [])
    descriptions = recent.get("primaryDocDescription", [])

    filings = []
    ipo_date: Optional[str] = None

    for form, date, accn, doc, desc in zip(forms, dates, accns, docs, descriptions):
        # Detect earliest S-1/S-1/A as IPO proxy (Bug 4 fix)
        if form in {"S-1", "S-1/A"}:
            if ipo_date is None or date < ipo_date:
                ipo_date = date

        if form not in _DILUTIVE_FORMS:
            continue
        # Only last 24 months (rough check via string comparison YYYY-MM-DD)
        if date < "2024-01-01":
            continue
        filings.append({
            "date": date,
            "form": form,
            "accn": accn,
            "primary_doc": doc,
            "description": desc or "",
        })

    return {
        "name": name,
        "tickers": tickers,
        "filings": filings[:20],  # cap at 20 most recent dilutive filings
        "ipo_date": ipo_date,      # earliest S-1 date — None for long-established companies
    }


async def get_company_facts(cik: str) -> dict:
    """
    Get XBRL structured financial data for a company.
    Returns parsed dict with:
      - shares_outstanding: list of {period, value, form}
      - cash: list of {period, value, form}
      - operating_cf: list of {period, value, form}
    All values are raw (USD or shares). No LLM needed.
    """
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    try:
        async with httpx.AsyncClient(headers=_EDGAR_HEADERS, timeout=15.0) as client:
            r = await client.get(url)
            r.raise_for_status()
            data = r.json()
    except Exception as exc:
        logger.warning("edgar_facts_error cik=%s error=%s", cik, exc)
        return {}

    gaap = data.get("facts", {}).get("us-gaap", {})
    ifrs = data.get("facts", {}).get("ifrs-full", {})
    _REPORT_FORMS = {"10-K", "10-Q", "20-F", "6-K", "20-F/A"}

    def _extract(concept_names: list[str], unit: str) -> list[dict]:
        """Standard extraction — dedup by period keeping latest filing. For non-shares."""
        for name in concept_names:
            entries = (gaap.get(name) or ifrs.get(name) or {}).get("units", {}).get(unit, [])
            if entries:
                filtered = [
                    {
                        "period": e.get("end", ""),
                        "value": e.get("val"),
                        "form": e.get("form", ""),
                        "filed": e.get("filed", ""),
                    }
                    for e in entries
                    if e.get("form", "") in _REPORT_FORMS
                    and e.get("val") is not None
                    and e.get("end", "")
                ]
                seen: dict[str, dict] = {}
                for item in filtered:
                    p = item["period"]
                    if p not in seen or item["filed"] > seen[p]["filed"]:
                        seen[p] = item
                return sorted(seen.values(), key=lambda x: x["period"])
        return []

    def _extract_shares_sum(concept_names: list[str]) -> list[dict]:
        """
        Shares extraction that SUMS entries for the same (period, accn).

        Bug 2+3 fix: For dual/multi-class companies (e.g. Class A + Class B), EDGAR XBRL
        reports each class as a separate entry under the same concept. The old dedup-by-period
        kept only ONE class. Now we:
          1. Sum all values with the same (period, accession number) → total across classes.
          2. Deduplicate by period keeping the latest filing (for amendments).

        This is safe for single-class companies: only one entry per (period, accn) → no change.
        """
        for name in concept_names:
            entries = (gaap.get(name) or ifrs.get(name) or {}).get("units", {}).get("shares", [])
            if not entries:
                continue
            # Step 1: group by (period, accn) and sum
            by_key: dict[tuple, dict] = {}
            for e in entries:
                form = e.get("form", "")
                period = e.get("end", "")
                val = e.get("val")
                if form not in _REPORT_FORMS or val is None or not period:
                    continue
                key = (period, e.get("accn", ""))
                if key in by_key:
                    by_key[key]["value"] += val
                else:
                    by_key[key] = {
                        "period": period,
                        "value": val,
                        "form": form,
                        "filed": e.get("filed", ""),
                    }
            if not by_key:
                continue
            # Step 2: dedup by period, keep latest filing
            seen: dict[str, dict] = {}
            for item in by_key.values():
                p = item["period"]
                if p not in seen or item["filed"] > seen[p]["filed"]:
                    seen[p] = item
            return sorted(seen.values(), key=lambda x: x["period"])
        return []

    # Shares: use sum-per-(period,accn) for CommonStockSharesOutstanding.
    # WeightedAverage is already an aggregate → standard dedup as fallback only.
    shares = (
        _extract_shares_sum(["CommonStockSharesOutstanding"])
        or _extract(["WeightedAverageNumberOfSharesOutstandingBasic"], "shares")
    )
    cash = _extract(
        [
            "CashAndCashEquivalentsAtCarryingValue",
            "CashCashEquivalentsAndShortTermInvestments",
            "Cash",
        ],
        "USD",
    )
    op_cf = _extract(
        ["NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
        "USD",
    )

    return {
        "shares_outstanding": shares[-8:],   # last 8 data points
        "cash": cash[-8:],
        "operating_cf": op_cf[-8:],
    }


def _strip_html(html: str) -> str:
    """Strip HTML tags and decode common entities. Returns plain text."""
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<")
    text = text.replace("&gt;", ">").replace("&ldquo;", '"').replace("&rdquo;", '"')
    text = text.replace("&rsquo;", "'").replace("&#9746;", "[X]").replace("&#9744;", "[ ]")
    text = re.sub(r"\s+", " ", text).strip()
    return text


async def get_cover_page(cik: str, accn: str, primary_doc: str) -> str:
    """
    Fetch only the cover page of a filing (first N chars after HTML stripping).
    This is the KEY optimization: instead of 200 pages, we read ~600 tokens.

    Args:
        cik:         10-digit CIK (with leading zeros)
        accn:        Accession number (e.g. '0001213900-26-007445')
        primary_doc: Primary document filename (e.g. 'ea0272361-f3_nvni.htm')

    Returns:
        Plain text cover page (~600 tokens), or empty string on error.
    """
    # Build URL: /Archives/edgar/data/{cik_int}/{accn_no_dashes}/{primary_doc}
    cik_int = str(int(cik))  # remove leading zeros for the path
    accn_path = accn.replace("-", "")
    url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accn_path}/{primary_doc}"

    try:
        async with httpx.AsyncClient(headers=_EDGAR_HEADERS, timeout=_TIMEOUT) as client:
            # Use streaming to avoid downloading the full file
            async with client.stream("GET", url) as r:
                r.raise_for_status()
                # Read only the first 32 KB (cover page is in the first few KB)
                chunks = []
                total = 0
                async for chunk in r.aiter_bytes(chunk_size=8192):
                    chunks.append(chunk)
                    total += len(chunk)
                    if total >= 32_768:
                        break
                raw = b"".join(chunks).decode("utf-8", errors="replace")
    except Exception as exc:
        logger.warning("edgar_cover_error accn=%s error=%s", accn, exc)
        return ""

    text = _strip_html(raw)
    return text[:_COVER_PAGE_CHARS]


def summarize_xbrl(facts: dict, ipo_date: Optional[str] = None) -> dict:
    """
    Convert raw XBRL facts to human-readable summary for LLM context.
    Returns a compact dict with key financial metrics — no LLM needed for this.

    Bug 4 fix: if ipo_date is provided, pre-IPO share data is excluded from the
    history before computing shares_change_pct. Pre-IPO private share counts are
    not comparable to post-IPO public float.
    """
    shares = facts.get("shares_outstanding", [])
    cash_list = facts.get("cash", [])
    op_cf_list = facts.get("operating_cf", [])

    result: dict = {}

    if shares:
        # Bug 4 fix: separate pre-IPO (private) from post-IPO (public) data.
        # Pre-IPO share structure is not comparable to public float.
        pre_ipo_shares: list[dict] = []
        if ipo_date:
            pre_ipo_shares = [s for s in shares if s["period"] < ipo_date]
            public_shares = [s for s in shares if s["period"] >= ipo_date]
            if public_shares:
                shares = public_shares  # use only post-IPO for analysis
            # If no post-IPO data yet (very recent IPO), keep all but flag it
            result["ipo_date_approx"] = ipo_date
            if pre_ipo_shares:
                result["pre_ipo_periods_excluded"] = len(pre_ipo_shares)

        latest = shares[-1]
        oldest = shares[0]
        result["shares_outstanding_latest"] = {
            "period": latest["period"],
            "shares": latest["value"],
            "form": latest["form"],
        }
        if len(shares) >= 2:
            change = latest["value"] - oldest["value"]
            pct = change / oldest["value"] * 100 if oldest["value"] else 0
            result["shares_change_pct"] = round(pct, 1)
            result["shares_history"] = [
                {"period": s["period"], "shares": s["value"]} for s in shares
            ]
        elif len(shares) == 1:
            result["shares_history"] = [
                {"period": s["period"], "shares": s["value"]} for s in shares
            ]

    if cash_list:
        latest_cash = cash_list[-1]
        result["cash_latest"] = {
            "period": latest_cash["period"],
            "usd": latest_cash["value"],
            "form": latest_cash["form"],
        }
        result["cash_history"] = [
            {"period": c["period"], "usd": c["value"]} for c in cash_list
        ]

    if op_cf_list:
        # Estimate quarterly burn rate from last 2-4 data points
        recent_cf = op_cf_list[-4:]
        if len(recent_cf) >= 2:
            avg_qtr_cf = sum(c["value"] for c in recent_cf) / len(recent_cf)
            result["quarterly_operating_cf"] = round(avg_qtr_cf)
            if avg_qtr_cf < 0 and cash_list:
                months_runway = abs(cash_list[-1]["value"] / avg_qtr_cf) * 3
                result["estimated_runway_months"] = round(months_runway, 1)

    return result
