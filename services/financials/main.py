"""
Financials Microservice - Extracción y procesamiento de datos financieros.

Este microservicio se encarga de:
- Extraer datos XBRL desde SEC-API
- Enriquecer datos via edgartools
- Calcular métricas financieras
- Aplicar ajustes por splits
- Proveer estructuras jerárquicas para display

Arquitectura:
- SEC-API: Datos rápidos, pre-procesados (fuente principal)
- edgartools: Detalles, segmentos, geografía (enriquecimiento)
- Cache Redis: Datos de larga duración (7 días)
"""

import os
import json
from datetime import datetime
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import structlog
import redis.asyncio as redis

from services.sec_xbrl import SECXBRLService
from services.edgar import EdgarService
from services.fmp import FMPFinancialsService

# Logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
)
logger = structlog.get_logger(__name__)

# Configuración
SEC_API_KEY = os.getenv("SEC_API_IO", "")
FMP_API_KEY = os.getenv("FMP_API_KEY", "")
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "")
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")
PORT = int(os.getenv("FINANCIALS_PORT", "8020"))

# TTL de caché largo (7 días - los financials históricos no cambian)
CACHE_TTL_SECONDS = 604800

# Servicios globales
_sec_xbrl_service: Optional[SECXBRLService] = None
_edgar_service: Optional[EdgarService] = None
_fmp_service: Optional[FMPFinancialsService] = None
_redis_client: Optional[redis.Redis] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializar y limpiar recursos."""
    global _sec_xbrl_service, _edgar_service, _fmp_service, _redis_client
    
    # Inicializar Redis
    if REDIS_PASSWORD:
        _redis_client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            password=REDIS_PASSWORD,
            decode_responses=True,
        )
    else:
        _redis_client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            decode_responses=True,
        )
    
    try:
        await _redis_client.ping()
        logger.info("redis_connected", host=REDIS_HOST)
    except Exception as e:
        logger.warning("redis_connection_failed", error=str(e))
        _redis_client = None
    
    # Inicializar servicios
    if SEC_API_KEY:
        _sec_xbrl_service = SECXBRLService(
            api_key=SEC_API_KEY,
            polygon_api_key=POLYGON_API_KEY if POLYGON_API_KEY else None,
        )
        logger.info("sec_xbrl_service_initialized", splits_enabled=bool(POLYGON_API_KEY))
    else:
        logger.error("SEC_API_KEY not set - service will not work")
    
    if FMP_API_KEY:
        _fmp_service = FMPFinancialsService(api_key=FMP_API_KEY)
        logger.info("fmp_service_initialized")
    
    # EdgarService (para enrichment)
    _edgar_service = EdgarService(redis_client=_redis_client)
    logger.info("edgar_service_initialized")
    
    logger.info("financials_service_started", port=PORT)
    
    yield
    
    # Cleanup
    if _sec_xbrl_service:
        await _sec_xbrl_service.close()
    if _redis_client:
        await _redis_client.close()
    
    logger.info("financials_service_stopped")


app = FastAPI(
    title="Tradeul Financials Service",
    description="Servicio de datos financieros XBRL",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS (solo para desarrollo)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/health")
async def health():
    """Health check."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "sec_xbrl": _sec_xbrl_service is not None,
            "edgar": _edgar_service is not None,
            "fmp": _fmp_service is not None,
            "redis": _redis_client is not None,
        }
    }


@app.get("/api/v1/financials/{symbol}")
async def get_financials(
    symbol: str,
    period: str = Query("annual", description="annual o quarter"),
    limit: int = Query(10, ge=1, le=60, description="Number of periods (max 60 for quarterly ~15 years)"),
    refresh: bool = Query(False, description="Force refresh from API"),
):
    """
    Obtener datos financieros completos de un ticker.
    
    Args:
        symbol: Símbolo del ticker (ej: AAPL, GOOGL)
        period: "annual" para 10-K/20-F, "quarter" para 10-Q/6-K
        limit: Número de períodos a obtener (máx 30)
        refresh: Forzar recarga desde API
    
    Returns:
        Datos financieros en formato simbiótico con:
        - income_statement: Estado de resultados
        - balance_sheet: Balance general
        - cash_flow: Flujo de efectivo
        - Metadatos: períodos, splits, industria, etc.
    """
    if not _sec_xbrl_service:
        raise HTTPException(status_code=500, detail="SEC-API service not configured")
    
    symbol = symbol.upper()
    cache_key = f"financials:symbiotic:{symbol}:{period}:{limit}"
    
    # Intentar cache si no es refresh
    if not refresh and _redis_client:
        try:
            cached = await _redis_client.get(cache_key)
            if cached:
                data = json.loads(cached)
                data["cached"] = True
                logger.info(f"[{symbol}] Cache hit")
                return data
        except Exception as e:
            logger.warning(f"Cache read error: {e}")
    
    # Obtener datos frescos
    try:
        data = await _sec_xbrl_service.get_financials(
            ticker=symbol,
            period=period,
            limit=limit,
        )
        
        # Enriquecer con edgartools si disponible
        if _edgar_service:
            try:
                company_info = await _edgar_service.get_company_info(symbol)
                if company_info and company_info.sic:
                    data["industry_code"] = str(company_info.sic)
            except Exception as e:
                logger.debug(f"[{symbol}] Edgar enrichment skipped: {e}")
        
        # Enriquecer con FMP si disponible
        if _fmp_service:
            try:
                profile = await _fmp_service.get_company_profile(symbol)
                if profile:
                    data["industry"] = profile.get("industry", data.get("industry"))
                    data["sector"] = profile.get("sector", data.get("sector"))
            except Exception as e:
                logger.debug(f"[{symbol}] FMP enrichment skipped: {e}")
        
        data["cached"] = False
        data["last_updated"] = datetime.utcnow().isoformat()
        
        # Guardar en cache
        if _redis_client and data.get("periods"):
            try:
                await _redis_client.setex(
                    cache_key,
                    CACHE_TTL_SECONDS,
                    json.dumps(data),
                )
            except Exception as e:
                logger.warning(f"Cache write error: {e}")
        
        return data
        
    except Exception as e:
        import traceback
        logger.error(f"[{symbol}] Error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/financials/{symbol}/segments")
