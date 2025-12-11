"""
Financial Analysis Router - HYBRID ARCHITECTURE

Endpoint para obtener datos financieros completos de un ticker:
- Income Statement (anual y trimestral)
- Balance Sheet (anual y trimestral)
- Cash Flow Statement (anual y trimestral)

ARQUITECTURA HÍBRIDA:
- SEC-API XBRL: Datos rápidos, pre-procesados (fuente principal)
- edgartools: Datos detallados, segmentos, geografía (enriquecimiento opcional)
- FMP Profile: Industry/Sector (solo para clasificación)
"""

import json
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Query

from shared.utils.redis_client import RedisClient
from shared.utils.logger import get_logger
from shared.models.financials import FinancialData
from services.fmp_financials import FMPFinancialsService
from services.sec_xbrl_financials import SECXBRLFinancialsService
from services.edgartools_service import get_edgartools_service, EdgarToolsService
from http_clients import TickerMetadataClient

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/financials", tags=["financials"])

# Clientes (se inyectan desde main.py)
_redis_client: Optional[RedisClient] = None
_fmp_service: Optional[FMPFinancialsService] = None
_sec_xbrl_service: Optional[SECXBRLFinancialsService] = None
_ticker_metadata_client: Optional[TickerMetadataClient] = None
_edgartools_service: Optional[EdgarToolsService] = None


def set_ticker_metadata_client(client: TickerMetadataClient):
    """Inyectar cliente de metadata para obtener CIK"""
    global _ticker_metadata_client
    _ticker_metadata_client = client

# TTL de caché largo (7 días - los financials históricos no cambian)
CACHE_TTL_SECONDS = 604800  # 7 días


def set_redis_client(client: RedisClient):
    """Inyectar cliente Redis"""
    global _redis_client
    _redis_client = client


def set_fmp_api_key(api_key: str):
    """Inicializar servicio FMP con API key (solo para industry/sector)"""
    global _fmp_service
    _fmp_service = FMPFinancialsService(api_key)


