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


@router.get("/search")
async def search_tickers(
    q: str = Query(..., description="Search query (symbol or company name)", min_length=1),
    limit: int = Query(10, ge=1, le=50, description="Max results to return")
):
    """
    Buscar tickers por símbolo o nombre de empresa (autocomplete)
    
    Args:
        q: Query string (ej: "AA", "Apple", etc.)
        limit: Máximo de resultados a devolver
    
    Returns:
        Lista de tickers que coinciden con la búsqueda
    """
    from main import timescale_client
    
    if not timescale_client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    query_upper = q.upper()
    
    # Buscar en tickers_unified por symbol o company_name
    sql = """
        SELECT symbol, company_name, exchange, sector, is_actively_trading
        FROM tickers_unified
        WHERE 
            (symbol ILIKE $1 OR company_name ILIKE $2)
            AND is_actively_trading = true
        ORDER BY 
            CASE 
                WHEN symbol = $3 THEN 0
                WHEN symbol LIKE $4 THEN 1
                ELSE 2
            END,
            symbol ASC
        LIMIT $5
    """
    
    try:
        results = await timescale_client.fetch(
            sql,
            f"{query_upper}%",     # Symbol starts with
            f"%{query_upper}%",    # Company name contains
            query_upper,           # Exact match priority
            f"{query_upper}%",     # Symbol starts with (for sorting)
            limit
        )
        
        tickers = [
            {
                "symbol": row["symbol"],
                "name": row["company_name"],
                "exchange": row["exchange"],
                "type": row["sector"],
                "displayName": f"{row['symbol']} - {row['company_name']}" if row['company_name'] else row['symbol']
            }
            for row in results
        ]
        
        return {
            "query": q,
            "results": tickers,
            "total": len(tickers)
        }
    
    except Exception as e:
        logger.error("search_error", error=str(e), query=q)
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


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
    
    # Convertir a dict con TODOS los campos
    return metadata.dict()


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
    
    # Convertir a dict con TODOS los campos
    result = metadata.dict()
    result["refreshed"] = True
    return result


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

