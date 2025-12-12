"""
Financial Analysis Router - MICROSERVICE ARCHITECTURE

Proxy router que delega todas las operaciones al microservicio financials.
Usa HTTP client con connection pooling para baja latencia.

Endpoints:
- GET /{symbol}: Datos financieros completos
- GET /{symbol}/segments: Segmentos y geografía
- GET /{symbol}/income-details: Detalles del income statement
- POST /cache/clear: Limpiar cache
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query

from shared.utils.logger import get_logger
from http_clients import http_clients, FinancialsClient

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/financials", tags=["financials"])


def _get_client() -> FinancialsClient:
    """Obtener cliente de financials."""
    if not http_clients.financials:
        raise HTTPException(
            status_code=503, 
            detail="Financials service not available"
        )
    return http_clients.financials


# ============================================================================
# API Endpoints
# ============================================================================

@router.get("/{symbol}")
async def get_financials(
    symbol: str,
    period: str = Query("annual", description="annual o quarter"),
    limit: int = Query(10, ge=1, le=30, description="Number of periods"),
    refresh: bool = Query(False, description="Force refresh from API")
):
    """
    Obtiene datos financieros simbióticos de un ticker.
    
    Formato simbiótico:
    - Campos consolidados semánticamente
    - Sin duplicados
    - Ordenados por importancia financiera
    - Estructura jerárquica para display
    
    Los datos se cachean en Redis por 7 días.
    """
    symbol = symbol.upper()
    client = _get_client()
    
    try:
        data = await client.get_financials(
            symbol=symbol,
            period=period,
            limit=limit,
            refresh=refresh
        )
        return data
        
    except Exception as e:
        logger.error("financials_error", symbol=symbol, error=str(e))
        # Intentar parsear error del servicio
        if hasattr(e, 'response'):
            try:
                detail = e.response.json().get('detail', str(e))
                raise HTTPException(status_code=e.response.status_code, detail=detail)
            except:
                pass
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{symbol}/income")
async def get_income_statements(
    symbol: str,
    period: str = Query("annual", description="annual o quarter"),
    limit: int = Query(10, ge=1, le=30)
):
    """Obtiene solo los Income Statements."""
    data = await get_financials(symbol, period, limit)
    return {"income_statement": data.get("income_statement", [])}


@router.get("/{symbol}/balance")
async def get_balance_sheets(
    symbol: str,
    period: str = Query("annual", description="annual o quarter"),
    limit: int = Query(10, ge=1, le=30)
):
    """Obtiene solo los Balance Sheets."""
    data = await get_financials(symbol, period, limit)
    return {"balance_sheet": data.get("balance_sheet", [])}


@router.get("/{symbol}/cashflow")
async def get_cash_flows(
    symbol: str,
    period: str = Query("annual", description="annual o quarter"),
    limit: int = Query(10, ge=1, le=30)
):
    """Obtiene solo los Cash Flow Statements."""
    data = await get_financials(symbol, period, limit)
    return {"cash_flow": data.get("cash_flow", [])}


# ============================================================================
# SEGMENTS & GEOGRAPHY (via edgartools)
# ============================================================================

@router.get("/{symbol}/segments")
async def get_segment_breakdown(symbol: str):
    """
    Desgloses por segmento y geografía via dimensiones XBRL estándar.
    
    Usa dimensiones US-GAAP:
    - StatementBusinessSegmentsAxis → Segmentos de negocio
    - StatementGeographicalAxis → Geografía
    - ProductOrServiceAxis → Productos/Servicios
    
    Funciona automáticamente para cualquier empresa.
    """
    symbol = symbol.upper()
    client = _get_client()
    
    try:
        data = await client.get_segments(symbol)
        
        if not data or not data.get('segments'):
            return {
                "symbol": symbol,
                "segments": {},
                "geography": {},
                "products": {},
            }
        
        return data
        
    except Exception as e:
        logger.error("segments_error", symbol=symbol, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# INCOME DETAILS (via edgartools)
# ============================================================================

@router.get("/{symbol}/income-details")
async def get_income_details(
    symbol: str,
    years: int = Query(10, ge=1, le=15, description="Years of history")
):
    """
    Obtener detalles del income statement via edgartools.
    
    Complementa los datos de SEC-API con:
    - Desglose de revenue (premiums, products, services)
    - Desglose de costos (medical costs, COGS, SG&A)
    - Campos que SEC-API no captura bien
    """
    symbol = symbol.upper()
    client = _get_client()
    
    try:
        data = await client.get_income_details(symbol, years=years)
        return data
        
    except Exception as e:
        logger.error("income_details_error", symbol=symbol, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# Alias para compatibilidad
@router.get("/{symbol}/enrichment")
async def get_enrichment(
    symbol: str,
    years: int = Query(10, ge=1, le=15, description="Años a extraer")
):
    """Alias para income-details."""
    return await get_income_details(symbol, years)


# ============================================================================
# CACHE MANAGEMENT
# ============================================================================

@router.post("/cache/clear")
async def clear_cache(symbol: Optional[str] = None):
    """
    Limpiar cache de financials.
    
    Args:
        symbol: Ticker específico o None para limpiar todo
    """
    client = _get_client()
    
    try:
        result = await client.clear_cache(symbol)
        return result
        
    except Exception as e:
        logger.error("cache_clear_error", symbol=symbol, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{symbol}/cache")
async def clear_ticker_cache(symbol: str):
    """Limpiar cache para un ticker específico."""
    return await clear_cache(symbol.upper())


# ============================================================================
# HEALTH CHECK
# ============================================================================

@router.get("/health/check")
async def health_check():
    """Verificar estado del servicio de financials."""
    client = _get_client()
    
    is_healthy = await client.health_check()
    
    return {
        "service": "financials",
        "status": "healthy" if is_healthy else "unhealthy",
    }