def set_sec_api_key(api_key: str, polygon_api_key: str = None):
    """Inicializar servicio SEC-API XBRL con API key y Polygon para splits"""
    global _sec_xbrl_service
    if api_key:
        _sec_xbrl_service = SECXBRLFinancialsService(
            api_key=api_key,
            polygon_api_key=polygon_api_key
        )
        logger.info(f"SEC XBRL service initialized (splits enabled: {bool(polygon_api_key)})")


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
    Obtiene datos financieros simbióticos de un ticker desde SEC-API XBRL.
    
    Formato simbiótico:
    - Campos consolidados semánticamente
    - Sin duplicados
    - Ordenados por importancia financiera
    
    Los datos se cachean en Redis por 7 días.
    """
    if not _sec_xbrl_service:
        raise HTTPException(status_code=500, detail="SEC-API XBRL service not configured")
    
    symbol = symbol.upper()
    cache_key = f"financials:symbiotic:{symbol}:{period}:{limit}"
    
    # Intentar obtener de caché si no es refresh
    if not refresh and _redis_client:
        try:
            cached = await _redis_client.get(cache_key, deserialize=False)
            if cached:
                data = json.loads(cached) if isinstance(cached, (str, bytes)) else cached
                if isinstance(data, str):
                    data = json.loads(data)
                
                # Verificar que tenemos datos (formato simbiótico)
                periods_count = len(data.get("periods", []))
                
                if periods_count >= limit * 0.8:
                    # Calcular edad del caché
                    if "last_updated" in data:
                        try:
                            cached_time = datetime.fromisoformat(data["last_updated"].replace("Z", "+00:00"))
                            age_seconds = int((datetime.now(cached_time.tzinfo) - cached_time).total_seconds())
                            data["cache_age_seconds"] = age_seconds
                        except:
                            pass
                    
                    data["cached"] = True
                    logger.info("financials_cache_hit", symbol=symbol, periods=periods_count)
                    return data
                else:
                    logger.info("financials_cache_incomplete", symbol=symbol, cached_periods=periods_count, requested=limit)
                    return data
        except Exception as e:
            logger.warning("financials_cache_error", symbol=symbol, error=str(e))
    
    # Obtener CIK del servicio de metadata (fuente única de verdad)
    # Esto garantiza que buscamos filings de la empresa ACTUAL, no de tickers reutilizados
    cik = None
    try:
        # Opción 1: Redis directo (más rápido)
        if _redis_client:
            metadata_raw = await _redis_client.get(f"metadata:ticker:{symbol}")
            if metadata_raw:
                metadata = json.loads(metadata_raw) if isinstance(metadata_raw, str) else metadata_raw
                cik = metadata.get("cik")
        
        # Opción 2: Fallback a TickerMetadataClient
        if not cik and _ticker_metadata_client:
            metadata = await _ticker_metadata_client.get_metadata(symbol)
            if metadata:
                cik = metadata.get("cik")
                
        if cik:
            logger.info("financials_cik_resolved", symbol=symbol, cik=cik)
        else:
            logger.warning("financials_cik_not_found", symbol=symbol, fallback="ticker-based search")
    except Exception as e:
        logger.warning("financials_cik_lookup_error", symbol=symbol, error=str(e))
    
    # Obtener datos frescos de SEC-API XBRL
    logger.info("financials_fetching_sec", symbol=symbol, period=period, limit=limit, cik=cik)
    
    try:
        raw_data = await _sec_xbrl_service.get_financials(symbol, period, limit, cik=cik)
        
        if not raw_data or not raw_data.get("income_statement"):
            raise HTTPException(status_code=404, detail=f"No financial data found for {symbol}")
        
        # Añadir industry/sector de FMP profile (para display)
        industry_display = None
        sector = None
        if _fmp_service:
            try:
                profile = await _fmp_service.get_profile(symbol)
                if profile:
                    industry_display = profile.get("industry")
                    sector = profile.get("sector")
            except Exception as e:
                logger.debug("fmp_profile_error", symbol=symbol, error=str(e))
        
        # Usar nuestro mapeo de industria (SIC-based) para estructura de campos
        # industry_code es para lógica interna (insurance, banking, etc.)
        # industry es para display (Medical - Healthcare Plans, etc.)
        industry_code = raw_data.get("industry")  # Nuestro mapeo SIC
        
        # Construir respuesta con formato simbiótico
        response_data = {
            "symbol": raw_data["symbol"],
            "currency": raw_data.get("currency", "USD"),
            "industry": industry_display or industry_code,  # Display name
            "industry_code": industry_code,  # Código interno (insurance, banking, etc.)
            "sector": sector,
            "source": "sec-api-xbrl",
            "symbiotic": True,
            "split_adjusted": raw_data.get("split_adjusted", False),
            "splits": raw_data.get("splits", []),
            "periods": raw_data.get("periods", []),
            "period_end_dates": raw_data.get("period_end_dates", []),  # Fechas exactas de cierre
            "fiscal_year_end_month": raw_data.get("fiscal_year_end_month"),  # Mes típico de cierre (1-12)
            "income_statement": raw_data.get("income_statement", []),
            "balance_sheet": raw_data.get("balance_sheet", []),
            "cash_flow": raw_data.get("cash_flow", []),
            "processing_time_seconds": raw_data.get("processing_time_seconds"),
            "last_updated": raw_data["last_updated"],
            "cached": False
        }
        
        # Guardar en caché
        if _redis_client:
            try:
                await _redis_client.set(
                    cache_key,
                    json.dumps(response_data),
                    ttl=CACHE_TTL_SECONDS,
                    serialize=False
                )
                logger.info("financials_cached", symbol=symbol, periods=len(raw_data.get("periods", [])), ttl_days=CACHE_TTL_SECONDS//86400)
            except Exception as e:
                logger.warning("financials_cache_save_error", symbol=symbol, error=str(e))
        
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("financials_error", symbol=symbol, error=str(e))
        raise HTTPException(status_code=500, detail=f"Error fetching financials: {str(e)}")


@router.get("/{symbol}/income")
async def get_income_statements(
    symbol: str,
    period: str = Query("annual", description="annual o quarter"),
    limit: int = Query(10, ge=1, le=30)
):
    """Obtiene solo los Income Statements"""
    data = await get_financials(symbol, period, limit)
    return data.income_statements


@router.get("/{symbol}/balance")
async def get_balance_sheets(
    symbol: str,
    period: str = Query("annual", description="annual o quarter"),
    limit: int = Query(10, ge=1, le=30)
):
    """Obtiene solo los Balance Sheets"""
    data = await get_financials(symbol, period, limit)
    return data.balance_sheets


@router.get("/{symbol}/cashflow")
async def get_cash_flows(
    symbol: str,
    period: str = Query("annual", description="annual o quarter"),
    limit: int = Query(10, ge=1, le=30)
):
    """Obtiene solo los Cash Flow Statements"""
    data = await get_financials(symbol, period, limit)
    return data.cash_flows


@router.post("/precache/{symbol}")
async def precache_ticker(
    symbol: str,
    period: str = Query("annual", description="annual o quarter"),
    limit: int = Query(10, ge=1, le=30)
):
    """
    Pre-cachear datos de un ticker específico.
    Útil para asegurar que los datos estén listos antes de que el usuario los pida.
    """
    try:
        from jobs.precache_financials import get_precache_job
        
        job = get_precache_job()
        if not job:
            raise HTTPException(status_code=503, detail="Precache job not initialized")
        
        success = await job.precache_ticker(symbol.upper(), period, limit)
        
        if success:
            return {"status": "success", "symbol": symbol, "period": period}
        else:
            return {"status": "partial", "symbol": symbol, "message": "Some data may be missing due to rate limits"}
            
    except Exception as e:
        logger.error("precache_error", symbol=symbol, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# EDGARTOOLS ENDPOINTS - Segmentos y Geografía (dimensiones XBRL)
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
    Cache: 24 horas.
    """
    symbol = symbol.upper()
    
    try:
        service = get_edgartools_service()
        data = await service.get_segments(symbol)
        
        if not data:
            raise HTTPException(
                status_code=404, 
                detail=f"No segment data for {symbol}"
            )
        
        return data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("segments_error", symbol=symbol, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{symbol}/segments/cache")
async def clear_segment_cache(symbol: str):
    """Limpiar cache de segmentos para un símbolo."""
    service = get_edgartools_service()
    service.clear_cache(symbol.upper())
    return {"status": "cleared", "symbol": symbol.upper()}


@router.get("/{symbol}/company-info")
async def get_company_info(symbol: str):
    """
    Obtener información de la empresa incluyendo industria.
    
    Returns:
        {
            "symbol": "UNH",
            "name": "UNITEDHEALTH GROUP INC",
            "sic": 6324,
            "industry": "insurance",
            "profile": {...}  # Campos específicos de la industria
        }
    """
    symbol = symbol.upper()
    
    try:
        service = get_edgartools_service()
        data = await service.get_company_info(symbol)
        
        if not data:
            # Fallback si edgartools falla
            return {
                "symbol": symbol,
                "name": None,
                "sic": None,
                "industry": None,
                "profile": None,
            }
        
        # Añadir perfil de industria si existe
        if data.get("industry"):
            # Perfiles de industria con campos específicos
            INDUSTRY_PROFILES = {
                'insurance': {
                    'income_fields': ['premiums_earned_net', 'policyholder_benefits_and_claims_incurred_net', 
                                     'medical_costs', 'operating_income', 'net_income'],
                    'key_metrics': ['medical_loss_ratio', 'combined_ratio', 'return_on_equity'],
                },
                'banking': {
                    'income_fields': ['interest_income_expense_net', 'provision_for_loan_losses',
                                     'noninterest_income', 'noninterest_expense', 'net_income'],
                    'key_metrics': ['net_interest_margin', 'efficiency_ratio', 'return_on_assets'],
                },
                'technology': {
                    'income_fields': ['revenue', 'gross_profit', 'rd_expenses', 
                                     'operating_income', 'ebitda', 'net_income'],
                    'key_metrics': ['gross_margin', 'operating_margin', 'rd_as_percent_of_revenue'],
                },
                'retail': {
                    'income_fields': ['revenue', 'gross_profit', 'sga_expenses',
                                     'operating_income', 'net_income'],
                    'key_metrics': ['gross_margin', 'operating_margin', 'inventory_turnover'],
                },
                'healthcare': {
                    'income_fields': ['revenue', 'gross_profit', 'rd_expenses',
                                     'operating_income', 'net_income'],
                    'key_metrics': ['gross_margin', 'rd_as_percent_of_revenue'],
                },
            }
            
            profile = INDUSTRY_PROFILES.get(data["industry"])
            if profile:
                data["profile"] = profile
        
        return data
        
    except Exception as e:
        logger.error("company_info_error", symbol=symbol, error=str(e))
        return {
            "symbol": symbol,
            "name": None,
            "sic": None,
            "industry": None,
            "profile": None,
            "error": str(e),
        }


# ============================================================================
# XBRL ENRICHER - Campos adicionales que SEC-API no extrae
# ============================================================================

@router.get("/{symbol}/income-details")
async def get_income_details(
    symbol: str,
    years: int = Query(5, ge=1, le=15, description="Años a extraer")
):
    """
    Obtener income statement completo con todos los componentes de revenue.
    
    Usa edgartools para extraer campos que SEC-API no proporciona:
    - Investment income
    - Contract revenue (products/services)  
    - Componentes detallados de costos
    
    Nota: Este endpoint es más lento (~5-10s) porque parsea el XBRL completo.
    Los datos se cachean por 24 horas.
    """
    symbol = symbol.upper()
    
    try:
        from services.xbrl_enricher import get_xbrl_enricher
        
        enricher = get_xbrl_enricher()
        data = await enricher.get_income_statement_details(symbol, years)
        
        if not data:
            raise HTTPException(
                status_code=404,
                detail=f"No detailed income data for {symbol}"
            )
        
        return data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("income_details_error", symbol=symbol, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
