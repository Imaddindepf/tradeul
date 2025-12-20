"""
SEC Dilution Router
Endpoints para análisis de dilución basado en SEC filings
"""

import sys
sys.path.append('/app')

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from typing import Optional, AsyncGenerator
from datetime import datetime
import asyncio

from shared.utils.timescale_client import TimescaleClient
from shared.utils.redis_client import RedisClient
from shared.utils.logger import get_logger

from services.core.sec_dilution_service import SECDilutionService
from services.analysis.spac_detector import SPACDetector
from services.analysis.preliminary_analyzer import get_preliminary_analyzer
from services.market.cash_runway_service import get_enhanced_cash_runway
from models.sec_dilution_models import DilutionProfileResponse

logger = get_logger(__name__)

# SPAC Detector (singleton)
spac_detector = SPACDetector()

router = APIRouter(prefix="/api/sec-dilution", tags=["sec-dilution"])


@router.get("/{ticker}/check")
async def check_sec_dilution_cache(
    ticker: str,
    enqueue_if_missing: bool = Query(default=True, description="Auto-enqueue scraping job if no cache")
):
    """
    🚀 CHECK CACHE (NON-BLOCKING)
    
    Verifica si hay datos de dilución en caché para un ticker.
    NUNCA bloquea - retorna inmediatamente.
    
    **Flujo:**
    1. Chequea Redis (caché L1) - ~10ms
    2. Chequea PostgreSQL (caché L2) - ~50ms
    3. Si no hay datos:
       - Retorna `{"status": "no_cache"}`
       - Opcionalmente encola job de scraping
    
    **Uso ideal:**
    ```javascript
    const result = await checkSECCache(ticker);
    if (result.status === 'cached') {
        showData(result.data);
    } else {
        showPreliminaryTerminal();
        subscribeToJobNotifications(ticker);
    }
    ```
    
    **Respuestas:**
    - `{status: "cached", data: {...}}` - Datos disponibles
    - `{status: "no_cache", job_status: "queued|processing|none"}` - Sin datos
    """
    try:
        ticker = ticker.upper()
        
        db = TimescaleClient()
        await db.connect()
        redis = RedisClient()
        await redis.connect()
        
        try:
            service = SECDilutionService(db, redis)
            
            # Intentar obtener de caché SOLAMENTE (no bloquear)
            profile = await service.get_from_cache_only(ticker)
            
            if profile:
                # Hay datos en caché - devolverlos
                dilution_analysis = profile.calculate_potential_dilution()
                cache_age = None
                if profile.metadata.last_scraped_at:
                    cache_age = int((datetime.now() - profile.metadata.last_scraped_at).total_seconds())
                
                # No incluir source_filings para respuesta rápida
                profile.metadata.source_filings = []
                
                # SPAC detection (quick)
                is_spac = None
                try:
                    spac_result = await spac_detector.detect(ticker)
                    is_spac = spac_result.is_spac
                except:
                    pass
                
                return {
                    "status": "cached",
                    "data": DilutionProfileResponse(
                        profile=profile,
                        dilution_analysis=dilution_analysis,
                        cached=True,
                        cache_age_seconds=cache_age,
                        is_spac=is_spac,
                        sic_code=None
                    )
                }
            
            # No hay caché - verificar si hay job en progreso
            job_status = "none"
            job_id = None
            
            if enqueue_if_missing:
                # Encolar job automáticamente
                from services.external.job_queue_service import get_job_queue
                try:
                    queue = await get_job_queue()
                    
                    # Verificar si ya hay job
                    existing = await queue.get_job_status(ticker)
                    if existing:
                        job_status = existing.get("status", "unknown")
                        job_id = existing.get("job_id")
                    else:
                        # Encolar nuevo job
                        result = await queue.enqueue_scraping(ticker)
                        job_status = result.get("status", "queued")
                        job_id = result.get("job_id")
                        logger.info("auto_enqueued_scraping_job", ticker=ticker, job_id=job_id)
                except Exception as e:
                    logger.warning("failed_to_enqueue_job", ticker=ticker, error=str(e))
            
            return {
                "status": "no_cache",
                "ticker": ticker,
                "job_status": job_status,
                "job_id": job_id,
                "message": "Data not cached. Use /preliminary/stream for quick AI analysis while waiting."
            }
            
        finally:
            await db.disconnect()
            await redis.disconnect()
        
    except Exception as e:
        logger.error("check_sec_cache_failed", ticker=ticker, error=str(e))
        return {
            "status": "error",
            "ticker": ticker,
            "error": str(e)
        }


