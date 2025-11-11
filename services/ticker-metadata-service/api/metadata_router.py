"""
Metadata Router

Endpoints para gestión de metadata de tickers.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Any

import sys
sys.path.append('/app')

from shared.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.get("/{symbol}")
async def get_metadata(
    symbol: str,
    force_refresh: bool = Query(False, description="Forzar refresh desde API externa")
):
    """
    Obtiene metadata completo de un ticker
    
    Args:
        symbol: Símbolo del ticker (ej: AAPL)
        force_refresh: Si True, fuerza refresh desde Polygon API
    
    Returns:
        Metadata completo del ticker
    """
    # Import dentro de función para evitar circular imports
    from main import metadata_manager
    
    if not metadata_manager:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    metadata = await metadata_manager.get_metadata(symbol.upper(), force_refresh=force_refresh)
    
    if not metadata:
        raise HTTPException(status_code=404, detail=f"Metadata for {symbol} not found")
    
    # Convertir a dict para respuesta
    return {
        "symbol": metadata.symbol,
        "company_name": metadata.company_name,
        "exchange": metadata.exchange,
        "sector": metadata.sector,
        "industry": metadata.industry,
        "market_cap": metadata.market_cap,
        "float_shares": metadata.float_shares,
        "shares_outstanding": metadata.shares_outstanding,
        "avg_volume_30d": metadata.avg_volume_30d,
        "avg_volume_10d": metadata.avg_volume_10d,
        "avg_price_30d": metadata.avg_price_30d,
        "beta": metadata.beta,
        "is_etf": metadata.is_etf,
        "is_actively_trading": metadata.is_actively_trading,
        "updated_at": metadata.updated_at.isoformat() if metadata.updated_at else None
    }


@router.post("/{symbol}/refresh")
async def refresh_metadata(symbol: str):
    """
    Fuerza refresh de metadata desde fuente externa
    
    Args:
        symbol: Símbolo del ticker
    
    Returns:
        Metadata actualizado
    """
    from main import metadata_manager
    
    if not metadata_manager:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    logger.info("manual_refresh_requested", symbol=symbol)
    
    metadata = await metadata_manager.enrich_metadata(symbol.upper())
    
    if not metadata:
        raise HTTPException(status_code=500, detail=f"Failed to refresh metadata for {symbol}")
    
    return {
        "symbol": metadata.symbol,
        "company_name": metadata.company_name,
        "exchange": metadata.exchange,
        "sector": metadata.sector,
        "industry": metadata.industry,
        "market_cap": metadata.market_cap,
        "float_shares": metadata.float_shares,
        "shares_outstanding": metadata.shares_outstanding,
        "is_etf": metadata.is_etf,
        "is_actively_trading": metadata.is_actively_trading,
        "updated_at": metadata.updated_at.isoformat() if metadata.updated_at else None,
        "refreshed": True
    }


@router.post("/bulk/refresh")
async def bulk_refresh(
    symbols: List[str],
    max_concurrent: int = Query(5, ge=1, le=20, description="Max concurrent requests")
):
    """
    Refresh metadata para múltiples symbols en paralelo
    
    Args:
        symbols: Lista de símbolos
        max_concurrent: Máximo de requests concurrentes
    
    Returns:
        Dict con resultados por symbol
    """
    from main import metadata_manager
    
    if not metadata_manager:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    if len(symbols) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 symbols per request")
    
    logger.info("bulk_refresh_requested", count=len(symbols))
    
    results = await metadata_manager.bulk_enrich(symbols, max_concurrent=max_concurrent)
    
    successful = sum(1 for success in results.values() if success)
    
    return {
        "total": len(symbols),
        "successful": successful,
        "failed": len(symbols) - successful,
        "results": results
    }


@router.get("/stats/service")
async def get_service_stats():
    """
    Obtiene estadísticas del servicio
    """
    from main import metadata_manager
    
    if not metadata_manager:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    return metadata_manager.get_stats()

