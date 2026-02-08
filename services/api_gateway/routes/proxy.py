"""
Proxy Routes - Forward requests to internal services

These endpoints allow the frontend to access internal services
through the API Gateway instead of calling them directly.
"""

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, Depends
from fastapi.responses import JSONResponse, StreamingResponse, Response
import structlog

from auth import get_current_user, AuthenticatedUser

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["proxy"])

# In-memory cache for logos (simple TTL-less cache, resets on restart)
_logo_cache: dict[str, bytes] = {}

# Internal service URLs (only accessible within Docker network)
MARKET_SESSION_URL = "http://market_session:8002"
SEC_FILINGS_URL = "http://sec-filings:8012"
DILUTION_TRACKER_URL = "http://dilution_tracker:8000"


# ============================================================================
# MARKET SESSION PROXY
# ============================================================================

@router.get("/api/session/current")
async def proxy_market_session():
    """Proxy to market session service - get current session"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{MARKET_SESSION_URL}/api/session/current")
            return JSONResponse(
                content=response.json(),
                status_code=response.status_code
            )
    except httpx.RequestError as e:
        logger.error("market_session_proxy_error", error=str(e))
        raise HTTPException(status_code=503, detail="Market session service unavailable")


@router.get("/api/session/market-status")
async def proxy_market_status():
    """Proxy to market session service - get market status"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{MARKET_SESSION_URL}/api/session/market-status")
            return JSONResponse(
                content=response.json(),
                status_code=response.status_code
            )
    except httpx.RequestError as e:
        logger.error("market_status_proxy_error", error=str(e))
        raise HTTPException(status_code=503, detail="Market session service unavailable")


# ============================================================================
# SEC FILINGS PROXY
# ============================================================================

@router.get("/api/v1/filings/live")
async def proxy_sec_filings(request: Request):
    """Proxy to SEC filings service - get live filings (pass all query params)"""
    try:
        # Pass ALL query parameters to the backend service
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{SEC_FILINGS_URL}/api/v1/filings/live",
                params=dict(request.query_params)
            )
            return JSONResponse(
                content=response.json(),
                status_code=response.status_code
            )
    except httpx.RequestError as e:
        logger.error("sec_filings_proxy_error", error=str(e))
        raise HTTPException(status_code=503, detail="SEC filings service unavailable")


@router.get("/api/v1/filings/proxy")
async def proxy_sec_document(url: str = Query(...)):
    """Proxy to SEC filings service - proxy SEC document URLs"""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{SEC_FILINGS_URL}/api/v1/proxy",
                params={"url": url}
            )
            return StreamingResponse(
                content=response.iter_bytes(),
                status_code=response.status_code,
                media_type=response.headers.get("content-type", "text/html")
            )
    except httpx.RequestError as e:
        logger.error("sec_proxy_document_error", error=str(e))
        raise HTTPException(status_code=503, detail="SEC filings service unavailable")


# ============================================================================
# DILUTION TRACKER PROXY
# ============================================================================