@router.get("/{ticker}/profile")
async def get_sec_dilution_profile(
    ticker: str,
    force_refresh: bool = Query(default=False, description="Force re-scraping ignoring cache"),
    include_filings: bool = Query(default=False, description="Include source filings in response (makes response 10x larger and slower)")
):
    """
    Obtener perfil completo de dilución SEC para un ticker
    
    Incluye:
    - Warrants outstanding
    - ATM offerings activos
    - Shelf registrations (S-3, S-1)
    - Completed offerings (histórico)
    - Análisis de dilución potencial
    
    **Caché:**
    - Primera solicitud: 10-60 segundos (scraping SEC + Grok API)
    - Siguientes solicitudes: <150ms (desde Redis o PostgreSQL)
    - TTL: 24 horas
    
    **Parámetros:**
    - `ticker`: Ticker symbol (ej: AAPL, TSLA, SOUN)
    - `force_refresh`: true para forzar re-scraping (ignora caché)
    - `include_filings`: true para incluir source_filings (no recomendado, usar /filings en su lugar)
    
    **Nota sobre performance:**
    Por defecto, este endpoint NO incluye los source_filings para mantener
    la respuesta rápida (~5KB, <150ms). Si necesitas ver los filings, usa:
    GET /api/sec-dilution/{ticker}/filings (con paginación)
    
    **Ejemplo:**
    ```
    GET /api/sec-dilution/SOUN/profile
    GET /api/sec-dilution/SOUN/profile?include_filings=true  # Más lento
    ```
    """
    try:
        ticker = ticker.upper()
        
        # Conectar a servicios
        db = TimescaleClient()
        await db.connect()
        redis = RedisClient()
        await redis.connect()
        
        try:
            # Obtener profile
            service = SECDilutionService(db, redis)
            profile = await service.get_dilution_profile(ticker, force_refresh=force_refresh)
            
            if not profile:
                raise HTTPException(
                    status_code=404,
                    detail=f"Could not retrieve dilution profile for {ticker}. Ticker may not exist or SEC data unavailable."
                )
            
            # Calcular análisis de dilución
            dilution_analysis = profile.calculate_potential_dilution()
            
            # Determinar si viene de caché
            cached = not force_refresh
            cache_age = None
            
            if cached and profile.metadata.last_scraped_at:
                cache_age = int((datetime.now() - profile.metadata.last_scraped_at).total_seconds())
            
            # 🚀 OPTIMIZACIÓN: Por defecto NO incluir source_filings
            # Esto reduce la respuesta de 62KB a ~5KB y mejora latencia de 900ms a <150ms
            if not include_filings:
                # Guardar count antes de limpiar
                filings_count = len(profile.metadata.source_filings)
                # Limpiar los filings para hacer la respuesta más ligera
                profile.metadata.source_filings = []
                # Añadir metadata útil
                logger.info("profile_response_optimized", 
                           ticker=ticker, 
                           filings_excluded=filings_count,
                           include_filings=include_filings)
            
            # Detect SPAC status
            is_spac = None
            sic_code = None
            try:
                spac_result = await spac_detector.detect(ticker)
                is_spac = spac_result.is_spac
                sic_code = spac_result.company_info.get("sic_code")
                if is_spac:
                    logger.info("spac_detected_in_profile", ticker=ticker, confidence=spac_result.confidence)
            except Exception as e:
                logger.debug("spac_detection_skipped", ticker=ticker, error=str(e))
            
            return DilutionProfileResponse(
                profile=profile,
                dilution_analysis=dilution_analysis,
                cached=cached,
                cache_age_seconds=cache_age,
                is_spac=is_spac,
                sic_code=sic_code
            )
            
        finally:
            await db.disconnect()
            await redis.disconnect()
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.error("get_sec_dilution_profile_failed", ticker=ticker, error=str(e))
        raise HTTPException(status_code=500, detail=f"{str(e)}\n{tb}")


