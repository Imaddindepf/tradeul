"""
Financial Analysis Router
=========================
Primary data source is now Perplexity Finance v3 (same payload the user sees on
https://www.perplexity.ai/finance/<TICKER>/financials). We scrape it the same
way analyst-ratings does (curl_cffi + Chrome impersonation), transform it into
the SymbioticFinancialData shape the frontend expects, and serve it.

If Perplexity is unreachable we fall back to the legacy XBRL `financials`
microservice so the UI degrades gracefully.

Endpoints:
- GET    /{symbol}                Full income / balance / cash-flow (Symbiotic shape)
- GET    /{symbol}/income         Income statement only
- GET    /{symbol}/balance        Balance sheet only
- GET    /{symbol}/cashflow       Cash flow only
- GET    /{symbol}/segments       Segments + KPIs from Perplexity v3
- GET    /{symbol}/income-details Income detail enrichment (microservice)
- POST   /cache/clear             Clear cache (both v3 + microservice)
- DELETE /{symbol}/cache          Clear cache for one ticker
- GET    /health/check            Service health
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from http_clients import FinancialsClient, http_clients
from perplexity_v3 import (
    clear_cache as clear_perplexity_cache,
    fetch_v3,
    transform_segments,
    transform_to_symbiotic,
)
from shared.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/financials", tags=["financials"])


def _get_client() -> Optional[FinancialsClient]:
    """Return the legacy financials microservice client, or None if unavailable."""
    return http_clients.financials if http_clients.financials else None


def _v3_period(period: str) -> str:
    """Normalize FE period selector → Perplexity v3 `period` query string."""
    p = (period or "").lower().strip()
    if p in ("annual", "annually", "year", "yearly", "a"):
        return "annual"
    if p in ("ttm", "trailing"):
        return "ttm"
    return "quarter"


def _apply_limit(symbiotic: Dict[str, Any], limit: int) -> Dict[str, Any]:
    """Trim each ConsolidatedField.values + periods list to the most recent `limit` entries."""
    if not symbiotic or limit <= 0:
        return symbiotic
    periods = symbiotic.get("periods") or []
    if len(periods) <= limit:
        return symbiotic

    symbiotic["periods"] = periods[:limit]
    for block in ("income_statement", "balance_sheet", "cash_flow"):
        fields = symbiotic.get(block) or []
        for field in fields:
            values = field.get("values") or []
            field["values"] = values[:limit]
    return symbiotic


# ============================================================================
# API Endpoints
# ============================================================================

@router.get("/{symbol}")
async def get_financials(
    symbol: str,
    period: str = Query("annual", description="annual | quarter | ttm"),
    limit: int = Query(10, ge=1, le=30, description="Number of periods"),
    refresh: bool = Query(False, description="Force refresh from upstream"),
):
    """
    Symbiotic financials for a ticker.

    Primary source: Perplexity Finance v3.
    Fallback: legacy `financials` microservice (XBRL).
    """
    symbol = symbol.upper().strip()
    if not symbol or not symbol.isalpha() or len(symbol) > 6:
        raise HTTPException(status_code=400, detail="Invalid ticker symbol")

    v3_period = _v3_period(period)

    if refresh:
        clear_perplexity_cache(symbol)

    try:
        payload = await fetch_v3(symbol, v3_period)
    except Exception as exc:
        payload = None
        logger.warning("perplexity_v3_fetch_exception", symbol=symbol, error=str(exc))

    if payload:
        try:
            symbiotic = transform_to_symbiotic(symbol, v3_period, payload)
            if symbiotic and symbiotic.get("periods"):
                return _apply_limit(symbiotic, limit)
        except Exception as exc:
            logger.error("perplexity_v3_transform_failed", symbol=symbol, error=str(exc))

    # ── Fallback: legacy microservice ─────────────────────────────────────
    client = _get_client()
    if client is None:
        raise HTTPException(
            status_code=502,
            detail="Financial data unavailable: Perplexity v3 failed and no fallback is configured.",
        )

    logger.info("financials_fallback_to_microservice", symbol=symbol, period=period)
    try:
        data = await client.get_financials(
            symbol=symbol,
            period=period,
            limit=limit,
            refresh=refresh,
        )
        return data
    except Exception as exc:
        logger.error("financials_microservice_error", symbol=symbol, error=str(exc))
        if hasattr(exc, "response"):
            try:
                detail = exc.response.json().get("detail", str(exc))
                raise HTTPException(status_code=exc.response.status_code, detail=detail)
            except HTTPException:
                raise
            except Exception:  # pragma: no cover - defensive
                pass
        raise HTTPException(status_code=502, detail="Failed to retrieve financial data") from exc


@router.get("/{symbol}/income")
async def get_income_statements(
    symbol: str,
    period: str = Query("annual"),
    limit: int = Query(10, ge=1, le=30),
):
    data = await get_financials(symbol, period, limit)
    return {
        "symbol": data.get("symbol"),
        "currency": data.get("currency"),
        "periods": data.get("periods"),
        "income_statement": data.get("income_statement", []),
    }


@router.get("/{symbol}/balance")
async def get_balance_sheets(
    symbol: str,
    period: str = Query("annual"),
    limit: int = Query(10, ge=1, le=30),
):
    data = await get_financials(symbol, period, limit)
    return {
        "symbol": data.get("symbol"),
        "currency": data.get("currency"),
        "periods": data.get("periods"),
        "balance_sheet": data.get("balance_sheet", []),
    }


@router.get("/{symbol}/cashflow")
async def get_cash_flows(
    symbol: str,
    period: str = Query("annual"),
    limit: int = Query(10, ge=1, le=30),
):
    data = await get_financials(symbol, period, limit)
    return {
        "symbol": data.get("symbol"),
        "currency": data.get("currency"),
        "periods": data.get("periods"),
        "cash_flow": data.get("cash_flow", []),
    }


# ============================================================================
# SEGMENTS — Perplexity v3 (rich) with microservice fallback
# ============================================================================

@router.get("/{symbol}/segments")
async def get_segment_breakdown(symbol: str):
    """
    Business segments + KPIs (Bitcoin mined, GPUs, MW capacity, RPO, etc.) as
    surfaced by Perplexity Finance v3. Falls back to the legacy XBRL service
    if Perplexity is unreachable.
    """
    symbol = symbol.upper().strip()
    if not symbol or not symbol.isalpha() or len(symbol) > 6:
        raise HTTPException(status_code=400, detail="Invalid ticker symbol")

    # Perplexity quarter payload already contains the full historical segments list
    try:
        payload = await fetch_v3(symbol, "quarter")
    except Exception as exc:
        payload = None
        logger.warning("perplexity_v3_segments_fetch_exception", symbol=symbol, error=str(exc))

    if payload:
        try:
            segments = transform_segments(symbol, payload)
            if segments and (
                segments.get("segments", {}).get("revenue")
                or segments.get("geography", {}).get("revenue")
                or segments.get("products", {}).get("revenue")
            ):
                return segments
        except Exception as exc:
            logger.error("perplexity_v3_segments_transform_failed", symbol=symbol, error=str(exc))

    # Fallback to legacy microservice
    client = _get_client()
    if client is None:
        return {
            "symbol": symbol,
            "segments": {},
            "geography": {},
            "products": {},
        }

    try:
        data = await client.get_segments(symbol)
        if not data:
            return {"symbol": symbol, "segments": {}, "geography": {}, "products": {}}
        has_data = (
            data.get("segments", {}).get("revenue")
            or data.get("geography", {}).get("revenue")
            or data.get("products", {}).get("revenue")
        )
        if not has_data:
            return {"symbol": symbol, "segments": {}, "geography": {}, "products": {}}
        return data
    except Exception as exc:
        logger.error("segments_microservice_error", symbol=symbol, error=str(exc))
        return {"symbol": symbol, "segments": {}, "geography": {}, "products": {}}


# ============================================================================
# INCOME DETAILS (legacy microservice)
# ============================================================================

@router.get("/{symbol}/income-details")
async def get_income_details(
    symbol: str,
    years: int = Query(10, ge=1, le=15, description="Years of history"),
):
    symbol = symbol.upper()
    client = _get_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Financials microservice unavailable")
    try:
        return await client.get_income_details(symbol, years=years)
    except Exception as exc:
        logger.error("income_details_error", symbol=symbol, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{symbol}/enrichment")
async def get_enrichment(
    symbol: str,
    years: int = Query(10, ge=1, le=15),
):
    return await get_income_details(symbol, years)


# ============================================================================
# CACHE MANAGEMENT
# ============================================================================

@router.post("/cache/clear")
async def clear_cache(symbol: Optional[str] = None):
    """Clear Perplexity v3 cache and (if available) the microservice cache."""
    removed = clear_perplexity_cache(symbol)

    microservice_result: Dict[str, Any] = {"status": "skipped"}
    client = _get_client()
    if client is not None:
        try:
            microservice_result = await client.clear_cache(symbol)
        except Exception as exc:
            logger.warning("microservice_cache_clear_failed", error=str(exc))
            microservice_result = {"status": "error", "error": str(exc)}

    return {
        "perplexity_v3": {"removed": removed},
        "microservice": microservice_result,
    }


@router.delete("/{symbol}/cache")
async def clear_ticker_cache(symbol: str):
    return await clear_cache(symbol.upper())


# ============================================================================
# HEALTH CHECK
# ============================================================================

@router.get("/health/check")
async def health_check():
    client = _get_client()
    microservice_status = "unavailable"
    if client is not None:
        try:
            microservice_status = "healthy" if await client.health_check() else "unhealthy"
        except Exception:  # pragma: no cover - defensive
            microservice_status = "unhealthy"

    return {
        "service": "financials",
        "primary_source": "perplexity_v3",
        "microservice": microservice_status,
    }
