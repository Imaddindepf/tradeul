"""
Statistics Router

Endpoints para estadísticas de mercado de tickers.
"""

from fastapi import APIRouter, HTTPException

import sys
sys.path.append('/app')

from shared.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.get("/{symbol}")
async def get_statistics(symbol: str):
    """
    Obtiene estadísticas de mercado del ticker
    
    Args:
        symbol: Símbolo del ticker
    
    Returns:
        Estadísticas: market cap, float, volumes, beta, etc
    """
    from main import metadata_manager
    
    if not metadata_manager:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    stats = await metadata_manager.get_statistics(symbol.upper())
    
    if not stats:
        raise HTTPException(status_code=404, detail=f"Statistics for {symbol} not found")
    
    return stats