@router.post("/{ticker}/refresh")
async def refresh_sec_dilution_profile(ticker: str):
    """
    Forzar actualización del perfil de dilución (invalidar caché + re-scraping)
    
    Esto:
    1. Invalida el caché Redis
    2. Fuerza re-scraping de SEC EDGAR
    3. Re-analiza con Grok API
    4. Actualiza PostgreSQL
    5. Re-cachea en Redis
    
    **Uso:**
    Llamar este endpoint cuando sepas que hay nuevos filings SEC o
    cuando quieras datos actualizados.
    
    **Ejemplo:**
    ```
    POST /api/sec-dilution/SOUN/refresh
    ```
    """
    try:
        ticker = ticker.upper()
        
        db = TimescaleClient()
        await db.connect()
        redis = RedisClient()
        await redis.connect()
        
        try:
            service = SECDilutionService(db, redis)
            
            # Invalidar caché
            await service.invalidate_cache(ticker)
            
            # Re-scraping
            profile = await service.get_dilution_profile(ticker, force_refresh=True)
            
            if not profile:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to refresh dilution profile for {ticker}"
                )
            
            return {
                "ticker": ticker,
                "status": "refreshed",
                "message": f"Dilution profile for {ticker} has been refreshed successfully",
                "scraped_at": profile.metadata.last_scraped_at.isoformat(),
                "source_filings_count": len(profile.metadata.source_filings)
            }
            
        finally:
            await db.disconnect()
            await redis.disconnect()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("refresh_sec_dilution_profile_failed", ticker=ticker, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{ticker}/warrants")
async def get_warrants(ticker: str):
    """
    Obtener solo los warrants de un ticker
    
    **Ejemplo:**
    ```
    GET /api/sec-dilution/SOUN/warrants
    ```
    """
    try:
        ticker = ticker.upper()
        
        db = TimescaleClient()
        await db.connect()
        redis = RedisClient()
        await redis.connect()
        
        try:
            service = SECDilutionService(db, redis)
            profile = await service.get_dilution_profile(ticker)
            
            if not profile:
                raise HTTPException(status_code=404, detail=f"Profile not found for {ticker}")
            
            return {
                "ticker": ticker,
                "warrants": [w.dict() for w in profile.warrants],
                "count": len(profile.warrants),
                "last_updated": profile.metadata.last_scraped_at.isoformat()
            }
            
        finally:
            await db.disconnect()
            await redis.disconnect()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_warrants_failed", ticker=ticker, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{ticker}/atm-offerings")
async def get_atm_offerings(ticker: str):
    """
    Obtener solo los ATM offerings de un ticker
    
    **Ejemplo:**
    ```
    GET /api/sec-dilution/SOUN/atm-offerings
    ```
    """
    try:
        ticker = ticker.upper()
        
        db = TimescaleClient()
        await db.connect()
        redis = RedisClient()
        await redis.connect()
        
        try:
            service = SECDilutionService(db, redis)
            profile = await service.get_dilution_profile(ticker)
            
            if not profile:
                raise HTTPException(status_code=404, detail=f"Profile not found for {ticker}")
            
            return {
                "ticker": ticker,
                "atm_offerings": [a.dict() for a in profile.atm_offerings],
                "count": len(profile.atm_offerings),
                "last_updated": profile.metadata.last_scraped_at.isoformat()
            }
            
        finally:
            await db.disconnect()
            await redis.disconnect()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_atm_offerings_failed", ticker=ticker, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{ticker}/shelf-registrations")
