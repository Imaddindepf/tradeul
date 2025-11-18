"""
SEC Dilution Router
Endpoints para análisis de dilución basado en SEC filings
"""

import sys
sys.path.append('/app')

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import datetime

from shared.utils.timescale_client import TimescaleClient
from shared.utils.redis_client import RedisClient
from shared.utils.logger import get_logger

from services.sec_dilution_service import SECDilutionService
from models.sec_dilution_models import DilutionProfileResponse

logger = get_logger(__name__)

router = APIRouter(prefix="/api/sec-dilution", tags=["sec-dilution"])


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
            
            return DilutionProfileResponse(
                profile=profile,
                dilution_analysis=dilution_analysis,
                cached=cached,
                cache_age_seconds=cache_age
            )
            
        finally:
            await db.disconnect()
            await redis.disconnect()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_sec_dilution_profile_failed", ticker=ticker, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


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

