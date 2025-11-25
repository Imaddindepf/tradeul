"""
SEC Filings Service - FastAPI Main Application
Combina real-time (Stream API) + histórico (Query API)
"""
import asyncio
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query as QueryParam, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
import httpx

from config import settings
from models import (
    FilingsListResponse,
    FilingFilter,
    StreamStatus,
    BackfillStatus,
    FilingResponse,
)
from utils.database import db_client
from tasks.stream_client import stream_client
from tasks.query_client import query_client
from tasks.sec_stream_manager import SECStreamManager
import redis.asyncio as aioredis


# =====================================================
# LIFECYCLE MANAGEMENT
# =====================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manejo del ciclo de vida de la aplicación
    Inicia/detiene servicios de background
    """
    print("🚀 Starting SEC Filings Service...")
    
    # Conectar a base de datos
    await db_client.connect()
    
    # Conectar clientes
    await query_client.connect()
    
    # Conectar a Redis para SEC Stream Manager
    redis_client = None
    sec_stream_manager = None
    sec_stream_task = None
    
    if settings.SEC_API_IO:
        try:
            # Construir Redis URL
            if settings.REDIS_PASSWORD:
                redis_url = f"redis://:{settings.REDIS_PASSWORD}@{settings.REDIS_HOST}:{settings.REDIS_PORT}/0"
            else:
                redis_url = f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/0"
            
            redis_client = await aioredis.from_url(
                redis_url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=10
            )
            await redis_client.ping()
            print("✅ Connected to Redis for SEC Stream")
            
            # Crear e iniciar SEC Stream Manager
            if settings.STREAM_ENABLED:
                print("📡 Starting SEC Stream API WebSocket...")
                sec_stream_manager = SECStreamManager(
                    sec_api_key=settings.SEC_API_IO,
                    redis_client=redis_client,
                    stream_url=settings.SEC_STREAM_URL
                )
                sec_stream_task = asyncio.create_task(sec_stream_manager.start())
                print("✅ SEC Stream Manager started")
        except Exception as e:
            print(f"⚠️ Failed to start SEC Stream Manager: {e}")
    else:
        print("⚠️ SEC Stream API disabled (no API key)")
    
    # Iniciar Stream API legacy si está habilitado (mantener por compatibilidad)
    stream_task = None
    # if settings.STREAM_ENABLED and settings.SEC_API_IO:
    #     print("📡 Starting Stream API client (legacy)...")
    #     stream_task = asyncio.create_task(stream_client.run())
    
    # Hacer backfill inicial si está habilitado
    if settings.BACKFILL_ENABLED and settings.SEC_API_IO:
        print(f"🔄 Starting initial backfill ({settings.BACKFILL_DAYS_BACK} days)...")
        asyncio.create_task(
            query_client.backfill_recent(settings.BACKFILL_DAYS_BACK)
        )
    
    print("✅ SEC Filings Service ready!")
    
    yield
    
    # Shutdown
    print("🛑 Shutting down SEC Filings Service...")
    
    # Detener SEC Stream Manager
    if sec_stream_manager:
        await sec_stream_manager.stop()
        if sec_stream_task:
            sec_stream_task.cancel()
            try:
                await sec_stream_task
            except asyncio.CancelledError:
                pass
    
    # Cerrar Redis
    if redis_client:
        await redis_client.close()
    
    # Detener Stream API legacy
    if stream_task:
        await stream_client.disconnect()
        stream_task.cancel()
        try:
            await stream_task
        except asyncio.CancelledError:
            pass
    
    # Cerrar clientes
    await query_client.disconnect()
    await db_client.disconnect()
    
    print("✅ SEC Filings Service stopped")


# =====================================================
# FASTAPI APP
# =====================================================

app = FastAPI(
    title="SEC Filings Service",
    description="Real-time + historical SEC EDGAR filings",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, especificar orígenes
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =====================================================
# HEALTH & STATUS ENDPOINTS
# =====================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "sec-filings"}


@app.get("/status")
async def get_status():
    """Obtener estado general del servicio"""
    db_stats = await db_client.get_stats()
    stream_status = stream_client.get_status()
    backfill_status = query_client.get_status()
    
    return {
        "service": "sec-filings",
        "database": db_stats,
        "stream": stream_status,
        "backfill": backfill_status,
    }


@app.get("/stream/status", response_model=StreamStatus)
async def get_stream_status():
    """Obtener estado del Stream API"""
    status = stream_client.get_status()
    return StreamStatus(**status)


@app.get("/backfill/status", response_model=BackfillStatus)
async def get_backfill_status():
    """Obtener estado del backfill"""
    status = query_client.get_status()
    return BackfillStatus(**status)


# =====================================================
# FILINGS ENDPOINTS
# =====================================================

@app.get("/api/v1/filings", response_model=FilingsListResponse)
async def get_filings(
    ticker: Optional[str] = QueryParam(None, description="Ticker symbol"),
    form_type: Optional[str] = QueryParam(None, description="Form type (8-K, 10-K, etc.)"),
    cik: Optional[str] = QueryParam(None, description="CIK number"),
    date_from: Optional[date] = QueryParam(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[date] = QueryParam(None, description="End date (YYYY-MM-DD)"),
    items: Optional[str] = QueryParam(None, description="Comma-separated items (e.g., '1.03,9.01')"),
    page: int = QueryParam(1, ge=1, description="Page number"),
    page_size: int = QueryParam(50, ge=1, le=200, description="Page size (max 200)"),
):
    """
    Obtener filings con filtros
    
    Ejemplos:
    - `/api/v1/filings?ticker=TSLA&form_type=8-K&page=1&page_size=50`
    - `/api/v1/filings?date_from=2024-01-01&date_to=2024-12-31`
    - `/api/v1/filings?items=1.03&form_type=8-K`
    """
    # Parsear items si se proporciona
    items_list = items.split(",") if items else None
    
    # Crear filtros
    filters = FilingFilter(
        ticker=ticker,
        form_type=form_type,
        cik=cik,
        date_from=date_from,
        date_to=date_to,
        items=items_list,
        page=page,
        page_size=page_size,
    )
    
    # Obtener filings
    filings, total = await db_client.get_filings(filters)
    
    return FilingsListResponse(
        filings=filings,
        total=total,
        page=page,
        page_size=page_size,
        message=f"Found {total} filings"
    )


@app.get("/api/v1/filings/live", response_model=FilingsListResponse)
async def get_filings_live(
    ticker: Optional[str] = QueryParam(None, description="Ticker symbol"),
    form_type: Optional[str] = QueryParam(None, description="Form type (8-K, 10-K, etc.)"),
    date_from: Optional[date] = QueryParam(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[date] = QueryParam(None, description="End date (YYYY-MM-DD)"),
    page_size: int = QueryParam(50, ge=1, le=200, description="Page size (max 200)"),
    from_index: int = QueryParam(0, ge=0, description="Starting index for pagination"),
):
    """
    Búsqueda DIRECTA en SEC API (sin BD local)
    
    Usa esto cuando:
    - Necesitas datos inmediatos
    - El backfill no ha procesado esas fechas aún
    - Quieres datos frescos directo de SEC
    
    Ejemplos:
    - `/api/v1/filings/live?ticker=MNDR`
    - `/api/v1/filings/live?ticker=CMBM&form_type=8-K`
    """
    # Construir query Lucene
    query_parts = []
    
    if ticker:
        query_parts.append(f"ticker:({ticker})")
    
    if form_type:
        query_parts.append(f"formType:\"{form_type}\"")
    
    # Filtro de fechas con timestamps para incluir todo el día
    # Formato SEC API: filedAt:[2021-09-15T00:00:00 TO 2021-09-15T23:59:59]
    if date_from and date_to:
        # Incluir desde las 00:00:00 del date_from hasta las 23:59:59 del date_to
        query_parts.append(f"filedAt:[{date_from}T00:00:00 TO {date_to}T23:59:59]")
    elif date_from:
        # Desde date_from hasta hoy
        today = datetime.now().date()
        query_parts.append(f"filedAt:[{date_from}T00:00:00 TO {today}T23:59:59]")
    elif date_to:
        # Todo hasta date_to
        query_parts.append(f"filedAt:[* TO {date_to}T23:59:59]")
    
    # Si no hay filtros, traer todo (últimos 50)
    lucene_query = " AND ".join(query_parts) if query_parts else "*"
    
    try:
        # Query directo a SEC API con paginación
        response = await query_client.query_filings(lucene_query, from_index, min(page_size, 100))
        
        if not response or 'filings' not in response:
            return FilingsListResponse(
                filings=[],
                total=0,
                page=1,
                page_size=page_size,
                message="No filings found"
            )
        
        # Parsear filings
        filings = []
        for filing_data in response['filings']:
            filing = query_client.parse_filing(filing_data)
            if filing:
                # Convertir a dict con camelCase
                filing_dict = filing.model_dump(by_alias=True)
                filings.append(filing_dict)
        
        total = response.get('total', {}).get('value', len(filings))
        
        return FilingsListResponse(
            filings=filings,
            total=total,
            page=1,
            page_size=page_size,
            message=f"Found {len(filings)} filings (live from SEC API)"
        )
    
    except Exception as e:
        print(f"❌ Error querying live filings: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching live filings: {str(e)}"
        )


@app.get("/api/v1/filings/{accession_no}", response_model=FilingResponse)
async def get_filing_by_accession(accession_no: str):
    """Obtener filing por accession number"""
    filing = await db_client.get_filing_by_accession(accession_no)
    
    if not filing:
        raise HTTPException(status_code=404, detail=f"Filing {accession_no} not found")
    
    return FilingResponse(
        filing=filing,
        message="Filing found"
    )


@app.get("/api/v1/filings/latest/{count}")
async def get_latest_filings(count: int = 50):
    """Obtener los últimos N filings"""
    if count > 200:
        count = 200
    
    filters = FilingFilter(page=1, page_size=count)
    filings, total = await db_client.get_filings(filters)
    
    return {
        "filings": filings,
        "total": total,
        "count": len(filings)
    }


@app.get("/api/v1/proxy", response_class=HTMLResponse)
async def proxy_sec_filing(url: str = QueryParam(..., description="SEC.gov URL to proxy")):
    """
    Proxy para cargar filings de SEC.gov sin restricciones de CORS/X-Frame-Options
    
    Esto permite mostrar filings en iframe dentro de la app.
    Similar a Godel Terminal.
    """
    # Validar que la URL sea de SEC.gov
    if not url.startswith("https://www.sec.gov/") and not url.startswith("https://sec.gov/"):
        raise HTTPException(
            status_code=400,
            detail="Only SEC.gov URLs are allowed"
        )
    
    try:
        # SEC.gov requiere User-Agent con información de contacto
        # Referencia: https://www.sec.gov/os/accessing-edgar-data
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(url, headers={
                "User-Agent": "TradeUL App admin@tradeul.com",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Host": "www.sec.gov"
            })
            response.raise_for_status()
            
            # Devolver el HTML sin headers restrictivos
            return HTMLResponse(
                content=response.text,
                status_code=200,
                headers={
                    "Cache-Control": "public, max-age=3600",
                    "X-Content-Type-Options": "nosniff"
                }
            )
    
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Error fetching from SEC.gov: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Proxy error: {str(e)}"
        )


# =====================================================
# BACKFILL ENDPOINTS (Admin)
# =====================================================

@app.post("/api/v1/backfill/recent")
async def trigger_recent_backfill(
    background_tasks: BackgroundTasks,
    days: int = QueryParam(30, ge=1, le=365, description="Days back")
):
    """
    Trigger backfill de últimos N días (background task)
    """
    if query_client.stats["is_running"]:
        raise HTTPException(
            status_code=409,
            detail="Backfill already running"
        )
    
    background_tasks.add_task(query_client.backfill_recent, days)
    
    return {
        "message": f"Backfill started for last {days} days",
        "status": "running"
    }


@app.post("/api/v1/backfill/date-range")
async def trigger_date_range_backfill(
    background_tasks: BackgroundTasks,
    start_date: date = QueryParam(..., description="Start date (YYYY-MM-DD)"),
    end_date: date = QueryParam(..., description="End date (YYYY-MM-DD)"),
    form_types: Optional[str] = QueryParam(None, description="Comma-separated form types"),
):
    """
    Trigger backfill para un rango de fechas específico
    """
    if query_client.stats["is_running"]:
        raise HTTPException(
            status_code=409,
            detail="Backfill already running"
        )
    
    # Validar fechas
    if start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="start_date must be before end_date"
        )
    
    # Parsear form types
    form_types_list = form_types.split(",") if form_types else None
    
    if form_types_list:
        background_tasks.add_task(
            query_client.backfill_specific_forms,
            form_types_list,
            start_date,
            end_date
        )
    else:
        background_tasks.add_task(
            query_client.backfill_date_range,
            start_date,
            end_date
        )
    
    return {
        "message": f"Backfill started from {start_date} to {end_date}",
        "form_types": form_types_list or "all",
        "status": "running"
    }


# =====================================================
# STATS ENDPOINTS
# =====================================================

@app.get("/api/v1/stats")
async def get_stats():
    """Obtener estadísticas de la base de datos"""
    stats = await db_client.get_stats()
    return stats


@app.get("/api/v1/stats/by-ticker/{ticker}")
async def get_stats_by_ticker(ticker: str):
    """Obtener estadísticas para un ticker específico"""
    filters = FilingFilter(ticker=ticker.upper(), page=1, page_size=1)
    _, total = await db_client.get_filings(filters)
    
    return {
        "ticker": ticker.upper(),
        "total_filings": total
    }


@app.get("/api/v1/stats/by-form-type/{form_type}")
async def get_stats_by_form_type(form_type: str):
    """Obtener estadísticas para un form type específico"""
    filters = FilingFilter(form_type=form_type, page=1, page_size=1)
    _, total = await db_client.get_filings(filters)
    
    return {
        "form_type": form_type,
        "total_filings": total
    }


# =====================================================
# MAIN (para desarrollo local)
# =====================================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.SERVICE_PORT,
        reload=True,
        log_level=settings.LOG_LEVEL.lower()
    )