async def get_shelf_registrations(ticker: str):
    """
    Obtener solo las shelf registrations (S-3, S-1) de un ticker
    
    **Ejemplo:**
    ```
    GET /api/sec-dilution/SOUN/shelf-registrations
    ```
    """
    try:
        ticker = ticker.upper()
        
        db = TimescaleClient()
        await db.connect()
        redis = RedisClient()
        await redis.connect()
        
        try:
            service = SECDilutionService(db, redis)
            profile = await service.get_dilution_profile(ticker)
            
            if not profile:
                raise HTTPException(status_code=404, detail=f"Profile not found for {ticker}")
            
            return {
                "ticker": ticker,
                "shelf_registrations": [s.dict() for s in profile.shelf_registrations],
                "count": len(profile.shelf_registrations),
                "last_updated": profile.metadata.last_scraped_at.isoformat()
            }
            
        finally:
            await db.disconnect()
            await redis.disconnect()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_shelf_registrations_failed", ticker=ticker, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{ticker}/completed-offerings")
async def get_completed_offerings(ticker: str):
    """
    Obtener solo los completed offerings (histórico) de un ticker
    
    **Ejemplo:**
    ```
    GET /api/sec-dilution/SOUN/completed-offerings
    ```
    """
    try:
        ticker = ticker.upper()
        
        db = TimescaleClient()
        await db.connect()
        redis = RedisClient()
        await redis.connect()
        
        try:
            service = SECDilutionService(db, redis)
            profile = await service.get_dilution_profile(ticker)
            
            if not profile:
                raise HTTPException(status_code=404, detail=f"Profile not found for {ticker}")
            
            return {
                "ticker": ticker,
                "completed_offerings": [o.dict() for o in profile.completed_offerings],
                "count": len(profile.completed_offerings),
                "last_updated": profile.metadata.last_scraped_at.isoformat()
            }
            
        finally:
            await db.disconnect()
            await redis.disconnect()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_completed_offerings_failed", ticker=ticker, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{ticker}/filings")
async def get_sec_filings(
    ticker: str,
    page: int = Query(default=1, ge=1, description="Page number (starts at 1)"),
    limit: int = Query(default=50, ge=1, le=200, description="Items per page (max 200)"),
    form_type: Optional[str] = Query(default=None, description="Filter by form type (e.g., '10-K', '8-K')"),
    year: Optional[int] = Query(default=None, description="Filter by year")
):
    """
    Obtener los SEC filings procesados para un ticker (con paginación)
    
    Este endpoint devuelve los source filings que se usaron para el análisis de dilución.
    Es más ligero que el endpoint /profile y permite al usuario explorar todos los filings.
    
    **Paginación:**
    - `page`: Número de página (empieza en 1)
    - `limit`: Items por página (default 50, max 200)
    
    **Filtros opcionales:**
    - `form_type`: Filtrar por tipo (10-K, 8-K, 424B5, etc.)
    - `year`: Filtrar por año
    
    **Ejemplo:**
    ```
    GET /api/sec-dilution/SOUN/filings?page=1&limit=50
    GET /api/sec-dilution/SOUN/filings?form_type=10-K
    GET /api/sec-dilution/SOUN/filings?year=2024
    ```
    """
    try:
        ticker = ticker.upper()
        
        db = TimescaleClient()
        await db.connect()
        redis = RedisClient()
        await redis.connect()
        
        try:
            service = SECDilutionService(db, redis)
            profile = await service.get_dilution_profile(ticker)
            
            if not profile:
                raise HTTPException(status_code=404, detail=f"Profile not found for {ticker}")
            
            # Obtener todos los filings
            all_filings = profile.metadata.source_filings
            
            # Aplicar filtros
            filtered_filings = all_filings
            
            if form_type:
                filtered_filings = [f for f in filtered_filings if f.get('form_type') == form_type]
            
            if year:
                filtered_filings = [
                    f for f in filtered_filings 
                    if f.get('filing_date') and f['filing_date'].startswith(str(year))
                ]
            
            # Paginación
            total_count = len(filtered_filings)
            total_pages = (total_count + limit - 1) // limit  # Ceiling division
            
            start_idx = (page - 1) * limit
            end_idx = start_idx + limit
            
            paginated_filings = filtered_filings[start_idx:end_idx]
            
            return {
                "ticker": ticker,
                "filings": paginated_filings,
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total_items": total_count,
                    "total_pages": total_pages,
                    "has_next": page < total_pages,
                    "has_prev": page > 1
                },
                "filters": {
                    "form_type": form_type,
                    "year": year
                },
                "last_updated": profile.metadata.last_scraped_at.isoformat()
            }
            
        finally:
            await db.disconnect()
            await redis.disconnect()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_sec_filings_failed", ticker=ticker, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{ticker}/dilution-analysis")
