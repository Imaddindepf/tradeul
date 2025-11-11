"""
Company Router

Endpoints para información de compañías.
"""

from fastapi import APIRouter, HTTPException

import sys
sys.path.append('/app')

from shared.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.get("/{symbol}")
async def get_company_profile(symbol: str):
    """
    Obtiene perfil completo de la compañía
    
    Args:
        symbol: Símbolo del ticker
    
    Returns:
        Perfil de la compañía
    """
    from main import metadata_manager
    
    if not metadata_manager:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    profile = await metadata_manager.get_company_profile(symbol.upper())
    
    if not profile:
        raise HTTPException(status_code=404, detail=f"Company profile for {symbol} not found")
    
    return profile


@router.get("/{symbol}/info")
async def get_company_info(symbol: str):
    """
    Obtiene información básica de la compañía
    
    Alias más simple que devuelve solo: nombre, exchange, sector, industria
    """
    from main import metadata_manager
    
    if not metadata_manager:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    profile = await metadata_manager.get_company_profile(symbol.upper())
    
    if not profile:
        raise HTTPException(status_code=404, detail=f"Company info for {symbol} not found")
    
    # Retornar solo info básica
    return {
        "symbol": profile["symbol"],
        "company_name": profile["company_name"],
        "exchange": profile["exchange"],
        "sector": profile["sector"],
        "industry": profile["industry"]
    }