async def get_segments(symbol: str):
    """
    Obtener datos de segmentos y geografía via edgartools.
    
    Returns:
        - segments: Desglose por segmentos de negocio
        - geography: Desglose geográfico
        - products: Desglose por productos/servicios
    """
    if not _edgar_service:
        raise HTTPException(status_code=500, detail="Edgar service not configured")
    
    symbol = symbol.upper()
    
    try:
        segments = await _edgar_service.get_segments(symbol)
        
        if not segments:
            return {
                "symbol": symbol,
                "segments": {},
                "geography": {},
                "products": {},
            }
        
        return segments
        
    except Exception as e:
        logger.error(f"[{symbol}] Segments error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/financials/{symbol}/income-details")
async def get_income_details(
    symbol: str,
    years: int = Query(10, ge=1, le=15, description="Years of history"),
):
    """
    Obtener detalles del income statement via edgartools.
    
    Complementa los datos de SEC-API con:
    - Desglose de revenue (premiums, products, services)
    - Desglose de costos (medical costs, COGS, SG&A)
    - Campos que SEC-API no captura bien
    """
    if not _edgar_service:
        raise HTTPException(status_code=500, detail="Edgar service not configured")
    
    symbol = symbol.upper()
    
    try:
        enrichment = await _edgar_service.get_enrichment(symbol, max_years=years)
        
        return {
            "symbol": symbol,
            "periods": enrichment.periods,
            "fields": {k: v.model_dump() for k, v in enrichment.fields.items()},
            "filings_processed": enrichment.filings_processed,
            "extraction_time_ms": enrichment.extraction_time_ms,
            "errors": enrichment.errors,
        }
        
    except Exception as e:
        logger.error(f"[{symbol}] Income details error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/financials/cache/clear")
async def clear_cache(symbol: Optional[str] = None):
    """
    Limpiar cache de financials.
    
    Args:
        symbol: Ticker específico o None para limpiar todo
    """
    if not _redis_client:
        raise HTTPException(status_code=500, detail="Redis not configured")
    
    try:
        if symbol:
            pattern = f"financials:*{symbol.upper()}*"
        else:
            pattern = "financials:*"
        
        keys = await _redis_client.keys(pattern)
        if keys:
            await _redis_client.delete(*keys)
        
        count = len(keys)
        logger.info(f"Cache cleared: {count} keys")
        
        return {
            "cleared": count,
            "pattern": pattern,
        }
        
    except Exception as e:
        logger.error(f"Cache clear error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/financials/mapping/stats")
async def get_mapping_stats():
    """
    Obtener estadísticas del sistema de mapeo XBRL → Canonical.
    
    Returns:
        Estadísticas del sistema de mapeo incluyendo:
        - Total de mapeos en caché
        - Distribución por fuente (direct, regex, fasb, fallback)
        - Conceptos desconocidos pendientes
    """
    try:
        from services.mapping.adapter import get_mapper
        mapper = get_mapper()
        
        stats = mapper.get_stats()
        
        # Añadir stats de la base de datos si está disponible
        if _redis_client:
            try:
                # Contar claves de caché de financials
                keys = await _redis_client.keys("financials:*")
                stats["redis_cache_entries"] = len(keys)
            except Exception:
                stats["redis_cache_entries"] = None
        
        return {
            "status": "ok",
            "mapping_engine": stats,
            "quality_score_enabled": True,
            "description": {
                "direct": "Mapeo directo XBRL→Canonical (confianza=1.0)",
                "regex": "Patrón regex coincidido (confianza=0.95)",
                "fasb": "Etiqueta FASB US-GAAP (confianza=0.9)",
                "fallback": "Generado automáticamente (confianza=0.5)"
            }
        }
        
    except Exception as e:
        logger.error(f"Mapping stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)