async def get_dilution_analysis(ticker: str):
    """
    Obtener solo el análisis de dilución potencial (sin los datos raw)
    
    Calcula:
    - Total potential new shares
    - Dilution % breakdown (warrants, ATM, shelf)
    - Overall dilution %
    
    **Ejemplo:**
    ```
    GET /api/sec-dilution/SOUN/dilution-analysis
    ```
    """
    try:
        ticker = ticker.upper()
        
        db = TimescaleClient()
        await db.connect()
        redis = RedisClient()
        await redis.connect()
        
        try:
            service = SECDilutionService(db, redis)
            profile = await service.get_dilution_profile(ticker)
            
            if not profile:
                raise HTTPException(status_code=404, detail=f"Profile not found for {ticker}")
            
            dilution_analysis = profile.calculate_potential_dilution()
            
            return {
                "ticker": ticker,
                "company_name": profile.company_name,
                "current_price": float(profile.current_price) if profile.current_price else None,
                "shares_outstanding": profile.shares_outstanding,
                "dilution_analysis": dilution_analysis,
                "last_updated": profile.metadata.last_scraped_at.isoformat()
            }
            
        finally:
            await db.disconnect()
            await redis.disconnect()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_dilution_analysis_failed", ticker=ticker, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ========================================================================
# NEW: ENHANCED ENDPOINTS (SEC-API /float, FMP Cash, Risk Flags)
# ========================================================================

@router.get("/{ticker}/shares-history")
async def get_shares_history(ticker: str):
    """
    Obtener historial de shares outstanding desde SEC-API /float.
    
    Fuente oficial de la SEC - más precisa que otras APIs.
    
    Incluye:
    - Historial de shares outstanding por trimestre
    - Dilución calculada: 3 meses, 6 meses, 1 año, histórica
    - Public float USD
    - Source filings de la SEC
    
    **Caché:** 6 horas
    
    **Ejemplo:**
    ```
    GET /api/sec-dilution/SOUN/shares-history
    ```
    """
    try:
        ticker = ticker.upper()
        
        db = TimescaleClient()
        await db.connect()
        redis = RedisClient()
        await redis.connect()
        
        try:
            service = SECDilutionService(db, redis)
            result = await service.get_shares_history(ticker)
            
            if "error" in result:
                raise HTTPException(status_code=404, detail=result["error"])
            
            return result
            
        finally:
            await db.disconnect()
            await redis.disconnect()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_shares_history_failed", ticker=ticker, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{ticker}/cash-position")
async def get_cash_position(ticker: str, max_quarters: int = 40):
    """
    Obtener cash position y cash runway desde SEC-API.io XBRL.
    
    **Fuente:** SEC-API.io (datos oficiales de la SEC, NO FMP)
    
    **Metodología DilutionTracker:**
    - Cash = Cash & Equivalents + Short-Term Investments + Restricted Cash
    
    Incluye:
    - Historial COMPLETO de cash (hasta 10 años)
    - Historial de operating cash flow
    - Burn rate diario calculado
    - Estimated current cash (prorrateado desde último reporte)
    - Cash runway en días
    - Risk level (critical, high, medium, low)
    
    **Parámetros:**
    - max_quarters: Máximo de trimestres a obtener (default 40 = 10 años)
    
    **Caché:** 6 horas
    
    **Ejemplo:**
    ```
    GET /api/sec-dilution/GPRO/cash-position
    GET /api/sec-dilution/GPRO/cash-position?max_quarters=20
    ```
    """
    try:
        ticker = ticker.upper()
        
        redis = RedisClient()
        await redis.connect()
        
        try:
            from services.sec.sec_cash_history import SECCashHistoryService
            service = SECCashHistoryService(redis)
            result = await service.get_full_cash_history(ticker, max_quarters)
            
            if result.get("error"):
                raise HTTPException(status_code=404, detail=result["error"])
            
            return result
            
        finally:
            await redis.disconnect()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_cash_position_failed", ticker=ticker, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{ticker}/cash-runway-enhanced")
