"""
SEC Filings Service - FastAPI Main Application
Combina real-time (Stream API) + histórico (Query API)
"""
import asyncio
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query as QueryParam, BackgroundTasks, Request
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
            
            # Guardar en app.state para acceso desde endpoints
            app.state.redis_client = redis_client
            
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


def build_lucene_query(
    ticker: Optional[str] = None,
    form_types: Optional[List[str]] = None,
    items: Optional[List[str]] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> str:
    """
    Construye una query Lucene compleja para SEC-API.io
    
    Sintaxis Lucene soportada por SEC-API:
    - ticker:(AAPL) - por ticker
    - formType:"8-K" - por form type exacto
    - formType:(8-K OR 10-K) - múltiples form types
    - items:"1.01" - items de 8-K
    - filedAt:[2024-01-01 TO 2024-12-31] - rango de fechas
    """
    query_parts = []
    
    # Ticker filter
    if ticker:
        # Soportar múltiples tickers separados por coma
        tickers = [t.strip().upper() for t in ticker.split(',')]
        if len(tickers) == 1:
            query_parts.append(f'ticker:({tickers[0]})')
        else:
            ticker_query = ' OR '.join(tickers)
            query_parts.append(f'ticker:({ticker_query})')
    
    # Form types filter - IMPORTANTE: usar OR para múltiples tipos
    if form_types:
        # Limpiar y filtrar tipos válidos
        clean_types = [ft.strip() for ft in form_types if ft.strip()]
        if clean_types:
            if len(clean_types) == 1:
                query_parts.append(f'formType:"{clean_types[0]}"')
            else:
                # Múltiples form types: formType:("8-K" OR "10-K" OR "10-Q")
                types_query = ' OR '.join([f'"{ft}"' for ft in clean_types])
                query_parts.append(f'formType:({types_query})')
    
    # 8-K Items filter
    if items:
        # Items vienen como ["1.01", "2.02", etc]
        clean_items = [item.strip() for item in items if item.strip()]
        if clean_items:
            if len(clean_items) == 1:
                query_parts.append(f'items:"{clean_items[0]}"')
            else:
                items_query = ' OR '.join([f'"{item}"' for item in clean_items])
                query_parts.append(f'items:({items_query})')
    
    # Date range filter
    # Formato SEC API: filedAt:[2021-09-15T00:00:00 TO 2021-09-15T23:59:59]
    if date_from and date_to:
        query_parts.append(f'filedAt:[{date_from}T00:00:00 TO {date_to}T23:59:59]')
    elif date_from:
        today = datetime.now().date()
        query_parts.append(f'filedAt:[{date_from}T00:00:00 TO {today}T23:59:59]')
    elif date_to:
        query_parts.append(f'filedAt:[* TO {date_to}T23:59:59]')
    
    # Combinar con AND
    return ' AND '.join(query_parts) if query_parts else '*'


@app.get("/api/v1/filings/live", response_model=FilingsListResponse)
async def get_filings_live(
    ticker: Optional[str] = QueryParam(None, description="Ticker symbol (comma-separated for multiple)"),
    form_types: Optional[str] = QueryParam(None, description="Form types comma-separated (8-K,10-K,10-Q)"),
    items: Optional[str] = QueryParam(None, description="8-K Items comma-separated (1.01,2.02,5.02)"),
    date_from: Optional[date] = QueryParam(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[date] = QueryParam(None, description="End date (YYYY-MM-DD)"),
    page_size: int = QueryParam(50, ge=1, le=200, description="Page size (max 200)"),
    from_index: int = QueryParam(0, ge=0, description="Starting index for pagination"),
):
    """
    Búsqueda DIRECTA en SEC API con queries Lucene complejas
    
    Características:
    - Soporta múltiples form types (ej: form_types=8-K,10-K,10-Q)
    - Soporta filtro por items de 8-K (ej: items=1.01,2.02)
    - Soporta rangos de fechas
    - Paginación eficiente
    
    Ejemplos:
    - `/api/v1/filings/live?ticker=TSLA&form_types=8-K,10-K`
    - `/api/v1/filings/live?form_types=8-K&items=2.02,5.02` (earnings & management changes)
    - `/api/v1/filings/live?form_types=S-1,424B5&date_from=2024-01-01` (offerings)
    """
    # Parsear listas
    form_types_list = [ft.strip() for ft in form_types.split(',')] if form_types else None
    items_list = [item.strip() for item in items.split(',')] if items else None
    
    # Construir query Lucene
    lucene_query = build_lucene_query(
        ticker=ticker,
        form_types=form_types_list,
        items=items_list,
        date_from=date_from,
        date_to=date_to,
    )
    
    print(f"📊 SEC Query: {lucene_query}")
    
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


@app.get("/api/v1/filings/realtime", response_model=FilingsListResponse)
async def get_realtime_filings(
    count: int = QueryParam(100, ge=1, le=500, description="Number of recent filings"),
    ticker: Optional[str] = QueryParam(None, description="Filter by ticker"),
):
    """
    Obtener filings recientes del cache Redis (real-time)
    
    Estos son los filings más recientes recibidos por el Stream API.
    Ideal para mostrar actividad en tiempo real.
    
    Ejemplos:
    - `/api/v1/filings/realtime` - últimos 100 filings
    - `/api/v1/filings/realtime?ticker=TSLA&count=50` - últimos 50 de TSLA
    """
    try:
        # Acceder al Redis client global (si está configurado)
        redis_client = None
        
        # Intentar obtener Redis client del app state
        if hasattr(app.state, 'redis_client') and app.state.redis_client:
            redis_client = app.state.redis_client
        else:
            # Conectar a Redis si no está en app state
            import redis.asyncio as aioredis
            if settings.REDIS_PASSWORD:
                redis_url = f"redis://:{settings.REDIS_PASSWORD}@{settings.REDIS_HOST}:{settings.REDIS_PORT}/0"
            else:
                redis_url = f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/0"
            
            redis_client = await aioredis.from_url(redis_url, decode_responses=True)
        
        import json
        
        if ticker:
            # Obtener por ticker específico
            key = f"cache:sec:filings:ticker:{ticker.upper()}"
            results = await redis_client.zrevrange(key, 0, count - 1)
        else:
            # Obtener últimos globales
            key = "cache:sec:filings:latest"
            results = await redis_client.zrevrange(key, 0, count - 1)
        
        # Parsear JSON
        filings = []
        for result in results:
            try:
                filing_data = json.loads(result)
                # Parsear a SECFiling para normalizar
                filing = query_client.parse_filing(filing_data)
                if filing:
                    filings.append(filing.model_dump(by_alias=True))
            except (json.JSONDecodeError, Exception):
                continue
        
        return FilingsListResponse(
            filings=filings,
            total=len(filings),
            page=1,
            page_size=count,
            message=f"Found {len(filings)} real-time filings from cache"
        )
        
    except Exception as e:
        print(f"⚠️ Error fetching realtime filings: {e}")
        # Fallback: devolver lista vacía (no es crítico)
        return FilingsListResponse(
            filings=[],
            total=0,
            page=1,
            page_size=count,
            message="Real-time cache not available"
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


@app.get("/api/v1/proxy")
async def proxy_sec_filing(
    url: str = QueryParam(..., description="SEC.gov URL to proxy"),
    request: Request = None
):
    """
    Proxy para cargar filings de SEC.gov sin restricciones de CORS/X-Frame-Options
    
    Esto permite mostrar filings en iframe dentro de la app.
    Reescribe links para que pasen por el proxy.
    Soporta HTML, imágenes, PDFs y otros archivos.
    """
    import re
    from urllib.parse import urljoin, quote
    from fastapi.responses import Response
    
    # Validar que la URL sea de SEC.gov
    if not url.startswith("https://www.sec.gov/") and not url.startswith("https://sec.gov/"):
        raise HTTPException(
            status_code=400,
            detail="Only SEC.gov URLs are allowed"
        )
    
    try:
        # SEC.gov requiere User-Agent con información de contacto
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(url, headers={
                "User-Agent": "Tradeul App admin@tradeul.com",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Host": "www.sec.gov"
            })
            response.raise_for_status()
            
            content_type = response.headers.get("content-type", "")
            
            # Determine if this is HTML that needs link rewriting
            is_html = (
                "html" in content_type.lower() or 
                "xml" in content_type.lower() or
                url.endswith(".htm") or 
                url.endswith(".html")
            )
            
            # For non-HTML content (images, PDFs, etc), return as-is with original content-type
            if not is_html:
                return Response(
                    content=response.content,
                    status_code=200,
                    media_type=content_type.split(';')[0].strip(),
                    headers={
                        "Cache-Control": "public, max-age=86400",  # Cache images longer
                        "X-Content-Type-Options": "nosniff"
                    }
                )
            
            # For HTML content, rewrite links
            content = response.text
            
            # Get proxy base URL (relative to sec.tradeul.com)
            proxy_base = "/api/v1/proxy?url="
            
            # Rewrite absolute SEC.gov links
            # href="https://www.sec.gov/..." -> href="/api/v1/proxy?url=https%3A%2F%2Fwww.sec.gov%2F..."
            def rewrite_absolute(match):
                attr = match.group(1)  # href or src
                sec_url = match.group(2)
                return f'{attr}="{proxy_base}{quote(sec_url, safe="")}"'
            
            content = re.sub(
                r'(href|src)="(https?://(?:www\.)?sec\.gov[^"]*)"',
                rewrite_absolute,
                content,
                flags=re.IGNORECASE
            )
            
            # Rewrite relative links starting with /
            # href="/Archives/..." -> href="/api/v1/proxy?url=https%3A%2F%2Fwww.sec.gov%2FArchives%2F..."
            def rewrite_relative_slash(match):
                attr = match.group(1)
                path = match.group(2)
                full_url = f"https://www.sec.gov{path}"
                return f'{attr}="{proxy_base}{quote(full_url, safe="")}"'
            
            content = re.sub(
                r'(href|src)="(/[^"]*)"',
                rewrite_relative_slash,
                content,
                flags=re.IGNORECASE
            )
            
            # Get base URL for relative paths (directory of current document)
            base_url = url.rsplit('/', 1)[0] + '/'
            
            # Rewrite relative links WITHOUT leading slash (e.g., "exhibit.htm", "image.jpg")
            # These are relative to the current document's directory
            # href="file.htm" -> href="/api/v1/proxy?url=https%3A%2F%2Fwww.sec.gov%2F...%2Ffile.htm"
            def rewrite_relative_file(match):
                attr = match.group(1)
                filename = match.group(2)
                # Skip if it's a fragment, javascript, mailto, data URI, or already absolute
                if filename.startswith(('#', 'javascript:', 'mailto:', 'data:', 'http://', 'https://')):
                    return match.group(0)
                full_url = base_url + filename
                return f'{attr}="{proxy_base}{quote(full_url, safe="")}"'
            
            # Match href/src="filename" where filename doesn't start with / or http
            content = re.sub(
                r'(href|src)="([^"/:#][^"]*)"',
                rewrite_relative_file,
                content,
                flags=re.IGNORECASE
            )
            
            return HTMLResponse(
                content=content,
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

