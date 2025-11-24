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
    Búsqueda ultrarrápida de tickers con PostgreSQL optimizado
    
    Optimizaciones aplicadas:
    - Índices GIN para full-text search en company_name
    - Índices B-tree en symbol para búsquedas por prefijo
    - Priorización de matches exactos y por prefijo
    - Caché implícito de PostgreSQL para queries frecuentes
    
    Args:
        q: Query string (ej: "AA", "Apple", etc.)
        limit: Máximo de resultados a devolver (default: 10, max: 50)
    
    Returns:
        JSON con lista de tickers que coinciden
        
    Performance target: < 50ms para queries típicas
    """
    from main import timescale_client, redis_client
    
    if not timescale_client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    query_upper = q.upper().strip()
    
    # Validación básica
    if len(query_upper) == 0:
        return {"query": q, "results": [], "total": 0}
    
    # Cache key para Redis (opcional)
    cache_key = f"ticker_search:{query_upper}:{limit}"
    
    # Intentar obtener de caché (si Redis está disponible)
    try:
        if redis_client:
            cached = await redis_client.get(cache_key)
            if cached:
                return cached
    except:
        pass  # Caché opcional, no bloquear por errores
    
    # Query optimizado con priorización inteligente
    sql = """
        SELECT 
            symbol, 
            company_name, 
            exchange, 
            sector, 
            is_actively_trading
        FROM tickers_unified
        WHERE 
            is_actively_trading = true
            AND (
                -- Búsqueda por símbolo (más común, más rápida)
                symbol ILIKE $1 || '%'
                OR 
                -- Búsqueda por nombre de empresa (con operador ~~* para índice GIN)
                company_name ILIKE '%' || $1 || '%'
            )
        ORDER BY 
            -- Priorización: exacto > prefijo > contains
            CASE 
                WHEN symbol = $1 THEN 0           -- Match exacto (máxima prioridad)
                WHEN symbol ILIKE $1 || '%' THEN 1  -- Symbol empieza con query
                WHEN company_name ILIKE $1 || '%' THEN 2  -- Company name empieza con query
                ELSE 3                             -- Contains en cualquier parte
            END,
            -- Desempate alfabético
            symbol ASC
        LIMIT $2
    """
    
    try:
        start_time = __import__('time').time()
        
        results = await timescale_client.fetch(
            sql,
            query_upper,  # $1 - query para búsqueda
            limit         # $2 - límite de resultados
        )
        
        elapsed_ms = (__import__('time').time() - start_time) * 1000
        
        # Formatear resultados
        tickers = [
            {
                "symbol": row["symbol"],
                "name": row["company_name"] or "",
                "exchange": row["exchange"] or "UNKNOWN",
                "type": row["sector"] or "N/A",
                "displayName": f"{row['symbol']} - {row['company_name']}" if row['company_name'] else row['symbol']
            }
            for row in results
        ]
        
        response_data = {
            "query": q,
            "results": tickers,
            "total": len(tickers),
            "elapsed_ms": round(elapsed_ms, 2)
        }
        
        # Guardar en caché (TTL: 5 minutos - los tickers no cambian frecuentemente)
        try:
            if redis_client and len(tickers) > 0:
                await redis_client.set(cache_key, response_data, ttl=300)
        except:
            pass  # No crítico
        
        # Log queries lentas (> 100ms)
        if elapsed_ms > 100:
            logger.warning("slow_ticker_search", query=q, elapsed_ms=elapsed_ms, results_count=len(tickers))
        
        return response_data
    
    except Exception as e:
        logger.error("search_error", error=str(e), query=q, error_type=type(e).__name__)
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