async def get_enhanced_cash_runway_endpoint(ticker: str, cik: Optional[str] = None):
    """
    Obtener cash runway MEJORADO usando metodología de DilutionTracker.com
    
    Formula:
        Estimated Cash = Historical Cash + Prorated CF + Capital Raises
    
    Incluye:
    - Historical cash desde SEC-API.io XBRL (o FMP como fallback)
    - Operating cash flow prorrateado por días desde último reporte
    - Capital raises extraídos de 8-K filings (Item 1.01/3.02)
    - Runway calculado en días y meses
    - Risk level (critical, high, medium, low)
    
    **Ejemplo:**
    ```
    GET /api/sec-dilution/YCBD/cash-runway-enhanced
    ```
    
    **Respuesta incluye:**
    - historical_cash: Cash reportado en último 10-Q/10-K
    - prorated_cf: Cash flow prorrateado desde fecha del reporte
    - capital_raises: Total de capital raises desde último reporte
    - estimated_current_cash: Suma de los anteriores
    - runway_days/months: Estimación de runway
    """
    try:
        ticker = ticker.upper()
        
        result = await get_enhanced_cash_runway(ticker, cik)
        
        if result.get("error"):
            raise HTTPException(status_code=404, detail=result["error"])
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_enhanced_cash_runway_failed", ticker=ticker, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{ticker}/enhanced-profile")
async def get_enhanced_profile(
    ticker: str,
    force_refresh: bool = Query(default=False, description="Force re-scraping ignoring cache")
):
    """
    Obtener perfil de dilución COMPLETO y MEJORADO.
    
    Este endpoint combina TODO en una sola llamada:
    - Perfil SEC estándar (warrants, ATM, shelf, etc.)
    - Historial de shares outstanding (SEC-API /float)
    - Cash position y runway (FMP)
    - Risk flags automáticos
    - Stats de optimización
    
    **Ideal para:** Dashboard de dilución completo
    
    **Caché:** Varía por componente (profile: 24h, shares: 6h, cash: 4h)
    
    **Ejemplo:**
    ```
    GET /api/sec-dilution/SOUN/enhanced-profile
    ```
    """
    try:
        ticker = ticker.upper()
        
        db = TimescaleClient()
        await db.connect()
        redis = RedisClient()
        await redis.connect()
        
        try:
            service = SECDilutionService(db, redis)
            result = await service.get_enhanced_dilution_profile(ticker, force_refresh=force_refresh)
            
            if "error" in result and result.get("profile") is None:
                raise HTTPException(status_code=404, detail=result.get("error", "Profile not found"))
            
            return result
            
        finally:
            await db.disconnect()
            await redis.disconnect()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_enhanced_profile_failed", ticker=ticker, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# PRELIMINARY ANALYSIS ENDPOINTS (AI-POWERED)
# =============================================================================

