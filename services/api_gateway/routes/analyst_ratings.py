"""
Analyst Ratings API
Proxies analyst consensus & individual ratings from Perplexity Finance.
Requires authentication. Results cached in-memory with 1-hour TTL.
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
import time
from shared.utils.logger import get_logger
from auth.dependencies import get_current_user
from auth.models import AuthenticatedUser

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/analyst-ratings", tags=["analyst-ratings"])

from bounded_cache import BoundedTTLCache

CACHE_TTL = 3600  # 1 hour
_cache = BoundedTTLCache(maxsize=256, ttl_seconds=CACHE_TTL)

_UPSTREAM = "https://www.perplexity.ai/rest/finance/analyst-ratings"
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


def _fetch_ratings(ticker: str):
    """Synchronous fetch with retry on different impersonate targets."""
    session = _get_session()
    headers = {**_BASE_HEADERS, "Referer": f"https://www.perplexity.ai/finance/{ticker}"}

    resp = session.get(f"{_UPSTREAM}/{ticker}", timeout=15, headers=headers)
    if resp.status_code == 200:
        return resp.json()

    # Retry with fresh session if Cloudflare blocks
    global _cffi_session
    from curl_cffi import requests as cffi_requests
    for target in ("chrome110", "chrome120", "chrome124", "safari17_0"):
        try:
            _cffi_session = cffi_requests.Session(impersonate=target)
            resp = _cffi_session.get(f"{_UPSTREAM}/{ticker}", timeout=15, headers=headers)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            continue

    _cffi_session = cffi_requests.Session(impersonate="chrome")
    return None


@router.get("/{ticker}")
async def get_analyst_ratings(
    ticker: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    ticker = ticker.upper().strip()
    if not ticker.isalpha() or len(ticker) > 5:
        raise HTTPException(status_code=400, detail="Invalid ticker")

    cached = _cache.get(ticker)
    if cached is not None:
        return cached

    try:
        data = _fetch_ratings(ticker)
        if data is None:
            logger.warning(f"analyst_ratings_fetch_failed ticker={ticker}")
            raise HTTPException(status_code=502, detail="Upstream unavailable")

        _cache.set(ticker, data)
        return data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"analyst_ratings_error ticker={ticker} error={e}")
        raise HTTPException(status_code=502, detail="Failed to fetch analyst ratings")
