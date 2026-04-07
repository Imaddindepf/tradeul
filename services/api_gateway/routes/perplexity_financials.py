"""
Perplexity Finance – Financial Statements Proxy
================================================
Proxies quarterly Balance Sheet and Cash Flow data from Perplexity Finance.
Used by the Dilution Tracker to compute Cash Need ratings with the same
underlying data source that DilutionTracker.com uses.

Endpoints exposed:
  GET /api/v1/perplexity-financials/{ticker}/balance-sheet   → quarterly Balance Sheet
  GET /api/v1/perplexity-financials/{ticker}/cash-flow       → quarterly Cash Flow
  GET /api/v1/perplexity-financials/{ticker}/cash-summary    → cash + OCF combined (used by dilution)

Results cached in-memory with a 4-hour TTL.
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, Optional, List
import time
from shared.utils.logger import get_logger
from auth.dependencies import get_current_user
from auth.models import AuthenticatedUser

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/perplexity-financials", tags=["perplexity-financials"])

_cache: Dict[str, Any] = {}
_cache_ts: Dict[str, float] = {}
CACHE_TTL = 4 * 3600  # 4 hours

_BASE_URL = "https://www.perplexity.ai/rest/finance/financials"
_BASE_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.perplexity.ai",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}

_cffi_session = None


def _get_session():
    global _cffi_session
    if _cffi_session is None:
        from curl_cffi import requests as cffi_requests
        _cffi_session = cffi_requests.Session(impersonate="chrome")
    return _cffi_session


def _fetch_financials(ticker: str, category: str) -> Optional[Dict]:
    """Fetch financial statements with Chrome impersonation + retry."""
    from curl_cffi import requests as cffi_requests
    global _cffi_session

    headers = {
        **_BASE_HEADERS,
        "Referer": f"https://www.perplexity.ai/finance/{ticker}/financials",
    }
    url = f"{_BASE_URL}/{ticker}?period=quarter&category={category}"

    session = _get_session()
    try:
        resp = session.get(url, timeout=15, headers=headers)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass

    for target in ("chrome110", "chrome120", "chrome124", "safari17_0"):
        try:
            _cffi_session = cffi_requests.Session(impersonate=target)
            resp = _cffi_session.get(url, timeout=15, headers=headers)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            continue

    _cffi_session = cffi_requests.Session(impersonate="chrome")
    return None


def _extract_section(data: Dict, section_type: str) -> List[Dict]:
    """Extract rows for a specific statement type from the quarter list."""
    for section in data.get("quarter", []):
        if section.get("type") == section_type:
            return section.get("data", [])
    return []


def _build_cash_summary(ticker: str) -> Dict:
    """
    Combines Balance Sheet + Cash Flow into a lean cash summary dict:
    {
        "ticker": str,
        "quarters": [
            {
                "date": "2025-09-30",
                "period": "Q3",
                "year": "2025",
                "cash": 3009000,            # cashAndCashEquivalents
                "operating_cf": -10617386,  # netCashProvidedByOperatingActivities
            },
            ...
        ],
        "latest": { same structure as above, or None }
    }
    Quarters are sorted most-recent first.
    """
    bs_data = _fetch_financials(ticker, "BALANCE_SHEET")
    cf_data = _fetch_financials(ticker, "CASH_FLOW")

    bs_rows = _extract_section(bs_data, "BALANCE_SHEET") if bs_data else []
    cf_rows = _extract_section(cf_data, "CASH_FLOW") if cf_data else []

    # Index CF by date for quick lookup
    cf_by_date = {row["date"]: row for row in cf_rows if "date" in row}

    quarters = []
    for row in bs_rows:
        date = row.get("date")
        if not date:
            continue
        cf_row = cf_by_date.get(date, {})
        quarters.append({
            "date": date,
            "period": row.get("period"),
            "year": row.get("calendarYear"),
            "cash": row.get("cashAndCashEquivalents"),
            "cash_and_short_term": row.get("cashAndShortTermInvestments"),
            "operating_cf": cf_row.get("netCashProvidedByOperatingActivities"),
        })

    # Sort most-recent first (filter out None cash entries)
    quarters = [q for q in quarters if q["cash"] is not None]
    quarters.sort(key=lambda q: q["date"], reverse=True)

    return {
        "ticker": ticker,
        "quarters": quarters,
        "latest": quarters[0] if quarters else None,
    }


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/{ticker}/balance-sheet")
async def get_balance_sheet(
    ticker: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    ticker = ticker.upper().strip()
    cache_key = f"bs:{ticker}"
    now = time.time()
    if cache_key in _cache and (now - _cache_ts.get(cache_key, 0)) < CACHE_TTL:
        return _cache[cache_key]

    data = _fetch_financials(ticker, "BALANCE_SHEET")
    if not data:
        raise HTTPException(status_code=502, detail="Upstream unavailable")

    rows = _extract_section(data, "BALANCE_SHEET")
    result = {
        "ticker": ticker,
        "quarters": sorted(rows, key=lambda r: r.get("date", ""), reverse=True),
    }
    _cache[cache_key] = result
    _cache_ts[cache_key] = now
    return result


@router.get("/{ticker}/cash-flow")
async def get_cash_flow(
    ticker: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    ticker = ticker.upper().strip()
    cache_key = f"cf:{ticker}"
    now = time.time()
    if cache_key in _cache and (now - _cache_ts.get(cache_key, 0)) < CACHE_TTL:
        return _cache[cache_key]

    data = _fetch_financials(ticker, "CASH_FLOW")
    if not data:
        raise HTTPException(status_code=502, detail="Upstream unavailable")

    rows = _extract_section(data, "CASH_FLOW")
    result = {
        "ticker": ticker,
        "quarters": sorted(rows, key=lambda r: r.get("date", ""), reverse=True),
    }
    _cache[cache_key] = result
    _cache_ts[cache_key] = now
    return result


@router.get("/{ticker}/cash-summary")
async def get_cash_summary(
    ticker: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Combined cash + operating CF per quarter, most-recent first.
    Used by the Dilution Tracker's Cash Need rating calculation.
    """
    ticker = ticker.upper().strip()
    cache_key = f"summary:{ticker}"
    now = time.time()
    if cache_key in _cache and (now - _cache_ts.get(cache_key, 0)) < CACHE_TTL:
        return _cache[cache_key]

    try:
        result = _build_cash_summary(ticker)
    except Exception as e:
        logger.error("perplexity_cash_summary_error", ticker=ticker, error=str(e))
        raise HTTPException(status_code=502, detail="Failed to fetch financial data")

    if not result["quarters"]:
        raise HTTPException(status_code=404, detail="No financial data available")

    _cache[cache_key] = result
    _cache_ts[cache_key] = now
    return result