@router.get("/{ticker}/preliminary/stream")
async def stream_preliminary_analysis(
    ticker: str,
    company_name: Optional[str] = Query(default=None, description="Company name for better analysis context")
):
    """
    🔬 STREAMING PRELIMINARY DILUTION ANALYSIS
    
    Devuelve análisis en tiempo real con formato de terminal.
    Ideal para UX interactiva donde el usuario ve el análisis "en vivo".
    
    **Formato:** Server-Sent Events (SSE)
    **Tiempo:** 15-30 segundos típicamente
    **Uso:** 
    ```javascript
    const eventSource = new EventSource('/api/sec-dilution/MULN/preliminary/stream');
    eventSource.onmessage = (event) => {
        terminal.append(event.data);
    };
    ```
    
    **Output:** Texto formateado como terminal con secciones:
    - [SCAN] Búsqueda en SEC EDGAR
    - [RISK] Score de dilución (1-10)
    - [WARRANTS] Detalles de warrants
    - [ATM/SHELF] Ofertas activas
    - [CASH] Posición de efectivo
    - [FLAGS] Red flags detectados
    - [VERDICT] Opinión del analista
    """
    ticker = ticker.upper()
    logger.info("preliminary_stream_requested", ticker=ticker)
    
    analyzer = get_preliminary_analyzer()
    
    async def generate_sse() -> AsyncGenerator[str, None]:
        """Generator for SSE events."""
        try:
            async for chunk in analyzer.analyze_streaming(ticker, company_name or ticker):
                # Split chunk by lines and send each line as separate SSE event
                # This ensures proper SSE format where each line has the data: prefix
                lines = chunk.split('\n')
                for i, line in enumerate(lines):
                    # Send the line content
                    yield f"data: {line}\n"
                    # After each line except the last, yield empty data to preserve newlines
                    if i < len(lines) - 1:
                        yield "data: \n"
                yield "\n"  # End of SSE event
            
            # Send done signal
            yield "data: [STREAM_END]\n\n"
            
        except Exception as e:
            logger.error("preliminary_stream_error", ticker=ticker, error=str(e))
            yield f"data: [ERROR] {str(e)}\n\n"
    
    return StreamingResponse(
        generate_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )


@router.get("/{ticker}/preliminary")
async def get_preliminary_analysis(
    ticker: str,
    company_name: Optional[str] = Query(default=None, description="Company name for better context"),
    mode: str = Query(default="full", description="Analysis mode: 'full' (45s) or 'quick' (15s)")
):
    """
    📊 PRELIMINARY DILUTION ANALYSIS (JSON)
    
    Análisis preliminar usando AI con búsqueda web.
    Útil cuando NO tenemos datos en caché/BD.
    
    **Modos:**
    - `full`: Análisis completo (~45 segundos)
    - `quick`: Snapshot rápido (~15 segundos)
    
    **Cuándo usar:**
    1. Ticker no existe en nuestra BD
    2. Usuario quiere análisis inmediato antes del scraping SEC
    3. Fallback cuando SEC scraping falla
    
    **Output incluye:**
    - Risk score (1-10)
    - Warrants, ATM, Shelf details
    - Cash position y runway
    - Red flags identificados
    - Analyst opinion
    
    **Diferencia con /profile:**
    - /preliminary: AI + web search (rápido, aproximado)
    - /profile: SEC scraping real (lento, preciso)
    """
    ticker = ticker.upper()
    logger.info("preliminary_analysis_requested", ticker=ticker, mode=mode)
    
    analyzer = get_preliminary_analyzer()
    
    try:
        if mode == "quick":
            result = await analyzer.quick_lookup(ticker)
        else:
            result = await analyzer.analyze_json(ticker, company_name or ticker)
        
        return result
        
    except Exception as e:
        logger.error("preliminary_analysis_failed", ticker=ticker, error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Preliminary analysis failed: {str(e)}"
        )


@router.get("/{ticker}/preliminary/quick")
async def get_quick_preliminary(ticker: str):
    """
    ⚡ ULTRA-FAST DILUTION RISK SNAPSHOT
    
    Devuelve nivel de riesgo en <5 segundos.
    Ideal para mostrar mientras carga el análisis completo.
    
    **Output:**
    ```json
    {
        "ticker": "MULN",
        "quick_risk_level": "CRITICAL",
        "one_liner": "High dilution risk due to active ATM and low cash",
        "key_concern": "Monthly ATM usage depleting shelf",
        "data_found": true
    }
    ```
    """
    ticker = ticker.upper()
    analyzer = get_preliminary_analyzer()
    
    try:
        return await analyzer.quick_lookup(ticker)
    except Exception as e:
        logger.error("quick_preliminary_failed", ticker=ticker, error=str(e))
        return {
            "ticker": ticker,
            "quick_risk_level": "UNKNOWN",
            "one_liner": "Unable to fetch quick analysis",
            "data_found": False,
            "error": str(e)
        }