@router.get("/api/v1/dilution/validate/{ticker}")
async def proxy_dilution_validate(ticker: str):
    """Proxy to dilution tracker service - validate ticker"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{DILUTION_TRACKER_URL}/api/analysis/validate/{ticker}")
            return JSONResponse(
                content=response.json(),
                status_code=response.status_code
            )
    except httpx.RequestError as e:
        logger.error("dilution_validate_proxy_error", ticker=ticker, error=str(e))
        raise HTTPException(status_code=503, detail="Dilution tracker service unavailable")


@router.get("/api/v1/dilution/{ticker}")
async def proxy_dilution_analysis(
    ticker: str,
    user: AuthenticatedUser = Depends(get_current_user)  # 🔒 Requiere auth - usa Grok LLM ($$$)
):
    """
    Proxy to dilution tracker service - get analysis for ticker.
    PROTEGIDO: Requiere autenticación (usa Grok LLM que es costoso)
    """
    logger.info("dilution_analysis_request", ticker=ticker, user_id=user.id)
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:  # 2 min timeout for SEC scraping
            response = await client.get(f"{DILUTION_TRACKER_URL}/api/analysis/{ticker}")
            return JSONResponse(
                content=response.json(),
                status_code=response.status_code
            )
    except httpx.TimeoutException as e:
        logger.error("dilution_proxy_timeout", ticker=ticker, error=str(e))
        raise HTTPException(status_code=504, detail=f"Dilution tracker timeout for {ticker}")
    except httpx.RequestError as e:
        logger.error("dilution_proxy_request_error", ticker=ticker, error=str(e), error_type=type(e).__name__)
        raise HTTPException(status_code=503, detail=f"Dilution tracker unavailable: {type(e).__name__}")
    except Exception as e:
        logger.error("dilution_proxy_unexpected_error", ticker=ticker, error=str(e), error_type=type(e).__name__)
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@router.get("/api/v1/dilution/{ticker}/history")
async def proxy_dilution_history(ticker: str, days: int = Query(30)):
    """Proxy to dilution tracker service - get dilution history"""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{DILUTION_TRACKER_URL}/api/analysis/{ticker}/history",
                params={"days": days}
            )
            return JSONResponse(
                content=response.json(),
                status_code=response.status_code
            )
    except httpx.RequestError as e:
        logger.error("dilution_history_proxy_error", ticker=ticker, error=str(e))
        raise HTTPException(status_code=503, detail="Dilution tracker service unavailable")


@router.get("/api/v1/dilution/{ticker}/sec-profile")
async def proxy_dilution_sec_profile(
    ticker: str, 
    refresh: bool = Query(False),
    user: AuthenticatedUser = Depends(get_current_user)  # 🔒 Requiere auth - usa Grok LLM ($$$)
):
    """
    Proxy to dilution tracker service - get SEC dilution profile.
    PROTEGIDO: Requiere autenticación (usa Grok LLM que es costoso)
    """
    logger.info("dilution_sec_profile_request", ticker=ticker, user_id=user.id, refresh=refresh)
    try:
        params = {"refresh": "true"} if refresh else {}
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(
                f"{DILUTION_TRACKER_URL}/api/sec-dilution/{ticker}/profile",
                params=params
            )
            return JSONResponse(
                content=response.json(),
                status_code=response.status_code
            )
    except httpx.RequestError as e:
        logger.error("dilution_sec_profile_proxy_error", ticker=ticker, error=str(e))
        raise HTTPException(status_code=503, detail="Dilution tracker service unavailable")


# ============================================================================
# LOGO PROXY (for sharing/export features)
# ============================================================================

@router.get("/api/v1/logo/{symbol}")
async def proxy_logo(symbol: str):
    """
    Proxy company logos for sharing features.
    Tries multiple sources: FMP, parqet, iex.
    Caches logos in memory.
    """
    symbol = symbol.upper()
    
    # Check cache first
    if symbol in _logo_cache:
        return Response(
            content=_logo_cache[symbol],
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=86400"}
        )
    
    # Try multiple logo sources
    sources = [
        f"https://financialmodelingprep.com/image-stock/{symbol}.png",
        f"https://storage.googleapis.com/iexcloud-hl37opg/api/logos/{symbol}.png",
        f"https://assets.parqet.com/logos/symbol/{symbol}?format=png",
    ]
    
    async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
        for url in sources:
            try:
                response = await client.get(url)
                if response.status_code == 200 and len(response.content) > 500:
                    content = response.content
                    # Verify it's actually an image (starts with PNG magic bytes or JPEG)
                    if content[:4] == b'\x89PNG' or content[:2] == b'\xff\xd8':
                        # Cache if small enough (< 100KB)
                        if len(content) < 100000:
                            _logo_cache[symbol] = content
                        return Response(
                            content=content,
                            media_type="image/png",
                            headers={"Cache-Control": "public, max-age=86400"}
                        )
            except Exception:
                continue
    
    # No logo found - return transparent 1x1 pixel
    return Response(
        content=b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82',
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"}
    )

