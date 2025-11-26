"""
Financial Analysis Router

Endpoint para obtener datos financieros completos de un ticker:
- Income Statement (anual y trimestral)
- Balance Sheet (anual y trimestral)
- Cash Flow Statement (anual y trimestral)

Usa FMP API (Financial Modeling Prep) con Redis para cachear respuestas.
"""

import json
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Query

from shared.utils.redis_client import RedisClient
from shared.utils.logger import get_logger
from shared.models.financials import FinancialData
from services.fmp_financials import FMPFinancialsService

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/financials", tags=["financials"])

# Clientes (se inyectan desde main.py)
_redis_client: Optional[RedisClient] = None
_fmp_service: Optional[FMPFinancialsService] = None

# TTL de caché (24 horas - los financials no cambian frecuentemente)
CACHE_TTL_SECONDS = 86400  # 24 horas


def set_redis_client(client: RedisClient):
    """Inyectar cliente Redis"""
    global _redis_client
    _redis_client = client


def set_fmp_api_key(api_key: str):
    """Inicializar servicio FMP con API key"""
    global _fmp_service
    _fmp_service = FMPFinancialsService(api_key)


# ============================================================================
# API Endpoints
# ============================================================================

@router.get("/{symbol}", response_model=FinancialData)
async def get_financials(
    symbol: str,
    period: str = Query("annual", description="annual o quarter"),
    limit: int = Query(5, ge=1, le=20, description="Number of periods"),
    refresh: bool = Query(False, description="Force refresh from API")
):
    """
    Obtiene datos financieros completos de un ticker.
    
    Incluye:
    - Income Statement (anual y/o trimestral)
    - Balance Sheet (anual y/o trimestral)
    - Cash Flow Statement (anual y/o trimestral)
    
    Los datos se cachean en Redis por 24 horas.
    """
    if not _fmp_service:
        raise HTTPException(status_code=500, detail="FMP service not configured")
    
    symbol = symbol.upper()
    cache_key = f"financials:fmp:{symbol}:{period}:{limit}"
    
    # Intentar obtener de caché si no es refresh
    if not refresh and _redis_client:
        try:
            cached = await _redis_client.get(cache_key, deserialize=False)
            if cached:
                data = json.loads(cached) if isinstance(cached, (str, bytes)) else cached
                if isinstance(data, str):
                    data = json.loads(data)
                
                # Calcular edad del caché
                if "last_updated" in data:
                    try:
                        cached_time = datetime.fromisoformat(data["last_updated"].replace("Z", "+00:00"))
                        age_seconds = int((datetime.now(cached_time.tzinfo) - cached_time).total_seconds())
                        data["cache_age_seconds"] = age_seconds
                    except:
                        pass
                
                data["cached"] = True
                logger.info("financials_cache_hit", symbol=symbol)
                return FinancialData(**data)
        except Exception as e:
            logger.warning("financials_cache_error", symbol=symbol, error=str(e))
    
    # Obtener datos frescos de FMP
    logger.info("financials_fetching_fmp", symbol=symbol, period=period, limit=limit)
    
    try:
        financial_data = await _fmp_service.get_financials(symbol, period, limit)
        
        if not financial_data:
            raise HTTPException(status_code=404, detail=f"No financial data found for {symbol}")
        
        # Guardar en caché
        if _redis_client:
            try:
                await _redis_client.set(
                    cache_key,
                    financial_data.model_dump_json(),
                    ttl=CACHE_TTL_SECONDS,
                    serialize=False
                )
                logger.info("financials_cached", symbol=symbol, ttl=CACHE_TTL_SECONDS)
            except Exception as e:
                logger.warning("financials_cache_save_error", symbol=symbol, error=str(e))
        
        return financial_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("financials_error", symbol=symbol, error=str(e))
        raise HTTPException(status_code=500, detail=f"Error fetching financials: {str(e)}")


@router.get("/{symbol}/income")
async def get_income_statements(
    symbol: str,
    period: str = Query("annual", description="annual o quarter"),
    limit: int = Query(5, ge=1, le=20)
):
    """Obtiene solo los Income Statements"""
    data = await get_financials(symbol, period, limit)
    return data.income_statements


@router.get("/{symbol}/balance")
async def get_balance_sheets(
    symbol: str,
    period: str = Query("annual", description="annual o quarter"),
    limit: int = Query(5, ge=1, le=20)
):
    """Obtiene solo los Balance Sheets"""
    data = await get_financials(symbol, period, limit)
    return data.balance_sheets


@router.get("/{symbol}/cashflow")
async def get_cash_flows(
    symbol: str,
    period: str = Query("annual", description="annual o quarter"),
    limit: int = Query(5, ge=1, le=20)
):
    """Obtiene solo los Cash Flow Statements"""
    data = await get_financials(symbol, period, limit)
    return data.cash_flows