# =============================================================================
# JOB QUEUE ENDPOINTS (BACKGROUND SCRAPING)
# =============================================================================

@router.post("/{ticker}/jobs/scrape")
async def enqueue_scraping_job(
    ticker: str,
    company_name: Optional[str] = Query(default=None),
    priority: bool = Query(default=False, description="High priority job (processed first)"),
    force_refresh: bool = Query(default=False, description="Force re-scraping even if cached")
):
    """
    📋 ENCOLAR JOB DE SCRAPING SEC
    
    Encola un job de scraping en background y retorna inmediatamente.
    El scraping se procesa asíncronamente por el worker ARQ.
    
    **Flujo:**
    1. Usuario llama POST /jobs/scrape → Retorna job_id inmediatamente
    2. Worker procesa el scraping en background (30-60s)
    3. Usuario puede:
       - Polling: GET /jobs/{ticker}/status
       - WebSocket: Escuchar notificaciones de completion
    
    **Parámetros:**
    - `ticker`: Símbolo del ticker
    - `company_name`: Nombre de la empresa (mejora contexto AI)
    - `priority`: true para jobs urgentes
    - `force_refresh`: true para ignorar cache
    
    **Respuesta:**
    ```json
    {
        "status": "queued",
        "ticker": "MULN",
        "job_id": "abc123...",
        "priority": false,
        "queued_at": "2024-01-15T10:30:00Z"
    }
    ```
    """
    from services.external.job_queue_service import get_job_queue
    
    ticker = ticker.upper()
    logger.info("enqueue_scraping_requested", ticker=ticker, priority=priority)
    
    try:
        queue = await get_job_queue()
        result = await queue.enqueue_scraping(
            ticker=ticker,
            company_name=company_name,
            force_refresh=force_refresh,
            priority=priority
        )
        return result
        
    except Exception as e:
        logger.error("enqueue_scraping_failed", ticker=ticker, error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to enqueue scraping job: {str(e)}"
        )


@router.get("/{ticker}/jobs/status")
async def get_job_status(ticker: str):
    """
    📊 ESTADO DEL JOB DE SCRAPING
    
    Obtiene el estado actual del job de scraping para un ticker.
    Útil para polling mientras el job está en proceso.
    
    **Estados posibles:**
    - `queued`: En cola, esperando worker
    - `processing`: Worker procesando activamente
    - `completed`: Terminado exitosamente
    - `failed`: Falló (ver error en respuesta)
    - `null`: No hay job para este ticker
    
    **Respuesta:**
    ```json
    {
        "ticker": "MULN",
        "status": "processing",
        "job_id": "abc123...",
        "updated_at": "2024-01-15T10:30:45Z"
    }
    ```
    """
    from services.external.job_queue_service import get_job_queue
    
    ticker = ticker.upper()
    
    try:
        queue = await get_job_queue()
        status = await queue.get_job_status(ticker)
        
        if not status:
            return {
                "ticker": ticker,
                "status": None,
                "message": "No job found for this ticker"
            }
        
        return {
            "ticker": ticker,
            **status
        }
        
    except Exception as e:
        logger.error("get_job_status_failed", ticker=ticker, error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get job status: {str(e)}"
        )


@router.get("/jobs/stats")
async def get_queue_stats():
    """
    📈 ESTADÍSTICAS DE LA COLA DE JOBS
    
    Obtiene estadísticas generales de la cola de jobs.
    
    **Respuesta:**
    ```json
    {
        "queued_jobs": 3,
        "timestamp": "2024-01-15T10:30:00Z"
    }
    ```
    """
    from services.external.job_queue_service import get_job_queue
    
    try:
        queue = await get_job_queue()
        return await queue.get_queue_stats()
        
    except Exception as e:
        logger.error("get_queue_stats_failed", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get queue stats: {str(e)}"
        )

