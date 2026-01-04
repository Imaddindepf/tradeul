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
from calculators.dilution_tracker_risk_scorer import DilutionTrackerRiskScorer
from models.sec_dilution_models import DilutionProfileResponse

logger = get_logger(__name__)

# SPAC Detector (singleton)
spac_detector = SPACDetector()

# Risk Scorer (singleton)
risk_scorer = DilutionTrackerRiskScorer()


async def _calculate_risk_assessment(profile, dilution_analysis: dict, redis) -> dict:
    """
    Calculate DilutionTracker-style risk ratings from profile data.
    
    This function obtains additional data (shares history, cash runway) to 
    calculate all 5 risk ratings accurately like DilutionTracker.com.
    
    Returns dict with:
    - overall_risk: Low/Medium/High
    - offering_ability: Low/Medium/High
    - overhead_supply: Low/Medium/High
    - historical: Low/Medium/High
    - cash_need: Low/Medium/High
    """
    try:
        ticker = profile.ticker
        shares_outstanding = profile.shares_outstanding or 0
        
        # Calculate shares from warrants
        warrants_shares = sum(
            int(w.outstanding or w.total_issued or 0)
            for w in (profile.warrants or [])
        )
        
        # Calculate shares from ATM at current price
        atm_shares = 0
        if profile.current_price and profile.current_price > 0:
            for atm in (profile.atm_offerings or []):
                remaining = float(atm.remaining_capacity or 0)
                if remaining > 0:
                    atm_shares += int(remaining / float(profile.current_price))
        
        # Calculate shares from convertible notes
        convertible_shares = 0
        for note in (profile.convertible_notes or []):
            if note.remaining_shares_when_converted:
                convertible_shares += int(note.remaining_shares_when_converted)
            elif note.total_shares_when_converted:
                convertible_shares += int(note.total_shares_when_converted)
            elif note.conversion_price and note.conversion_price > 0:
                principal = float(note.remaining_principal_amount or note.total_principal_amount or 0)
                convertible_shares += int(principal / float(note.conversion_price))
        
        # Calculate shares from equity lines
        equity_line_shares = 0
        if profile.current_price and profile.current_price > 0:
            for el in (profile.equity_lines or []):
                remaining = float(el.remaining_capacity or 0)
                if remaining > 0:
                    equity_line_shares += int(remaining / float(profile.current_price))
        
        # Shelf capacity - consider Baby Shelf restriction
        # If float value < $75M, company can only use 1/3 of float value per 12 months
        shelf_capacity = 0
        has_active_shelf = False
        
        # Calculate float value for Baby Shelf check
        free_float = profile.free_float or profile.shares_outstanding or 0
        current_price = float(profile.current_price or 0)
        float_value = free_float * current_price
        is_baby_shelf_restricted = float_value < 75_000_000  # $75M threshold
        
        for shelf in (profile.shelf_registrations or []):
            if shelf.status in ['Active', 'Effective', None]:
                has_active_shelf = True
                remaining = float(shelf.remaining_capacity or shelf.total_capacity or 0)
                
                # Apply Baby Shelf limitation if applicable
                if is_baby_shelf_restricted:
                    # Can only raise 1/3 of float value per 12 months
                    baby_shelf_limit = float_value / 3
                    remaining = min(remaining, baby_shelf_limit)
                
                shelf_capacity += remaining
        
        logger.debug("shelf_capacity_calculated", 
                    ticker=ticker,
                    raw_capacity=sum(float(s.remaining_capacity or s.total_capacity or 0) 
                                    for s in (profile.shelf_registrations or []) 
                                    if s.status in ['Active', 'Effective', None]),
                    baby_shelf_restricted=is_baby_shelf_restricted,
                    float_value=float_value,
                    effective_capacity=shelf_capacity)
        
        # ===== HISTORICAL: Get shares current (from SEC history) and 3 years ago =====
        # IMPORTANT: For Historical rating, use SEC-reported shares (not "fully diluted")
        # This ensures we compare apples-to-apples: SEC current vs SEC 3yr ago
        shares_3yr_ago = 0
        shares_current_sec = 0  # Current shares from SEC filings (for Historical calc)
        try:
            from services.data.shares_data_service import SharesDataService
            from datetime import timedelta
            
            shares_service = SharesDataService(redis)
            shares_history = await shares_service.get_shares_history(ticker)
            
            if shares_history and shares_history.get("history"):
                hist = shares_history["history"]
                target_date = datetime.now() - timedelta(days=3*365)
                
                # Get MOST RECENT from SEC history (for "current" in Historical calc)
                sorted_hist = sorted(hist, key=lambda x: x.get("date", ""), reverse=True)
                if sorted_hist:
                    shares_current_sec = sorted_hist[0].get("shares", 0)
                    logger.debug("historical_current_from_sec", ticker=ticker,
                               date=sorted_hist[0].get("date"), shares=shares_current_sec)
                
                # Find closest date <= 3 years ago
                for h in sorted_hist:
                    try:
                        h_date = datetime.strptime(h.get("date", "")[:10], "%Y-%m-%d")
                        if h_date <= target_date:
                            shares_3yr_ago = h.get("shares", 0)
                            logger.debug("historical_shares_found", ticker=ticker, 
                                       date=h.get("date"), shares=shares_3yr_ago)
                            break
                    except:
                        continue
                        
                # If no 3yr ago data, use earliest available
                if shares_3yr_ago == 0 and hist:
                    earliest = min(hist, key=lambda x: x.get("date", "9999"))
                    shares_3yr_ago = earliest.get("shares", 0)
                    logger.debug("using_earliest_shares", ticker=ticker, shares=shares_3yr_ago)
        except Exception as e:
            logger.debug("shares_history_fetch_failed", ticker=ticker, error=str(e))
        
        # For Historical rating, use SEC-reported current (not profile's fully diluted)
        shares_for_historical = shares_current_sec if shares_current_sec > 0 else shares_outstanding
        
        # ===== CASH NEED: Get runway months =====
        runway_months = None
        has_positive_cf = False
        try:
            from services.sec.sec_cash_history import SECCashHistoryService
            
            cash_service = SECCashHistoryService(redis)
            cash_data = await cash_service.get_full_cash_history(ticker, max_quarters=20)
            
            if cash_data and not cash_data.get("error"):
                runway_days = cash_data.get("runway_days")
                if runway_days is not None:
                    runway_months = runway_days / 30
                quarterly_cf = cash_data.get("quarterly_operating_cf", 0)
                has_positive_cf = quarterly_cf > 0 if quarterly_cf else False
                logger.debug("cash_runway_found", ticker=ticker, 
                           runway_months=runway_months, has_positive_cf=has_positive_cf)
        except Exception as e:
            logger.debug("cash_history_fetch_failed", ticker=ticker, error=str(e))
        
        # Calculate ratings
        ratings = risk_scorer.calculate_all_ratings(
            # Offering Ability
            shelf_capacity_remaining=shelf_capacity,
            has_active_shelf=has_active_shelf,
            has_pending_s1=len(profile.s1_offerings or []) > 0,
            
            # Overhead Supply (uses fully diluted shares_outstanding)
            warrants_shares=warrants_shares,
            atm_shares=atm_shares,
            convertible_shares=convertible_shares,
            equity_line_shares=equity_line_shares,
            shares_outstanding=shares_outstanding,
            
            # Historical (uses SEC-reported shares, not fully diluted)
            shares_outstanding_3yr_ago=shares_3yr_ago,
            shares_outstanding_current_sec=shares_for_historical,  # From SEC filings
            
            # Cash Need
            runway_months=runway_months,
            has_positive_operating_cf=has_positive_cf,
            
            # Current price
            current_price=float(profile.current_price or 0)
        )
        
        return ratings.to_dict()
        
    except Exception as e:
        logger.warning("risk_assessment_calculation_failed", error=str(e))
        return {
            "overall_risk": "Unknown",
            "offering_ability": "Unknown",
            "overhead_supply": "Unknown",
            "historical": "Unknown",
            "cash_need": "Unknown",
            "error": str(e)
        }


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
                
                # RECALCULAR ATM potential_shares usando current_price y remaining_capacity
                # (el valor guardado puede estar mal si se calculó con total_capacity)
                current_price = float(profile.current_price or 0)
                if current_price > 0:
                    for atm in profile.atm_offerings:
                        if atm.remaining_capacity:
                            atm.potential_shares_at_current_price = int(float(atm.remaining_capacity) / current_price)
                
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
                
                # Calculate risk assessment (same as /profile endpoint)
                risk_assessment = await _calculate_risk_assessment(profile, dilution_analysis, redis)
                
                return {
                    "status": "cached",
                    "data": DilutionProfileResponse(
                        profile=profile,
                        dilution_analysis=dilution_analysis,
                        cached=True,
                        cache_age_seconds=cache_age,
                        is_spac=is_spac,
                        sic_code=None,
                        risk_assessment=risk_assessment
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
            
            # RECALCULAR ATM potential_shares usando current_price y remaining_capacity
            # (el valor guardado puede estar mal si se calculó con total_capacity)
            current_price = float(profile.current_price or 0)
            if current_price > 0:
                for atm in profile.atm_offerings:
                    if atm.remaining_capacity:
                        atm.potential_shares_at_current_price = int(float(atm.remaining_capacity) / current_price)
            
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
            
            # Calculate risk assessment (DilutionTracker-style ratings)
            risk_assessment = await _calculate_risk_assessment(profile, dilution_analysis, redis)
            
            return DilutionProfileResponse(
                profile=profile,
                dilution_analysis=dilution_analysis,
                cached=cached,
                cache_age_seconds=cache_age,
                is_spac=is_spac,
                sic_code=sic_code,
                risk_assessment=risk_assessment
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
    - Prorated CF = (Last Quarter Operating CF / 90) * days since report
    - Capital Raises = Extracted from 8-K filings
    - Estimated Cash = Latest Cash + Prorated CF + Capital Raises
    
    Incluye:
    - Historial COMPLETO de cash (hasta 10 años)
    - Historial de operating cash flow
    - Capital raises desde último reporte
    - Burn rate diario calculado
    - Estimated current cash (prorrateado + raises)
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
            from services.market.capital_raise_extractor import get_total_capital_raises
            
            # Get SEC XBRL cash history
            service = SECCashHistoryService(redis)
            result = await service.get_full_cash_history(ticker, max_quarters)
            
            if result.get("error"):
                raise HTTPException(status_code=404, detail=result["error"])
            
            # Get capital raises since last report
            last_report_date = result.get("last_report_date")
            if last_report_date:
                try:
                    capital_raises_raw = await get_total_capital_raises(ticker, last_report_date)
                    
                    # Normalize structure for frontend
                    total_raised = capital_raises_raw.get("total_gross_proceeds", 0) or capital_raises_raw.get("total", 0) or 0
                    raise_count = capital_raises_raw.get("raise_count", 0) or capital_raises_raw.get("count", 0) or 0
                    raise_details = capital_raises_raw.get("raises", []) or capital_raises_raw.get("details", [])
                    
                    result["capital_raises"] = {
                        "total": total_raised,
                        "count": raise_count,
                        "details": raise_details
                    }
                    
                    # Add capital raises to estimated cash
                    if total_raised > 0:
                        result["estimated_current_cash"] = (
                            result.get("estimated_current_cash", 0) + total_raised
                        )
                        logger.info("capital_raises_added", ticker=ticker, total=total_raised)
                except Exception as cr_err:
                    logger.warning("capital_raises_fetch_failed", ticker=ticker, error=str(cr_err))
                    result["capital_raises"] = {"total": 0, "count": 0, "details": []}
            else:
                result["capital_raises"] = {"total": 0, "count": 0, "details": []}
            
            return result
            
        finally:
            await redis.disconnect()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_cash_position_failed", ticker=ticker, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{ticker}/risk-ratings")
async def get_risk_ratings(ticker: str):
    """
    Obtener los 5 Risk Ratings de DilutionTracker.
    
    **Ratings:**
    1. **Overall Risk** - Combinación de los 4 sub-ratings (High = short bias)
    2. **Offering Ability** - Capacidad de ofertas: >$20M=High, $1M-$20M=Med, <$1M=Low
    3. **Overhead Supply** - Dilución potencial: >50%=High, 20-50%=Med, <20%=Low
    4. **Historical** - O/S growth 3yr: >100%=High, 30-100%=Med, <30%=Low
    5. **Cash Need** - Runway: <6mo=High, 6-24mo=Med, >24mo=Low
    
    **Ejemplo respuesta:**
    ```json
    {
        "overall_risk": "High",
        "offering_ability": "High",
        "overhead_supply": "Medium",
        "historical": "Low",
        "cash_need": "High",
        "scores": {
            "overall": 72,
            "offering_ability": 90,
            "overhead_supply": 45,
            "historical": 25,
            "cash_need": 85
        }
    }
    ```
    """
    try:
        ticker = ticker.upper()
        
        redis = RedisClient()
        await redis.connect()
        
        try:
            from calculators.dilution_tracker_risk_scorer import get_dt_risk_scorer
            from services.sec.sec_cash_history import SECCashHistoryService
            
            scorer = get_dt_risk_scorer()
            
            # 1. Get dilution profile from cache
            cache_key = f"sec_dilution:profile:{ticker}"
            profile = await redis.get(cache_key, deserialize=True)
            
            # 2. Get cash data
            cash_service = SECCashHistoryService(redis)
            cash_data = await cash_service.get_full_cash_history(ticker, max_quarters=40)
            
            # 3. Extract inputs for risk calculation
            warrants = profile.get("warrants", []) if profile else []
            atm_offerings = profile.get("atm_offerings", []) if profile else []
            shelf_registrations = profile.get("shelf_registrations", []) if profile else []
            convertible_notes = profile.get("convertible_notes", []) if profile else []
            shares_outstanding = profile.get("shares_outstanding", 0) if profile else 0
            
            # Calculate warrant shares
            total_warrant_shares = sum(
                w.get("remaining_warrants", 0) or w.get("outstanding", 0) or 0
                for w in warrants
            )
            
            # Calculate ATM shares (estimate from remaining capacity / current price)
            current_price = profile.get("current_price", 1) if profile else 1
            total_atm_shares = sum(
                int((a.get("remaining_capacity", 0) or 0) / max(current_price, 0.01))
                for a in atm_offerings
            )
            
            # Calculate convertible shares
            total_convertible_shares = sum(
                c.get("shares_if_converted", 0) or c.get("remaining_shares_to_be_issued", 0) or 0
                for c in convertible_notes
            )
            
            # Get shelf capacity
            active_shelves = [s for s in shelf_registrations if s.get("status", "").lower() in ["active", "effective", "registered"]]
            total_shelf_capacity = sum(
                s.get("remaining_capacity", 0) or s.get("current_raisable_amount", 0) or 0
                for s in active_shelves
            )
            has_active_shelf = len(active_shelves) > 0
            
            # Get runway from cash data
            runway_months = None
            has_positive_cf = False
            if cash_data and not cash_data.get("error"):
                runway_days = cash_data.get("runway_days")
                if runway_days is not None:
                    runway_months = runway_days / 30
                quarterly_cf = cash_data.get("quarterly_operating_cf", 0)
                has_positive_cf = quarterly_cf > 0 if quarterly_cf else False
            
            # Get historical O/S (3 years ago) from shares history
            shares_3yr_ago = 0
            try:
                from services.data.shares_data_service import SharesDataService
                from datetime import timedelta
                shares_service = SharesDataService(redis)
                shares_history = await shares_service.get_shares_history(ticker)
                
                if shares_history and shares_history.get("history"):
                    hist = shares_history["history"]
                    target_date = datetime.now() - timedelta(days=3*365)
                    
                    # Find closest date <= 3 years ago
                    for h in sorted(hist, key=lambda x: x.get("date", ""), reverse=True):
                        try:
                            h_date = datetime.strptime(h.get("date", "")[:10], "%Y-%m-%d")
                            if h_date <= target_date:
                                shares_3yr_ago = h.get("shares", 0)
                                logger.info("historical_shares_found", ticker=ticker, 
                                           date=h.get("date"), shares=shares_3yr_ago)
                                break
                        except:
                            continue
            except Exception as e:
                logger.warning("shares_history_fetch_for_risk_failed", ticker=ticker, error=str(e))
            
            # Calculate ratings
            ratings = scorer.calculate_all_ratings(
                shelf_capacity_remaining=total_shelf_capacity,
                has_active_shelf=has_active_shelf,
                has_pending_s1=False,  # Would need S-1 detection
                warrants_shares=total_warrant_shares,
                atm_shares=total_atm_shares,
                convertible_shares=total_convertible_shares,
                equity_line_shares=0,  # Would need ELOC detection
                shares_outstanding=shares_outstanding,
                shares_outstanding_3yr_ago=shares_3yr_ago or int(shares_outstanding * 0.7),  # Estimate if missing
                runway_months=runway_months,
                has_positive_operating_cf=has_positive_cf,
                current_price=current_price
            )
            
            result = ratings.to_dict()
            result["ticker"] = ticker
            result["data_available"] = profile is not None
            
            return result
            
        finally:
            await redis.disconnect()
        
    except Exception as e:
        logger.error("get_risk_ratings_failed", ticker=ticker, error=str(e))
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


# =============================================================================
# WARRANT LIFECYCLE ENDPOINTS (v5)
# =============================================================================

@router.get("/{ticker}/warrant-lifecycle")
async def get_warrant_lifecycle(
    ticker: str,
    force_extract: bool = Query(default=False, description="Force re-extraction of lifecycle events")
):
    """
    🔄 WARRANT LIFECYCLE ANALYSIS
    
    Obtiene el análisis completo del ciclo de vida de warrants:
    - Ejercicios (cash y cashless)
    - Ajustes de precio (splits, resets, anti-dilution)
    - Expiraciones y cancelaciones
    - Proceeds recibidos
    
    **Fuentes:**
    - 10-Q/10-K: Tablas de warrants con ejercicios/outstanding
    - 8-K Item 3.02: Ejercicios materiales
    - 8-K Item 5.03: Amendments
    
    **Parámetros:**
    - `ticker`: Símbolo de la acción
    - `force_extract`: True para re-extraer eventos (ignorando caché)
    
    **Respuesta:**
    ```json
    {
        "ticker": "VMAR",
        "lifecycle_summary": {
            "total_active_outstanding": 2000000,
            "total_exercised_to_date": 500000,
            "total_expired_cancelled": 100000,
            "exercise_rate_pct": 19.23
        },
        "proceeds": {
            "potential_if_all_exercised": 1000000,
            "actual_received_to_date": 250000,
            "realization_rate_pct": 25.0
        },
        "lifecycle_events": [...],
        "price_adjustments": [...],
        "by_type": {
            "Common": { "count": 2, "outstanding": 1500000 },
            "Pre-Funded": { "count": 1, "outstanding": 500000 }
        }
    }
    ```
    
    **Caché:** 24 horas (lifecycle events son relativamente estables)
    """
    try:
        ticker = ticker.upper()
        
        db = TimescaleClient()
        await db.connect()
        redis = RedisClient()
        await redis.connect()
        
        try:
            # 1. Obtener profile existente
            service = SECDilutionService(db, redis)
            profile = await service.get_dilution_profile(ticker, force_refresh=False)
            
            if not profile:
                raise HTTPException(
                    status_code=404,
                    detail=f"No dilution profile found for {ticker}. Try /profile first."
                )
            
            # 2. Check cache (unless force_extract)
            cache_key = f"warrant_lifecycle:{ticker}"
            if not force_extract:
                cached = await redis.get(cache_key, deserialize=True)
                if cached:
                    logger.info("warrant_lifecycle_cache_hit", ticker=ticker)
                    cached["cached"] = True
                    return cached
            
            # 3. Extract lifecycle events
            from services.extraction.lifecycle_extractor import get_lifecycle_extractor
            
            extractor = get_lifecycle_extractor()
            if not extractor:
                raise HTTPException(
                    status_code=503,
                    detail="Lifecycle extractor not available. Check API keys."
                )
            
            # Convert warrants to dict format
            known_warrants = [w.dict() for w in profile.warrants]
            
            # Extract lifecycle
            result = await extractor.extract_lifecycle(
                ticker=ticker,
                cik=profile.cik,
                known_warrants=known_warrants
            )
            
            # 4. Calculate lifecycle summary from profile method
            lifecycle_summary = profile.calculate_warrant_lifecycle_summary()
            
            # 5. Build response
            response = {
                "ticker": ticker,
                "company_name": profile.company_name,
                "lifecycle_summary": lifecycle_summary.get("summary", {}),
                "proceeds": lifecycle_summary.get("proceeds", {}),
                "by_type": lifecycle_summary.get("by_type", {}),
                "by_status": lifecycle_summary.get("by_status", {}),
                "in_the_money": lifecycle_summary.get("in_the_money", {}),
                "out_of_money": lifecycle_summary.get("out_of_money", {}),
                "lifecycle_activity": lifecycle_summary.get("lifecycle_activity", {}),
                "lifecycle_events": result.lifecycle_events,
                "price_adjustments": result.price_adjustments,
                "updated_totals": result.updated_totals,
                "current_price": float(profile.current_price) if profile.current_price else None,
                "extracted_at": datetime.now().isoformat(),
                "cached": False
            }
            
            # 6. Cache result (24 hours)
            await redis.set(cache_key, response, ttl=86400, serialize=True)
            
            return response
            
        finally:
            await db.disconnect()
            await redis.disconnect()
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.error("get_warrant_lifecycle_failed", ticker=ticker, error=str(e))
        raise HTTPException(status_code=500, detail=f"{str(e)}\n{tb}")


@router.get("/{ticker}/warrant-agreements")
async def get_warrant_agreements(ticker: str):
    """
    📜 WARRANT AGREEMENTS (Exhibit 4.x)
    
    Obtiene los Warrant Agreements presentados en los SEC filings.
    Incluye términos detallados extraídos de los documentos.
    
    **Busca en:**
    - Exhibit 4.1, 4.2, etc. en S-1, F-1, 8-K
    - Warrant Agreements adjuntos a offerings
    
    **Respuesta:**
    ```json
    {
        "ticker": "VMAR",
        "warrant_agreements": [
            {
                "exhibit_number": "4.1",
                "filing_date": "2024-08-15",
                "form_type": "F-1",
                "description": "Form of Common Warrant",
                "exhibit_url": "https://...",
                "terms": {
                    "exercise_price": 0.50,
                    "expiration_date": "2029-08-15",
                    "ownership_blocker": {
                        "has_blocker": true,
                        "blocker_percentage": 4.99
                    },
                    "anti_dilution": {
                        "has_anti_dilution": true,
                        "protection_type": "Weighted Average"
                    }
                }
            }
        ]
    }
    ```
    """
    try:
        ticker = ticker.upper()
        
        db = TimescaleClient()
        await db.connect()
        redis = RedisClient()
        await redis.connect()
        
        try:
            # 1. Get profile for CIK
            service = SECDilutionService(db, redis)
            profile = await service.get_dilution_profile(ticker, force_refresh=False)
            
            if not profile or not profile.cik:
                raise HTTPException(
                    status_code=404,
                    detail=f"No profile or CIK found for {ticker}"
                )
            
            # 2. Check cache
            cache_key = f"warrant_agreements:{ticker}"
            cached = await redis.get(cache_key, deserialize=True)
            if cached:
                cached["cached"] = True
                return cached
            
            # 3. Find warrant agreement exhibits
            from services.extraction.lifecycle_extractor import (
                find_warrant_agreement_exhibits,
                get_lifecycle_extractor
            )
            from services.extraction.contextual_extractor import SECAPIClient
            from shared.config.settings import settings
            import os
            
            sec_api_key = settings.SEC_API_IO_KEY or os.getenv('SEC_API_IO', '')
            if not sec_api_key:
                raise HTTPException(
                    status_code=503,
                    detail="SEC API key not configured"
                )
            
            sec_client = SECAPIClient(sec_api_key)
            exhibits = await find_warrant_agreement_exhibits(sec_client, profile.cik, ticker)
            
            # 4. Extract terms from each exhibit (limit to 5 most recent)
            extractor = get_lifecycle_extractor()
            
            warrant_agreements = []
            for exhibit in exhibits[:5]:  # Limit to 5 to avoid rate limits
                agreement = {
                    **exhibit,
                    "terms": None
                }
                
                # Try to extract terms
                if extractor and exhibit.get('exhibit_url'):
                    try:
                        terms = await extractor.extract_warrant_agreement(
                            filing_url=exhibit.get('filing_url', ''),
                            exhibit_url=exhibit.get('exhibit_url')
                        )
                        agreement["terms"] = terms
                    except Exception as e:
                        logger.warning("warrant_agreement_extract_failed", 
                                      exhibit=exhibit.get('exhibit_number'),
                                      error=str(e))
                
                warrant_agreements.append(agreement)
            
            # 5. Build response
            response = {
                "ticker": ticker,
                "company_name": profile.company_name,
                "warrant_agreements": warrant_agreements,
                "total_found": len(exhibits),
                "analyzed": len(warrant_agreements),
                "extracted_at": datetime.now().isoformat(),
                "cached": False
            }
            
            # 6. Cache (7 days - warrant agreements don't change often)
            await redis.set(cache_key, response, ttl=604800, serialize=True)
            
            return response
            
        finally:
            await db.disconnect()
            await redis.disconnect()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_warrant_agreements_failed", ticker=ticker, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{ticker}/warrants/{warrant_id}/history")
async def get_warrant_history(
    ticker: str,
    warrant_id: str
):
    """
    📊 WARRANT SERIES HISTORY
    
    Obtiene el historial completo de un warrant específico:
    - Todos los eventos (ejercicios, ajustes, etc.)
    - Timeline cronológico
    - Running totals
    
    **Parámetros:**
    - `ticker`: Símbolo de la acción
    - `warrant_id`: ID o series_name del warrant (ej: "August 2024 Common Warrants")
    
    **Respuesta:**
    ```json
    {
        "ticker": "VMAR",
        "warrant": {
            "series_name": "August 2024 Common Warrants",
            "current_outstanding": 1500000,
            "current_exercise_price": 0.50,
            "expiration_date": "2029-08-15"
        },
        "timeline": [
            {
                "date": "2024-08-15",
                "event_type": "Issuance",
                "warrants_affected": 2000000,
                "outstanding_after": 2000000
            },
            {
                "date": "2024-10-15",
                "event_type": "Exercise",
                "warrants_affected": 500000,
                "shares_issued": 500000,
                "proceeds": 250000,
                "outstanding_after": 1500000
            }
        ]
    }
    ```
    """
    try:
        ticker = ticker.upper()
        
        db = TimescaleClient()
        await db.connect()
        redis = RedisClient()
        await redis.connect()
        
        try:
            # 1. Get profile
            service = SECDilutionService(db, redis)
            profile = await service.get_dilution_profile(ticker, force_refresh=False)
            
            if not profile:
                raise HTTPException(status_code=404, detail=f"Profile not found for {ticker}")
            
            # 2. Find the warrant by ID or series_name
            target_warrant = None
            for w in profile.warrants:
                # Match by ID (if numeric) or series_name (if string)
                if warrant_id.isdigit():
                    if w.id == int(warrant_id):
                        target_warrant = w
                        break
                else:
                    # Fuzzy match on series_name
                    if w.series_name and warrant_id.lower() in w.series_name.lower():
                        target_warrant = w
                        break
            
            if not target_warrant:
                raise HTTPException(
                    status_code=404, 
                    detail=f"Warrant '{warrant_id}' not found. Available: {[w.series_name for w in profile.warrants]}"
                )
            
            # 3. Get lifecycle events for this warrant
            cache_key = f"warrant_lifecycle:{ticker}"
            lifecycle_data = await redis.get(cache_key, deserialize=True)
            
            timeline = []
            
            # Add issuance event
            if target_warrant.issue_date and target_warrant.total_issued:
                timeline.append({
                    "date": str(target_warrant.issue_date),
                    "event_type": "Issuance",
                    "warrants_affected": target_warrant.total_issued,
                    "outstanding_after": target_warrant.total_issued,
                    "details": {
                        "exercise_price": float(target_warrant.exercise_price) if target_warrant.exercise_price else None,
                        "expiration_date": str(target_warrant.expiration_date) if target_warrant.expiration_date else None
                    }
                })
            
            # Add events from lifecycle data
            if lifecycle_data:
                events = lifecycle_data.get('lifecycle_events', [])
                adjustments = lifecycle_data.get('price_adjustments', [])
                
                # Filter for this warrant
                for e in events:
                    if (target_warrant.series_name and 
                        e.get('series_name', '').lower() in target_warrant.series_name.lower()):
                        timeline.append({
                            "date": e.get('event_date'),
                            "event_type": e.get('event_type'),
                            "warrants_affected": e.get('warrants_affected'),
                            "shares_issued": e.get('shares_issued'),
                            "proceeds": e.get('proceeds_received'),
                            "outstanding_after": e.get('outstanding_after'),
                            "source": e.get('source_filing')
                        })
                
                for a in adjustments:
                    if (target_warrant.series_name and 
                        a.get('series_name', '').lower() in target_warrant.series_name.lower()):
                        timeline.append({
                            "date": a.get('adjustment_date'),
                            "event_type": f"Price_Adjustment ({a.get('adjustment_type')})",
                            "details": {
                                "price_before": a.get('price_before'),
                                "price_after": a.get('price_after'),
                                "trigger": a.get('trigger_event')
                            },
                            "source": a.get('source_filing')
                        })
            
            # Sort by date
            timeline.sort(key=lambda x: x.get('date', '') or '')
            
            # 4. Build response
            return {
                "ticker": ticker,
                "warrant": {
                    "id": target_warrant.id,
                    "series_name": target_warrant.series_name,
                    "warrant_type": target_warrant.warrant_type,
                    "current_outstanding": target_warrant.outstanding or target_warrant.remaining,
                    "current_exercise_price": float(target_warrant.exercise_price) if target_warrant.exercise_price else None,
                    "issue_date": str(target_warrant.issue_date) if target_warrant.issue_date else None,
                    "expiration_date": str(target_warrant.expiration_date) if target_warrant.expiration_date else None,
                    "total_issued": target_warrant.total_issued,
                    "exercised": target_warrant.exercised,
                    "expired": target_warrant.expired,
                    "status": target_warrant.status
                },
                "timeline": timeline,
                "total_events": len(timeline)
            }
            
        finally:
            await db.disconnect()
            await redis.disconnect()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_warrant_history_failed", ticker=ticker, warrant_id=warrant_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

