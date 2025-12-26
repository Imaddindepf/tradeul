"""
API Gateway - Main Entry Point

Gateway principal para el frontend web:
- REST API para consultas
- WebSocket para datos en tiempo real
- Agregación de múltiples servicios
"""

import asyncio
import os
import uuid
from datetime import datetime
from typing import Optional, List
import structlog
import httpx
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Query, Request, Depends
from fastapi.responses import JSONResponse, StreamingResponse, Response, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from shared.config.settings import settings
from shared.config.fmp_endpoints import FMPEndpoints
from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import configure_logging, get_logger
from shared.models.description import (
    TickerDescription, CompanyInfo, MarketStats, ValuationMetrics,
    DividendInfo, RiskMetrics, AnalystRating, PriceTarget, FMPRatios
)
from shared.models.polygon import PolygonSingleTickerSnapshotResponse
from ws_manager import ConnectionManager
from routes.user_prefs import router as user_prefs_router, set_timescale_client
from routes.user_filters import router as user_filters_router, set_timescale_client as set_user_filters_timescale_client
from routes.financials import router as financials_router
from routes.proxy import router as proxy_router
from routes.realtime import router as realtime_router, set_redis_client as set_realtime_redis
from routers.watchlist_router import router as watchlist_router
from http_clients import http_clients, HTTPClientManager
from auth import clerk_jwt_verifier, PassiveAuthMiddleware, get_current_user, AuthenticatedUser

# Configurar logger
configure_logging(service_name="api_gateway")
logger = get_logger(__name__)

# ============================================================================
# Global State
# ============================================================================

redis_client: Optional[RedisClient] = None
timescale_client: Optional[TimescaleClient] = None
connection_manager: ConnectionManager = ConnectionManager()
stream_broadcaster_task: Optional[asyncio.Task] = None

# HTTP Clients Manager (connection pooling)
# Acceso via: http_clients.polygon, http_clients.fmp, etc.


# ============================================================================
# Lifecycle Management
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestión del ciclo de vida de la aplicación"""
    global redis_client, timescale_client, stream_broadcaster_task
    
    logger.info("api_gateway_starting")
    
    # Inicializar Redis
    redis_client = RedisClient()
    await redis_client.connect()
    
    # Inicializar TimescaleDB (requerido para preferencias de usuario y filtros)
    timescale_client = TimescaleClient()
    await timescale_client.connect()
    set_timescale_client(timescale_client)  # Para user_prefs
    set_user_filters_timescale_client(timescale_client)  # Para user_filters
    logger.info("timescale_connected")
    
    # Router de financials ahora es un microservicio separado
    # Se accede via http_clients.financials (FinancialsClient)
    logger.info("financials_microservice_ready")
    
    # Configurar router de realtime con Redis
    set_realtime_redis(redis_client)
    logger.info("realtime_router_configured")
    
    # Inicializar HTTP Clients con connection pooling
    # Esto evita crear conexiones por request - CRÍTICO para latencia
    await http_clients.initialize(
        polygon_api_key=settings.POLYGON_API_KEY,
        fmp_api_key=settings.FMP_API_KEY,
        sec_api_key=getattr(settings, 'SEC_API_IO_KEY', None),
        elevenlabs_api_key=os.getenv("ELEVEN_LABS_API_KEY"),
    )
    logger.info("http_clients_initialized_with_pooling")
    
    # Inicializar Clerk JWT Verifier (pre-carga JWKS para auth)
    if getattr(settings, 'auth_enabled', False):
        try:
            await clerk_jwt_verifier.initialize()
            logger.info("clerk_jwt_verifier_initialized")
        except Exception as e:
            logger.warning(f"clerk_jwt_init_failed error={e} - auth will be disabled")
    
    # Iniciar broadcaster de streams - DESACTIVADO: Ahora usamos servidor WebSocket dedicado
    # stream_broadcaster_task = asyncio.create_task(broadcast_streams())
    stream_broadcaster_task = None
    logger.info("WebSocket broadcaster disabled - using dedicated websocket_server")
    
    
    logger.info("api_gateway_started")
    
    yield
    
    # Shutdown
    logger.info("api_gateway_shutting_down")
    
    if stream_broadcaster_task:
        stream_broadcaster_task.cancel()
        try:
            await stream_broadcaster_task
        except asyncio.CancelledError:
            pass
    
    # Cerrar HTTP clients (liberar conexiones)
    await http_clients.close()
    
    if redis_client:
        await redis_client.disconnect()
    
    if timescale_client:
        await timescale_client.disconnect()
    
    logger.info("api_gateway_stopped")


# ============================================================================
# FastAPI App
# ============================================================================

app = FastAPI(
    title="Tradeul Scanner API",
    description="API Gateway para el scanner en tiempo real",
    version="1.0.0",
    lifespan=lifespan
)

# CORS Middleware
# Nota: allow_credentials=True requiere orígenes específicos (no "*")
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3000",
    "http://157.180.45.153:3000",
    "http://157.180.45.153:3001",
    "https://tradeul.com",
    "https://www.tradeul.com",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth Middleware (PASIVO - lee token pero NO bloquea)
# Controlado por AUTH_ENABLED env var (default: false)
app.add_middleware(
    PassiveAuthMiddleware,
    enabled=getattr(settings, 'auth_enabled', False)
)

# Registrar routers
app.include_router(user_prefs_router)
app.include_router(user_filters_router)
app.include_router(financials_router)
app.include_router(watchlist_router)
app.include_router(proxy_router)  # Incluye endpoints de dilution, SEC filings, etc.
app.include_router(realtime_router)  # Real-time ticker data for charts


# ============================================================================
# Stream Broadcaster
# ============================================================================

async def broadcast_streams():
    """
    DESACTIVADO COMPLETAMENTE: Ahora usamos servidor WebSocket dedicado (websocket_server)
    Esta función ya no se ejecuta - la línea está comentada en startup()
    """
    # Esta función nunca debe ejecutarse - está desactivada en startup()
    logger.warning("broadcast_streams() fue llamado pero está DESACTIVADO")
    return  # Return inmediatamente sin hacer nada
    
    streams_config = [
        {
            "stream": "stream:analytics:rvol",
            "group": "api_gateway_rvol",
            "consumer": "gateway_consumer_1",
            "message_type": "rvol"
        },
        {
            "stream": "stream:realtime:aggregates",
            "group": "api_gateway_agg",
            "consumer": "gateway_consumer_2",
            "message_type": "aggregate"
        }
    ]
    
    # Crear consumer groups
    for config in streams_config:
        try:
            await redis_client.create_consumer_group(
                config["stream"],
                config["group"],
                mkstream=True
            )
        except Exception as e:
            logger.debug("consumer_group_exists", stream=config["stream"])
    
    while True:
        try:
            # Leer de múltiples streams
            for config in streams_config:
                messages = await redis_client.read_stream(
                    stream_name=config["stream"],
                    consumer_group=config["group"],
                    consumer_name=config["consumer"],
                    count=50,
                    block=100  # 100ms
                )
                
                if messages:
                    # Parsear estructura: [(stream_name, [(message_id, data), ...])]
                    for stream_name, stream_messages in messages:
                        for message_id, data in stream_messages:
                            symbol = data.get('symbol') if isinstance(data, dict) else None
                            
                            if symbol:
                                # Transformar datos de Redis a formato Polygon para el frontend
                                transformed_data = {
                                    "o": float(data.get('open', 0)),
                                    "h": float(data.get('high', 0)),
                                    "l": float(data.get('low', 0)),
                                    "c": float(data.get('close', 0)),
                                    "v": int(data.get('volume', 0)),
                                    "vw": float(data.get('vwap', 0)),
                                    "av": int(data.get('volume_accumulated', 0)),
                                    "op": float(data.get('open', 0)),
                                }
                                
                                # Agregar RVOL si existe
                                if 'rvol' in data:
                                    transformed_data['rvol'] = float(data['rvol'])
                                
                                # Preparar mensaje para WebSocket
                                ws_message = {
                                    "type": config["message_type"],
                                    "symbol": symbol,
                                    "data": transformed_data,
                                    "timestamp": datetime.now().isoformat()
                                }
                                
                                # Broadcast a suscriptores
                                await connection_manager.broadcast_to_subscribers(
                                    ws_message,
                                    symbol
                                )
                            
                            # ACK mensaje
                            await redis_client.xack(
                                config["stream"],
                                config["group"],
                                message_id
                            )
            
            # Pequeña pausa para no saturar CPU
            await asyncio.sleep(0.01)
        
        except asyncio.CancelledError:
            logger.info("stream_broadcaster_cancelled")
            raise
        
        except Exception as e:
            logger.error(
                "stream_broadcaster_error",
                error=str(e),
                error_type=type(e).__name__
            )
            await asyncio.sleep(1)


# ============================================================================
# REST API Endpoints
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "api_gateway",
        "timestamp": datetime.now().isoformat(),
        "redis_connected": redis_client is not None,
        "timescale_connected": timescale_client is not None
    }


@app.get("/api/v1/auth/me")
async def get_current_user_info(user: AuthenticatedUser = Depends(get_current_user)):
    """
    Endpoint de prueba para verificar autenticación.
    Devuelve los datos del usuario autenticado.
    """
    return {
        "authenticated": True,
        "user_id": user.id,
        "email": user.email,
        "name": user.display_name,
        "is_admin": user.is_admin,
        "is_premium": user.is_premium,
        "roles": user.roles,
    }


@app.get("/api/v1/scanner/status")
async def get_scanner_status():
    """
    Obtiene el estado actual del scanner
    
    Returns:
        Estado general del sistema
    """
    try:
        # Obtener estado de Redis
        market_session = await redis_client.get("market:session:current")
        
        # Obtener count de tickers filtrados
        filtered_count = await redis_client.get("scanner:filtered:count")
        
        return {
            "status": "running",
            "market_session": market_session or "UNKNOWN",
            "filtered_tickers_count": int(filtered_count or 0),
            "websocket_connections": connection_manager.stats["active_connections"],
            "timestamp": datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error("scanner_status_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/scanner/filtered")
async def get_filtered_tickers(
    limit: int = Query(default=100, ge=1, le=1000)
):
    """
    Obtiene los tickers actualmente filtrados por el scanner
    
    Args:
        limit: Número máximo de tickers a retornar
    
    Returns:
        Lista de tickers filtrados con sus métricas
    """
    try:
        # Obtener sesión de mercado actual (usa cliente con connection pooling)
        session_data = await http_clients.market_session.get_current_session()
        current_session = session_data.get('session', 'POST_MARKET')
        
        # Leer desde cache del scanner (donde realmente se guardan los tickers)
        cache_key = f"scanner:filtered_complete:{current_session}"
        cached_data = await redis_client.get(cache_key, deserialize=True)
        
        if cached_data and isinstance(cached_data, list):
            # Limitar y retornar
            tickers = cached_data[:limit]
            return {
                "tickers": tickers,
                "count": len(tickers),
                "timestamp": datetime.now().isoformat()
            }
        
        # Fallback 1: Intentar leer último scan guardado (sin TTL)
        last_scan_key = "scanner:filtered_complete:LAST"
        last_scan_data = await redis_client.get(last_scan_key, deserialize=True)
        
        if last_scan_data and isinstance(last_scan_data, dict):
            last_tickers = last_scan_data.get("tickers", [])
            if last_tickers and isinstance(last_tickers, list):
                logger.info("using_last_scan_fallback", session=last_scan_data.get("session"), count=len(last_tickers))
                tickers = last_tickers[:limit]
                return {
                    "tickers": tickers,
                    "count": len(tickers),
                    "timestamp": last_scan_data.get("timestamp", datetime.now().isoformat()),
                    "source": "last_scan_cache"
                }
        
        # Fallback 2: Intentar leer del stream (por compatibilidad)
        messages = await redis_client.read_stream_range(
            "stream:scanner:filtered",
            count=limit
        )
        
        tickers = []
        seen = set()
        
        for message_id, data in messages:
            symbol = data.get('symbol')
            if symbol and symbol not in seen:
                tickers.append({
                    "symbol": symbol,
                    "price": float(data.get('price', 0)),
                    "change_percent": float(data.get('change_percent', 0)),
                    "volume": int(data.get('volume', 0)),
                    "rvol": float(data.get('rvol', 0)),
                    "market_cap": float(data.get('market_cap', 0)),
                    "timestamp": data.get('timestamp')
                })
                seen.add(symbol)
        
        return {
            "tickers": tickers,
            "count": len(tickers),
            "timestamp": datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error("filtered_tickers_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/ticker/{symbol}")
async def get_ticker_details(symbol: str):
    """
    Obtiene información detallada de un ticker
    
    Args:
        symbol: Símbolo del ticker (ej: AAPL)
    
    Returns:
        Información completa del ticker
    """
    try:
        symbol = symbol.upper()
        
        # Obtener datos de Redis (caché)
        cached_data = await redis_client.get(f"ticker:data:{symbol}")
        
        if cached_data:
            return JSONResponse(content=eval(cached_data))
        
        # Si no está en caché, obtener de TimescaleDB
        query = """
            SELECT 
                symbol,
                price,
                change_percent,
                volume,
                market_cap,
                float_shares,
                avg_volume_30d,
                timestamp
            FROM ticker_metadata
            WHERE symbol = $1
            ORDER BY timestamp DESC
            LIMIT 1
        """
        
        result = await timescale_client.fetchrow(query, symbol)
        
        if not result:
            raise HTTPException(status_code=404, detail=f"Ticker {symbol} not found")
        
        ticker_data = dict(result)
        
        # Guardar en caché (5 segundos)
        await redis_client.setex(
            f"ticker:data:{symbol}",
            5,
            str(ticker_data)
        )
        
        return ticker_data
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("ticker_details_error", symbol=symbol, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/metadata/search")
async def search_tickers(
    q: str = Query(..., description="Search query", min_length=1),
    limit: int = Query(10, ge=1, le=50, description="Max results")
):
    """
    Proxy para búsqueda de tickers (ticker-metadata-service)
    
    Args:
        q: Query string (symbol o company name)
        limit: Máximo de resultados
    
    Returns:
        Lista de tickers que coinciden con la búsqueda
    """
    try:
        # Usa cliente con connection pooling para baja latencia
        return await http_clients.ticker_metadata.search(q, limit)
    
    except httpx.TimeoutException:
        logger.error("metadata_search_timeout", query=q)
        raise HTTPException(status_code=504, detail="Search timeout")
    except httpx.ConnectError:
        logger.error("metadata_search_unavailable", query=q)
        raise HTTPException(status_code=503, detail="Metadata service unavailable")
    except httpx.HTTPStatusError as e:
        logger.error("metadata_search_error", query=q, status=e.response.status_code)
        raise HTTPException(status_code=e.response.status_code, detail=f"Search failed")
    except Exception as e:
        logger.error("metadata_search_error", query=q, error=str(e))
        raise HTTPException(status_code=500, detail=f"Search error: {str(e)}")


@app.get("/api/v1/ticker/{symbol}/metadata")
async def get_ticker_metadata(symbol: str):
    """
    Obtiene los metadatos completos de la compañía (sector, industria, exchange, etc.)
    
    Args:
        symbol: Símbolo del ticker (ej: AAPL)
    
    Returns:
        Metadatos completos de la compañía
    """
    try:
        symbol = symbol.upper()
        
        # Intentar obtener de ticker-metadata-service (usa connection pooling)
        try:
            metadata = await http_clients.ticker_metadata.get_metadata(symbol)
            if metadata:
                logger.info("metadata_service_success", symbol=symbol)
                return metadata
            else:
                logger.info("metadata_service_404_using_fallback", symbol=symbol)
        except httpx.TimeoutException:
            logger.warning("metadata_service_timeout", symbol=symbol)
        except httpx.ConnectError:
            logger.warning("metadata_service_unavailable", symbol=symbol)
        except Exception as e:
            logger.warning("metadata_service_error", symbol=symbol, error=str(e))
        
        # Fallback: Query directo a DB (modo degradado)
        logger.info("using_fallback_db_query", symbol=symbol)
        
        query = """
            SELECT 
                symbol, company_name, exchange, sector, industry,
                market_cap, float_shares, shares_outstanding,
                avg_volume_30d, avg_volume_10d, avg_price_30d, beta,
                description, homepage_url, phone_number, address,
                total_employees, list_date,
                logo_url, icon_url,
                cik, composite_figi, share_class_figi, ticker_root, ticker_suffix,
                type, currency_name, locale, market, round_lot, delisted_utc,
                is_etf, is_actively_trading, updated_at
            FROM ticker_metadata
            WHERE symbol = $1
        """
        
        result = await timescale_client.fetchrow(query, symbol)
        
        if not result:
            raise HTTPException(status_code=404, detail=f"Metadata for {symbol} not found")
        
        metadata = dict(result)
        
        # Convertir datetime a string para JSON
        if metadata.get('updated_at'):
            metadata['updated_at'] = metadata['updated_at'].isoformat()
        
        return metadata
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("ticker_metadata_error", symbol=symbol, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/proxy/logo")
async def proxy_logo(url: str):
    """
    Proxy para logos de Polygon.io con API key
    
    Args:
        url: URL del logo sin API key
    
    Returns:
        StreamingResponse con la imagen
    """
    try:
        # Usar cliente Polygon para proxy de logo
        response = await http_clients.polygon.proxy_logo(url)
        
        if response.status_code != 200:
            raise HTTPException(status_code=404, detail="Logo not found")
        
        # Devolver la imagen como stream
        return StreamingResponse(
            iter([response.content]),
            media_type=response.headers.get("content-type", "image/svg+xml"),
            headers={
                "Cache-Control": "public, max-age=86400",  # Cache 24h
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("logo_proxy_error", url=url, error=str(e))
        raise HTTPException(status_code=500, detail="Error fetching logo")


# ============================================================================
# Ticker Description Endpoint
# ============================================================================

@app.get("/api/v1/ticker/{symbol}/description")
async def get_ticker_description(
    symbol: str,
    force_refresh: bool = Query(default=False, description="Force refresh from API")
):
    """
    Get comprehensive ticker description combining:
    - Company info (metadata)
    - Market stats (profile)
    - Valuation ratios
    - Dividend info
    - Analyst ratings & price targets
    
    Caches for 5 minutes.
    """
    global redis_client
    
    symbol = symbol.upper()
    cache_key = f"description:{symbol}"
    cache_ttl = 300  # 5 minutes
    
    try:
        # Check cache first
        if not force_refresh and redis_client:
            cached = await redis_client.get(cache_key)
            if cached:
                logger.debug("description_cache_hit", symbol=symbol)
                return cached
        
        # Usar clientes HTTP con connection pooling
        # 1. Get metadata from Redis (already cached)
        metadata = None
        if redis_client:
            metadata = await redis_client.get(f"metadata:ticker:{symbol}")
        
        # 2. Fetch FMP profile (for price, beta, CEO, etc)
        profile_list = await http_clients.fmp.get_profile(symbol)
        profile_data = profile_list[0] if profile_list else {}
        
        # 3. Fetch FMP ratios
        ratios_list = await http_clients.fmp.get_ratios(symbol, limit=1)
        ratios_data = ratios_list[0] if ratios_list else {}
        
        # 4. Fetch analyst recommendations
        analyst_list = await http_clients.fmp.get_analyst_recommendations(symbol)
        analyst_data = analyst_list[0] if analyst_list else {}
        
        # 5. Fetch price targets (limit 10)
        targets_list = await http_clients.fmp.get_price_targets(symbol)
        targets_data = targets_list[:10] if targets_list else []
        
        # 6. Detect SPAC status (async, cached for company lifecycle)
        spac_info = {"is_spac": False, "sic_code": None}
        try:
            if http_clients.sec_edgar:
                spac_result = await http_clients.sec_edgar.detect_spac(
                    symbol, 
                    http_clients.sec_api if hasattr(http_clients, 'sec_api') else None
                )
                spac_info = {
                    "is_spac": spac_result.get("is_spac", False),
                    "sic_code": spac_result.get("sic_code")
                }
                if spac_info["is_spac"]:
                    logger.info("spac_detected", symbol=symbol, confidence=spac_result.get("confidence"))
        except Exception as e:
            logger.debug("spac_detection_skipped", symbol=symbol, error=str(e))
        
        # Build company info
        company = CompanyInfo(
            symbol=symbol,
            name=profile_data.get("companyName") or (metadata.get("company_name") if metadata else symbol),
            exchange=profile_data.get("exchange") or (metadata.get("exchange") if metadata else None),
            exchangeFullName=profile_data.get("exchangeFullName"),
            sector=profile_data.get("sector") or (metadata.get("sector") if metadata else None),
            industry=profile_data.get("industry") or (metadata.get("industry") if metadata else None),
            is_spac=spac_info.get("is_spac"),
            sic_code=spac_info.get("sic_code"),
            description=profile_data.get("description") or (metadata.get("description") if metadata else None),
            ceo=profile_data.get("ceo"),
            website=profile_data.get("website") or (metadata.get("homepage_url") if metadata else None),
            address=profile_data.get("address"),
            city=profile_data.get("city"),
            state=profile_data.get("state"),
            country=profile_data.get("country"),
            phone=profile_data.get("phone") or (metadata.get("phone_number") if metadata else None),
            employees=int(profile_data.get("fullTimeEmployees") or 0) if profile_data.get("fullTimeEmployees") else (metadata.get("total_employees") if metadata else None),
            ipoDate=profile_data.get("ipoDate") or (metadata.get("list_date") if metadata else None),
            logoUrl=profile_data.get("image") or (metadata.get("logo_url") if metadata else None),
            iconUrl=metadata.get("icon_url") if metadata else None,
        )
        
        # Build market stats
        stats = MarketStats(
            price=profile_data.get("price"),
            change=profile_data.get("change"),
            changePercent=profile_data.get("changePercentage"),
            volume=profile_data.get("volume"),
            avgVolume=profile_data.get("averageVolume") or (metadata.get("avg_volume_30d") if metadata else None),
            marketCap=profile_data.get("marketCap") or (metadata.get("market_cap") if metadata else None),
            sharesOutstanding=metadata.get("shares_outstanding") if metadata else None,
            floatShares=metadata.get("float_shares") if metadata else None,
            dayLow=None,  # Not in stable/profile
            dayHigh=None,
            yearLow=float(profile_data.get("range", "0-0").split("-")[0]) if profile_data.get("range") else None,
            yearHigh=float(profile_data.get("range", "0-0").split("-")[1]) if profile_data.get("range") else None,
            range52Week=profile_data.get("range"),
            beta=profile_data.get("beta"),
        )
        
        # Build valuation metrics
        valuation = ValuationMetrics(
            peRatio=ratios_data.get("priceToEarningsRatio"),
            forwardPE=None,  # Need separate endpoint
            pegRatio=ratios_data.get("priceToEarningsGrowthRatio"),
            pbRatio=ratios_data.get("priceToBookRatio"),
            psRatio=ratios_data.get("priceToSalesRatio"),
            evToEbitda=ratios_data.get("enterpriseValueMultiple"),
            evToRevenue=None,
            enterpriseValue=None,
        )
        
        # Build dividend info
        dividend = DividendInfo(
            trailingYield=ratios_data.get("dividendYieldPercentage"),
            forwardYield=None,
            payoutRatio=ratios_data.get("dividendPayoutRatio"),
            dividendPerShare=ratios_data.get("dividendPerShare") or profile_data.get("lastDividend"),
            exDividendDate=None,
            dividendDate=None,
            fiveYearAvgYield=None,
        )
        
        # Build risk metrics
        risk = RiskMetrics(
            beta=profile_data.get("beta"),
            shortInterest=None,  # Need separate endpoint
            shortRatio=None,
            shortPercentFloat=None,
        )
        
        # Build analyst rating
        analyst_rating = None
        if analyst_data:
            analyst_rating = AnalystRating(
                symbol=symbol,
                date=analyst_data.get("date"),
                analystRatingsbuy=analyst_data.get("analystRatingsbuy"),
                analystRatingsHold=analyst_data.get("analystRatingsHold"),
                analystRatingsSell=analyst_data.get("analystRatingsSell"),
                analystRatingsStrongSell=analyst_data.get("analystRatingsStrongSell"),
                analystRatingsStrongBuy=analyst_data.get("analystRatingsStrongBuy"),
            )
        
        # Build price targets
        price_targets = [
            PriceTarget(
                symbol=symbol,
                publishedDate=t.get("publishedDate"),
                analystName=t.get("analystName"),
                analystCompany=t.get("analystCompany"),
                priceTarget=t.get("priceTarget"),
                adjPriceTarget=t.get("adjPriceTarget"),
                priceWhenPosted=t.get("priceWhenPosted"),
                newsTitle=t.get("newsTitle"),
                newsURL=t.get("newsURL"),
                newsPublisher=t.get("newsPublisher"),
            )
            for t in targets_data
        ]
        
        # Calculate consensus target
        consensus_target = None
        target_upside = None
        if price_targets:
            valid_targets = [t.priceTarget for t in price_targets if t.priceTarget]
            if valid_targets:
                consensus_target = sum(valid_targets) / len(valid_targets)
                if stats.price and consensus_target:
                    target_upside = ((consensus_target - stats.price) / stats.price) * 100
        
        # Build complete description
        description = TickerDescription(
            symbol=symbol,
            company=company,
            stats=stats,
            valuation=valuation,
            dividend=dividend,
            risk=risk,
            analystRating=analyst_rating,
            priceTargets=price_targets,
            consensusTarget=round(consensus_target, 2) if consensus_target else None,
            targetUpside=round(target_upside, 2) if target_upside else None,
        )
        
        result = description.model_dump()
        
        # Cache result
        if redis_client:
            await redis_client.set(cache_key, result, ttl=cache_ttl)
            logger.info("description_cached", symbol=symbol)
        
        return result
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("description_error", symbol=symbol, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/ticker/{symbol}/snapshot", response_model=PolygonSingleTickerSnapshotResponse)
async def get_ticker_snapshot(
    symbol: str,
    force_refresh: bool = Query(default=False, description="Force refresh from API")
):
    """
    Get the most recent market data snapshot for a single ticker from Polygon.
    
    This endpoint consolidates the latest trade, quote, and aggregated data
    (minute, day, and previous day) for the specified ticker.
    
    Snapshot data is cleared at 3:30 AM EST and begins updating as exchanges
    report new information, which can start as early as 4:00 AM EST.
    
    Use Cases: 
    - Fallback when WebSocket quotes are not available
    - Focused monitoring, real-time analysis, price alerts
    
    Caches for 5 minutes (300 seconds) to reduce API calls.
    """
    global redis_client
    symbol = symbol.upper()
    cache_key = f"ticker_snapshot:{symbol}"
    cache_ttl = 300  # 5 minutes
    
    try:
        if not force_refresh and redis_client:
            cached_data = await redis_client.get(cache_key)
            if cached_data:
                logger.debug("ticker_snapshot_cache_hit", symbol=symbol)
                return cached_data
        
        # Usar cliente Polygon con connection pooling
        data = await http_clients.polygon.get_snapshot(symbol)
        
        # Validate response structure
        if data.get("status") != "OK":
            raise HTTPException(
                status_code=404, 
                detail=f"Snapshot not available for {symbol}: {data.get('status')}"
            )
        
        # Parse response with Pydantic model
        snapshot_response = PolygonSingleTickerSnapshotResponse(**data)
        
        # Cache the response
        if redis_client:
            await redis_client.set(cache_key, snapshot_response.model_dump(), ttl=cache_ttl)
            logger.info("ticker_snapshot_cached", symbol=symbol)
        
        return snapshot_response
            
    except httpx.HTTPStatusError as e:
        logger.error("ticker_snapshot_http_error", symbol=symbol, error=str(e), status_code=e.response.status_code)
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Snapshot not found for {symbol}")
        raise HTTPException(status_code=e.response.status_code, detail=f"API error: {e.response.text}")
    except Exception as e:
        logger.error("ticker_snapshot_fetch_error", symbol=symbol, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to fetch snapshot: {str(e)}")


@app.get("/api/v1/ticker/{symbol}/prev-close")
async def get_ticker_prev_close(
    symbol: str,
    user: AuthenticatedUser = Depends(get_current_user)  # 🔒 Requiere auth
):
    """
    Get previous day's close price for a ticker (lightweight endpoint).
    
    Returns only the prev_close value from the snapshot, useful for calculating
    change percentages without fetching the full snapshot.
    """
    global redis_client
    symbol = symbol.upper()
    cache_key = f"ticker_prev_close:{symbol}"
    cache_ttl = 3600  # 1 hora (prev_close no cambia durante el día)
    
    try:
        # Check cache first
        if redis_client:
            cached = await redis_client.get(cache_key)
            if cached:
                return {"symbol": symbol, "close": float(cached), "c": float(cached), "cached": True}
        
        # Fetch snapshot (usa cache interno del snapshot endpoint)
        snapshot_data = await http_clients.polygon.get_snapshot(symbol)
        
        if snapshot_data.get("status") != "OK":
            raise HTTPException(status_code=404, detail=f"Ticker {symbol} not found")
        
        # Extract prevDay close
        ticker_data = snapshot_data.get("ticker", {})
        prev_day = ticker_data.get("prevDay", {})
        prev_close = prev_day.get("c")  # Close price
        
        if prev_close is None:
            raise HTTPException(status_code=404, detail=f"Previous close not available for {symbol}")
        
        # Cache the result
        if redis_client:
            await redis_client.set(cache_key, str(prev_close), ttl=cache_ttl)
        
        return {
            "symbol": symbol,
            "close": prev_close,
            "c": prev_close,
            "cached": False
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching prev_close for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/rvol/{symbol}")
async def get_ticker_rvol(symbol: str):
    """
    Obtiene el RVOL actual de un ticker
    
    Args:
        symbol: Símbolo del ticker
    
    Returns:
        RVOL del ticker con información del slot
    """
    try:
        symbol = symbol.upper()
        
        # Obtener RVOL del Analytics Service
        # (podríamos hacer una llamada HTTP o leer de Redis)
        rvol_data = await redis_client.get(f"rvol:{symbol}")
        
        if not rvol_data:
            raise HTTPException(status_code=404, detail=f"RVOL data not available for {symbol}")
        
        return JSONResponse(content=eval(rvol_data))
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("rvol_error", symbol=symbol, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/history/scans")
async def get_scan_history(
    date: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=1000)
):
    """
    Obtiene histórico de scans para backtesting
    
    Args:
        date: Fecha en formato YYYY-MM-DD (opcional)
        limit: Número máximo de resultados
    
    Returns:
        Histórico de scans
    """
    try:
        if date:
            query = """
                SELECT 
                    scan_id,
                    symbol,
                    price,
                    volume,
                    rvol,
                    change_percent,
                    market_cap,
                    scan_timestamp
                FROM scan_results
                WHERE DATE(scan_timestamp) = $1
                ORDER BY scan_timestamp DESC
                LIMIT $2
            """
            results = await timescale_client.fetch(query, date, limit)
        else:
            query = """
                SELECT 
                    scan_id,
                    symbol,
                    price,
                    volume,
                    rvol,
                    change_percent,
                    market_cap,
                    scan_timestamp
                FROM scan_results
                ORDER BY scan_timestamp DESC
                LIMIT $1
            """
            results = await timescale_client.fetch(query, limit)
        
        scans = [dict(row) for row in results]
        
        return {
            "scans": scans,
            "count": len(scans),
            "timestamp": datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error("scan_history_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/stats")
async def get_system_stats():
    """Obtiene estadísticas del sistema completo"""
    try:
        stats = {
            "api_gateway": {
                "websocket_connections": connection_manager.stats["active_connections"],
                "messages_sent": connection_manager.stats["messages_sent"],
                "errors": connection_manager.stats["errors"]
            },
            "timestamp": datetime.now().isoformat()
        }
        
        return stats
    
    except Exception as e:
        logger.error("system_stats_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Benzinga News Proxy
# ============================================================================

@app.get("/news/api/v1/news")
async def proxy_news(
    ticker: Optional[str] = Query(None, description="Filter by ticker symbol"),
    channels: Optional[str] = Query(None, description="Filter by channels"),
    tags: Optional[str] = Query(None, description="Filter by tags"),
    author: Optional[str] = Query(None, description="Filter by author"),
    limit: int = Query(50, ge=1, le=2000, description="Limit results")
):
    """
    Proxy para el servicio de News (Benzinga y futuras fuentes)
    """
    try:
        # Usar cliente con connection pooling
        return await http_clients.benzinga_news.get_news(
            ticker=ticker,
            channels=channels,
            tags=tags,
            author=author,
            limit=limit
        )
    
    except httpx.TimeoutException:
        logger.error("news_service_timeout")
        raise HTTPException(status_code=504, detail="News service timeout")
    except httpx.ConnectError:
        logger.error("news_service_unavailable")
        raise HTTPException(status_code=503, detail="News service unavailable")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="Benzinga news service error")
    except Exception as e:
        logger.error("news_service_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/news/api/v1/news/latest")
async def proxy_news_latest(limit: int = Query(50, ge=1, le=200)):
    """Proxy para las últimas noticias"""
    try:
        # Usar cliente con connection pooling
        return await http_clients.benzinga_news.get_latest(limit)
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Service timeout")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Service unavailable")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="Service error")
    except Exception as e:
        logger.error("benzinga_latest_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/news/api/v1/news/ticker/{ticker}")
async def proxy_news_by_ticker(ticker: str, limit: int = Query(50, ge=1, le=200)):
    """Proxy para noticias por ticker"""
    try:
        # Usar cliente con connection pooling
        return await http_clients.benzinga_news.get_by_ticker(ticker, limit)
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Service timeout")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Service unavailable")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="Service error")
    except Exception as e:
        logger.error("news_ticker_error", error=str(e), ticker=ticker)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/proxy/news")
async def proxy_news_article(url: str = Query(..., description="News article URL to proxy")):
    """
    Proxy para cargar artículos de noticias sin restricciones de CORS/X-Frame-Options
    
    Esto permite mostrar artículos en iframe dentro de la app.
    Similar al sistema de SEC filings.
    """
    # Validar dominios permitidos
    allowed_domains = [
        "benzinga.com",
        "www.benzinga.com",
        "seekingalpha.com",
        "www.seekingalpha.com",
        "reuters.com",
        "www.reuters.com",
        "bloomberg.com",
        "www.bloomberg.com",
        "marketwatch.com",
        "www.marketwatch.com",
        "cnbc.com",
        "www.cnbc.com",
        "yahoo.com",
        "finance.yahoo.com",
    ]
    
    from urllib.parse import urlparse
    parsed = urlparse(url)
    
    if not any(parsed.netloc.endswith(domain) for domain in allowed_domains):
        raise HTTPException(
            status_code=400,
            detail=f"Domain not allowed: {parsed.netloc}. Only approved news domains are permitted."
        )
    
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
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
        logger.error("news_proxy_http_error", url=url, error=str(e))
        raise HTTPException(
            status_code=502,
            detail=f"Error fetching news article: {str(e)}"
        )
    except Exception as e:
        logger.error("news_proxy_error", url=url, error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Proxy error: {str(e)}"
        )


# ============================================================================
# Pattern Matching Proxy
# ============================================================================

PATTERN_MATCHING_URL = "http://pattern_matching:8025"

@app.get("/patterns/health")
async def proxy_patterns_health():
    """Proxy para health check del servicio Pattern Matching"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{PATTERN_MATCHING_URL}/health")
            return response.json()
    except Exception as e:
        logger.error("patterns_proxy_error", error=str(e))
        raise HTTPException(status_code=502, detail="Pattern Matching service unavailable")

@app.get("/patterns/api/index/stats")
async def proxy_patterns_index_stats():
    """Proxy para stats del índice FAISS"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{PATTERN_MATCHING_URL}/api/index/stats")
            return response.json()
    except Exception as e:
        logger.error("patterns_proxy_error", error=str(e))
        raise HTTPException(status_code=502, detail="Pattern Matching service unavailable")

@app.get("/patterns/api/search/{symbol}")
async def proxy_patterns_search(
    symbol: str,
    k: int = Query(30, ge=1, le=200),
    cross_asset: bool = Query(True)
):
    """Proxy para búsqueda de patrones similares"""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{PATTERN_MATCHING_URL}/api/search/{symbol}",
                params={"k": k, "cross_asset": cross_asset}
            )
            return response.json()
    except Exception as e:
        logger.error("patterns_search_error", symbol=symbol, error=str(e))
        raise HTTPException(status_code=502, detail="Pattern search failed")


@app.post("/patterns/api/search/historical")
async def proxy_patterns_search_historical(request: Request):
    """Proxy para búsqueda histórica de patrones - funciona sin mercado abierto"""
    try:
        body = await request.json()
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{PATTERN_MATCHING_URL}/api/search/historical",
                json=body
            )
            return response.json()
    except Exception as e:
        logger.error("patterns_historical_search_error", error=str(e))
        raise HTTPException(status_code=502, detail="Historical pattern search failed")


@app.get("/patterns/api/historical/prices/{symbol}")
async def proxy_patterns_historical_prices(
    symbol: str,
    date: str = Query(...),
    start_time: str = Query("09:30"),
    end_time: str = Query("16:00")
):
    """Proxy para obtener precios históricos de flat files"""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{PATTERN_MATCHING_URL}/api/historical/prices/{symbol}",
                params={"date": date, "start_time": start_time, "end_time": end_time}
            )
            return response.json()
    except Exception as e:
        logger.error("patterns_historical_prices_error", symbol=symbol, error=str(e))
        raise HTTPException(status_code=502, detail="Failed to fetch historical prices")


@app.get("/patterns/api/available-dates")
async def proxy_patterns_available_dates():
    """Proxy para obtener fechas disponibles en los flat files"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{PATTERN_MATCHING_URL}/api/available-dates")
            return response.json()
    except Exception as e:
        logger.error("patterns_available_dates_error", error=str(e))
        raise HTTPException(status_code=502, detail="Failed to fetch available dates")


# ============================================================================
# IPO Endpoints (Initial Public Offerings)
# ============================================================================

IPOS_CACHE_KEY = "cache:ipos:all"
IPOS_CACHE_TTL = 86400  # 24 hours

@app.get("/api/v1/ipos")
async def get_ipos(
    ipo_status: Optional[str] = Query(None, description="Filter by status: pending, new, history, rumor, withdrawn, direct_listing_process"),
    limit: int = Query(100, ge=1, le=1000, description="Limit results (max 1000)"),
    force_refresh: bool = Query(False, description="Force refresh from API")
):
    """
    Get IPO (Initial Public Offerings) data from Polygon.io
    
    - Data is cached for 24 hours in Redis
    - Includes pending, new, historical, rumors, and withdrawn IPOs
    - Use force_refresh=true to bypass cache
    """
    global redis_client
    
    try:
        # Try cache first (unless force refresh)
        if not force_refresh and redis_client:
            cached = await redis_client.get(IPOS_CACHE_KEY)
            if cached:
                # redis_client.get() ya deserializa automáticamente
                results = cached.get("results", [])
                
                # Apply status filter if provided
                if ipo_status:
                    results = [r for r in results if r.get("ipo_status") == ipo_status]
                
                # Apply limit
                results = results[:limit]
                
                logger.info("ipos_cache_hit", count=len(results))
                return {
                    "status": "OK",
                    "count": len(results),
                    "results": results,
                    "cached": True,
                    "cache_ttl_hours": 24
                }
        
        # Fetch from Polygon API usando cliente con connection pooling
        all_results = []
        
        # First request
        data = await http_clients.polygon.get_ipos(limit=1000)
        
        if data.get("results"):
            all_results.extend(data["results"])
        
        next_url = data.get("next_url")
        
        # Paginate to get more results (up to 3 pages = 3000 IPOs)
        page_count = 1
        while next_url and page_count < 3:
            data = await http_clients.polygon.get_ipos_page(next_url)
            
            if data.get("results"):
                all_results.extend(data["results"])
            
            next_url = data.get("next_url")
            page_count += 1
        
        # Cache the full results (redis_client serializa automáticamente)
        if redis_client and all_results:
            cache_data = {
                "results": all_results,
                "fetched_at": datetime.now().isoformat(),
                "total_count": len(all_results)
            }
            await redis_client.set(IPOS_CACHE_KEY, cache_data, ttl=IPOS_CACHE_TTL)
            logger.info("ipos_cached", count=len(all_results))
        
        # Apply filters for response
        results = all_results
        if ipo_status:
            results = [r for r in results if r.get("ipo_status") == ipo_status]
        
        results = results[:limit]
        
        return {
            "status": "OK",
            "count": len(results),
            "results": results,
            "cached": False,
            "total_available": len(all_results)
        }
        
    except httpx.HTTPError as e:
        logger.error("ipos_http_error", error=str(e))
        raise HTTPException(status_code=502, detail=f"Polygon API error: {str(e)}")
    except Exception as e:
        logger.error("ipos_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/ipos/stats")
async def get_ipos_stats():
    """Get IPO statistics by status"""
    global redis_client
    
    try:
        # Get cached data (redis_client.get() deserializa automáticamente)
        if redis_client:
            cached = await redis_client.get(IPOS_CACHE_KEY)
            if cached:
                results = cached.get("results", [])
                
                # Count by status
                stats = {}
                for ipo in results:
                    status = ipo.get("ipo_status", "unknown")
                    stats[status] = stats.get(status, 0) + 1
                
                return {
                    "status": "OK",
                    "total": len(results),
                    "by_status": stats,
                    "fetched_at": cached.get("fetched_at")
                }
        
        return {"status": "OK", "total": 0, "by_status": {}, "message": "No cached data, call /api/v1/ipos first"}
        
    except Exception as e:
        logger.error("ipos_stats_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# IPO Prospectus Endpoint (S-1, 424B4) - SEC-API.io con datos estructurados
# ============================================================================

IPO_PROSPECTUS_CACHE_TTL = 604800  # 7 días (los prospectos no cambian)
SEC_API_S1_424B4_URL = "https://api.sec-api.io/form-s1-424b4"

@app.get("/api/v1/ipos/{ticker}/prospectus")
async def get_ipo_prospectus(
    ticker: str,
    ipo_status: Optional[str] = Query(None, description="IPO status: pending, new, history - affects which forms to search"),
    issuer_name: Optional[str] = Query(None, description="Company name for searching when ticker not found"),
    force_refresh: bool = Query(False, description="Force refresh from API")
):
    """
    Get IPO prospectus data (S-1, 424B4) with structured data extraction.
    
    Uses SEC-API.io to get:
    - Public offering price (per share and total)
    - Underwriters (lead and co-managers)
    - Securities being offered
    - Management team
    - Employee counts
    - Law firms and auditors
    
    Depending on IPO status:
    - pending/rumor: Search for S-1 (registration statement)
    - new/history: Search for 424B4 (final prospectus) or S-1
    
    Results are cached for 7 days.
    """
    global redis_client
    ticker = ticker.upper()
    cache_key = f"cache:ipo_prospectus:{ticker}:{ipo_status or 'all'}"
    
    try:
        # Try cache first
        if not force_refresh and redis_client:
            cached = await redis_client.get(cache_key)
            if cached:
                logger.info("ipo_prospectus_cache_hit", ticker=ticker)
                return {
                    "status": "OK",
                    "ticker": ticker,
                    **cached,
                    "cached": True
                }
        
        # Check if SEC API key is available
        sec_api_key = settings.SEC_API_IO_KEY
        if not sec_api_key:
            logger.warning("sec_api_key_not_configured")
            raise HTTPException(status_code=503, detail="SEC API not configured")
        
        # Determine which form types to search based on IPO status
        form_filter = '(formType:"S-1" OR formType:"S-1/A" OR formType:"424B4")'
        if ipo_status in ["pending", "rumor"]:
            form_filter = '(formType:"S-1" OR formType:"S-1/A")'
        elif ipo_status in ["new", "history"]:
            form_filter = '(formType:"424B4" OR formType:"S-1" OR formType:"S-1/A")'
        
        filings = []
        search_method = "ticker"
        
        # Usar cliente SEC-API con connection pooling
        if not http_clients.sec_api:
            raise HTTPException(status_code=503, detail="SEC API client not initialized")
        
        # First try: search by ticker
        query = f'ticker:{ticker} AND {form_filter}'
        data = await http_clients.sec_api.search_s1_424b4(query, size=10)
        filings = data.get("data", [])
        
        # Second try: if no results and issuer_name provided, search by company name
        if not filings and issuer_name:
            # Clean issuer name for search (remove special chars, take first meaningful words)
            clean_name = issuer_name.replace(",", "").replace(".", "").replace("Inc", "").replace("Ltd", "").replace("Corp", "").strip()
            # Take first 3-4 words to avoid too specific search
            name_parts = clean_name.split()[:4]
            search_name = " ".join(name_parts)
            
            if search_name:
                query = f'entityName:"{search_name}" AND {form_filter}'
                logger.info("ipo_prospectus_fallback_search", ticker=ticker, search_name=search_name)
                
                data = await http_clients.sec_api.search_s1_424b4(query, size=10)
                filings = data.get("data", [])
                search_method = "entity_name"
        
        if not filings:
            # For pending IPOs, this is expected - S-1 might not be filed yet
            message = "No SEC filings found yet"
            if ipo_status in ["pending", "rumor"]:
                message = "S-1 Registration Statement not yet filed with SEC. This is normal for pending IPOs - the S-1 is typically filed a few weeks before the expected listing date."
            
            return {
                "status": "OK",
                "ticker": ticker,
                "filings": [],
                "structured_data": None,
                "cached": False,
                "ipo_status": ipo_status,
                "message": message,
                "suggestion": f"Check back closer to the IPO date, or search SEC EDGAR directly: https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company={issuer_name or ticker}&type=S-1"
            }
        
        # Process the first (most recent) filing as the main prospectus
        main_filing = filings[0]
        
        # Build structured response
        structured_data = {
            "form_type": main_filing.get("formType"),
            "filed_at": main_filing.get("filedAt"),
            "accession_no": main_filing.get("accessionNo"),
            "cik": main_filing.get("cik"),
            "entity_name": main_filing.get("entityName"),
            "filing_url": main_filing.get("filingUrl"),
            
            # Securities info
            "tickers": main_filing.get("tickers", []),
            "securities": main_filing.get("securities", []),
            
            # Pricing info (available in 424B4, sometimes in S-1)
            "public_offering_price": main_filing.get("publicOfferingPrice"),
            "underwriting_discount": main_filing.get("underwritingDiscount"),
            "proceeds_before_expenses": main_filing.get("proceedsBeforeExpenses"),
            
            # Parties involved
            "underwriters": main_filing.get("underwriters", []),
            "law_firms": main_filing.get("lawFirms", []),
            "auditors": main_filing.get("auditors", []),
            
            # Company info
            "management": main_filing.get("management", []),
            "employees": main_filing.get("employees"),
        }
        
        # Build simplified filings list for all found filings
        filings_list = []
        for f in filings:
            filings_list.append({
                "form_type": f.get("formType"),
                "filed_at": f.get("filedAt"),
                "accession_no": f.get("accessionNo"),
                "entity_name": f.get("entityName"),
                "filing_url": f.get("filingUrl"),
                "has_pricing": f.get("publicOfferingPrice") is not None,
                "underwriters_count": len(f.get("underwriters", [])),
            })
        
        result = {
            "filings": filings_list,
            "structured_data": structured_data,
            "fetched_at": datetime.now().isoformat(),
            "total_found": data.get("total", {}).get("value", len(filings))
        }
        
        # Cache the results
        if redis_client:
            await redis_client.set(cache_key, result, ttl=IPO_PROSPECTUS_CACHE_TTL)
            logger.info("ipo_prospectus_cached", ticker=ticker, count=len(filings))
        
        return {
            "status": "OK",
            "ticker": ticker,
            **result,
            "cached": False
        }
        
    except httpx.HTTPError as e:
        logger.error("ipo_prospectus_http_error", ticker=ticker, error=str(e))
        raise HTTPException(status_code=502, detail=f"SEC API error: {str(e)}")
    except Exception as e:
        logger.error("ipo_prospectus_error", ticker=ticker, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Chart Data Endpoint - TradingView Style (Lazy Loading)
# ============================================================================
# 
# Estrategia: Carga rápida inicial + lazy loading al hacer scroll
# - Primera carga: ~500 barras más recientes (rápido, <1s)
# - Scroll hacia atrás: pide más datos con parámetro "before"
# - Intraday: Polygon API (histórico desde 2015+)
# - Daily: FMP API (10+ años)
#

CHART_INTERVALS = {
    "1min": {"polygon_timespan": "minute", "polygon_multiplier": 1, "cache_ttl": 30, "bars_per_page": 500},   # 30s cache - datos muy frescos
    "5min": {"polygon_timespan": "minute", "polygon_multiplier": 5, "cache_ttl": 120, "bars_per_page": 500},  # 2 min cache
    "15min": {"polygon_timespan": "minute", "polygon_multiplier": 15, "cache_ttl": 300, "bars_per_page": 500}, # 5 min cache
    "30min": {"polygon_timespan": "minute", "polygon_multiplier": 30, "cache_ttl": 600, "bars_per_page": 500}, # 10 min cache
    "1hour": {"polygon_timespan": "hour", "polygon_multiplier": 1, "cache_ttl": 1800, "bars_per_page": 500},   # 30 min cache
    "4hour": {"polygon_timespan": "hour", "polygon_multiplier": 4, "cache_ttl": 3600, "bars_per_page": 500},   # 1h cache
    "1day": {"source": "fmp", "cache_ttl": 86400, "bars_per_page": 1000},  # FMP para daily
}

POLYGON_AGGS_URL = "https://api.polygon.io/v2/aggs/ticker"
FMP_DAILY_URL = "https://financialmodelingprep.com/api/v3/historical-price-full"


async def fetch_polygon_chunk(
    symbol: str,
    multiplier: int,
    timespan: str,
    to_date: str,
    limit: int = 500,
    before_timestamp: Optional[int] = None
) -> tuple[List[dict], Optional[int]]:
    """
    Fetch chart data from Polygon - optimized for speed.
    Uses 50000 limit to get all data in one request.
    Returns (bars, oldest_timestamp) for lazy loading pagination.
    
    NOTA: Usa http_clients.polygon con connection pooling.
    """
    from datetime import datetime as dt, timedelta
    
    # Parse to_date
    try:
        to_dt = dt.strptime(to_date, "%Y-%m-%d")
    except:
        to_dt = dt.now()
    
    # Smart from_date based on desired bars and timeframe
    # ~7 trading hours per day, ~21 trading days per month
    if timespan == "minute":
        # Minutes: need more days for same number of bars
        bars_per_day = 390 // multiplier  # 390 min trading day
        # When loading more (before_timestamp set), need to go further back
        days_needed = max(10, (limit // bars_per_day) + 10)
    else:
        # Hours: ~7 trading hours per day
        bars_per_day = 7 // multiplier
        days_needed = max(30, (limit // max(1, bars_per_day)) + 10)
    
    from_date = (to_dt - timedelta(days=days_needed)).strftime("%Y-%m-%d")
    
    # Usar cliente Polygon con connection pooling
    data = await http_clients.polygon.get_aggregates(
        symbol=symbol,
        multiplier=multiplier,
        timespan=timespan,
        from_date=from_date,
        to_date=to_date,
        limit=50000  # Max limit - get all in one request
    )
    
    results = data.get("results", [])
    
    # Transform to our format
    all_bars = []
    for bar in results:
        bar_time = int(bar["t"] / 1000)
        # If before_timestamp is set, only include bars BEFORE that timestamp
        if before_timestamp and bar_time >= before_timestamp:
            continue
        all_bars.append({
            "time": bar_time,
            "open": float(bar["o"]),
            "high": float(bar["h"]),
            "low": float(bar["l"]),
            "close": float(bar["c"]),
            "volume": int(bar["v"])
        })
    
    # Take only the last 'limit' bars (most recent of the filtered set) if we got more
    full_count = len(all_bars)
    if len(all_bars) > limit:
        all_bars = all_bars[-limit:]
    
    # Determine if there's more data available (for lazy loading)
    oldest_time = all_bars[0]["time"] if all_bars else None
    has_more = full_count >= limit or data.get("next_url") is not None
    
    logger.info("polygon_chunk_fetched", symbol=symbol, bars=len(all_bars), total_available=full_count, oldest=oldest_time, before=before_timestamp)
    return all_bars, oldest_time if has_more else None


async def fetch_fmp_chunk(
    symbol: str,
    to_date: str,
    limit: int = 1000
) -> tuple[List[dict], Optional[int]]:
    """
    Fetch a chunk of daily data from FMP.
    
    NOTA: Usa http_clients.fmp con connection pooling.
    """
    # Usar cliente FMP con connection pooling
    raw_data = await http_clients.fmp.get_historical_prices(symbol, to_date)
    
    historical = raw_data.get("historical", [])
    if not historical:
        historical = raw_data if isinstance(raw_data, list) else []
    
    # FMP returns descending, take first 'limit' and reverse
    historical = historical[:limit]
    
    bars = []
    for bar in reversed(historical):
        try:
            date_str = bar.get("date", "")
            from datetime import datetime as dt
            dt_obj = dt.strptime(date_str, "%Y-%m-%d")
            
            bars.append({
                "time": int(dt_obj.timestamp()),
                "open": float(bar.get("open", 0)),
                "high": float(bar.get("high", 0)),
                "low": float(bar.get("low", 0)),
                "close": float(bar.get("close", 0)),
                "volume": int(bar.get("volume", 0))
            })
        except Exception:
            continue
    
    oldest_time = bars[0]["time"] if bars else None
    has_more = len(historical) >= limit
    
    logger.info("fmp_chunk_fetched", symbol=symbol, bars=len(bars))
    return bars, oldest_time if has_more else None


@app.get("/api/v1/chart/{symbol}")
async def get_chart_data(
    symbol: str,
    interval: str = Query(default="1day", description="Chart interval: 1min, 5min, 15min, 30min, 1hour, 4hour, 1day"),
    before: Optional[int] = Query(default=None, description="Load bars before this Unix timestamp (for lazy loading)"),
    limit: Optional[int] = Query(default=None, description="Number of bars to load (default: 500 for intraday, 1000 for daily)"),
    force_refresh: bool = Query(default=False, description="Force refresh from API")
):
    """
    Get OHLCV chart data - TradingView Style with Lazy Loading.
    
    Strategy:
    - First call (no 'before'): Returns most recent ~500 bars (fast!)
    - Subsequent calls (with 'before'): Returns older bars for infinite scroll
    
    Sources:
    - Intraday (1min-4hour): Polygon API
    - Daily (1day): FMP API
    
    Response:
    {
        "symbol": "AAPL",
        "interval": "1hour",
        "source": "polygon" | "fmp",
        "data": [...],
        "count": 500,
        "oldest_time": 1699876800,  // For next "load more" call
        "has_more": true,
        "cached": false
    }
    
    Frontend usage:
    1. Initial: GET /chart/AAPL?interval=1hour
    2. Load more: GET /chart/AAPL?interval=1hour&before=<oldest_time>
    """
    global redis_client
    
    symbol = symbol.upper()
    interval = interval.lower()
    
    # Validate interval
    if interval not in CHART_INTERVALS:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid interval. Supported: {', '.join(CHART_INTERVALS.keys())}"
        )
    
    config = CHART_INTERVALS[interval]
    bars_limit = limit or config["bars_per_page"]
    
    # Calculate to_date from 'before' parameter or use today
    if before:
        from datetime import datetime as dt
        to_date = dt.fromtimestamp(before - 1).strftime("%Y-%m-%d")
    else:
        to_date = datetime.now().strftime("%Y-%m-%d")
    
    # Cache key includes the 'before' for proper chunked caching
    cache_key = f"chart:v3:{symbol}:{interval}:{before or 'latest'}:{bars_limit}"
    
    try:
        # Check cache first
        if not force_refresh and redis_client:
            cached = await redis_client.get(cache_key)
            if cached:
                logger.debug("chart_cache_hit", symbol=symbol, interval=interval, before=before)
                return {
                    "symbol": symbol,
                    "interval": interval,
                    "source": cached.get("source", "unknown"),
                    "data": cached.get("data", []),
                    "count": len(cached.get("data", [])),
                    "oldest_time": cached.get("oldest_time"),
                    "has_more": cached.get("has_more", False),
                    "cached": True,
                    "fetched_at": cached.get("fetched_at")
                }
        
        chart_data = []
        oldest_time = None
        source = "unknown"
        
        # Usar clientes HTTP con connection pooling (ya inicializados)
        if interval == "1day":
            # Use FMP for daily data
            chart_data, oldest_time = await fetch_fmp_chunk(
                symbol, to_date, bars_limit
            )
            source = "fmp"
        else:
            # Use Polygon for intraday data
            chart_data, oldest_time = await fetch_polygon_chunk(
                symbol,
                config["polygon_multiplier"],
                config["polygon_timespan"],
                to_date,
                bars_limit,
                before_timestamp=before  # Pass the before timestamp for filtering
            )
            source = "polygon"
        
        has_more = oldest_time is not None
        
        # Cache the result (longer TTL for historical data)
        cache_ttl = config["cache_ttl"] if not before else 86400  # 24h for historical chunks
        result = {
            "data": chart_data,
            "source": source,
            "oldest_time": oldest_time,
            "has_more": has_more,
            "fetched_at": datetime.now().isoformat()
        }
        
        if redis_client and chart_data:
            await redis_client.set(cache_key, result, ttl=cache_ttl)
            logger.info("chart_chunk_cached", symbol=symbol, interval=interval, bars=len(chart_data), before=before)
        
        return {
            "symbol": symbol,
            "interval": interval,
            "source": source,
            "data": chart_data,
            "count": len(chart_data),
            "oldest_time": oldest_time,
            "has_more": has_more,
            "cached": False,
            "fetched_at": result["fetched_at"]
        }
    
    except httpx.HTTPError as e:
        logger.error("chart_http_error", symbol=symbol, interval=interval, error=str(e))
        raise HTTPException(status_code=502, detail=f"API error: {str(e)}")
    except Exception as e:
        logger.error("chart_error", symbol=symbol, interval=interval, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# WebSocket Endpoints
# ============================================================================

@app.websocket("/ws/scanner")
async def websocket_scanner(
    websocket: WebSocket,
    token: str = Query(None)  # Token JWT en query param: ws://...?token=xxx
):
    """
    WebSocket para datos del scanner en tiempo real
    
    🔒 AUTENTICACIÓN:
    - Requiere token JWT en query param: ws://host/ws/scanner?token=<jwt>
    - Para refresh de token (sin desconectar): {"action": "refresh_token", "token": "<new_jwt>"}
    
    El cliente puede enviar comandos:
    - {"action": "subscribe", "symbols": ["AAPL", "TSLA"]}
    - {"action": "unsubscribe", "symbols": ["AAPL"]}
    - {"action": "subscribe_all"}
    - {"action": "refresh_token", "token": "<new_jwt>"}
    
    El servidor envía:
    - {"type": "rvol", "symbol": "AAPL", "data": {...}}
    - {"type": "aggregate", "symbol": "AAPL", "data": {...}}
    """
    # =============================================
    # AUTENTICACIÓN AL CONECTAR
    # =============================================
    user = None
    ws_auth_enabled = getattr(settings, 'auth_enabled', False)
    
    if ws_auth_enabled:
        if not token:
            logger.warning("ws_connection_rejected reason=missing_token")
            await websocket.close(code=4001, reason="Token required")
            return
        
        try:
            user = await clerk_jwt_verifier.verify_token(token)
            logger.info(f"ws_authenticated user_id={user.id}")
        except Exception as e:
            logger.warning(f"ws_connection_rejected reason=invalid_token error={e}")
            await websocket.close(code=4003, reason="Invalid token")
            return
    
    connection_id = str(uuid.uuid4())
    
    await connection_manager.connect(websocket, connection_id)
    
    try:
        # Enviar mensaje de bienvenida
        await connection_manager.send_personal_message(
            {
                "type": "connected",
                "connection_id": connection_id,
                "message": "Connected to Tradeul Scanner",
                "timestamp": datetime.now().isoformat()
            },
            connection_id
        )
        
        # Loop para recibir comandos del cliente
        while True:
            data = await websocket.receive_json()
            
            action = data.get("action")
            
            if action == "subscribe":
                symbols = set(data.get("symbols", []))
                connection_manager.subscribe(connection_id, symbols)
                
                await connection_manager.send_personal_message(
                    {
                        "type": "subscribed",
                        "symbols": list(symbols),
                        "timestamp": datetime.now().isoformat()
                    },
                    connection_id
                )
            
            elif action == "unsubscribe":
                symbols = set(data.get("symbols", []))
                connection_manager.unsubscribe(connection_id, symbols)
                
                await connection_manager.send_personal_message(
                    {
                        "type": "unsubscribed",
                        "symbols": list(symbols),
                        "timestamp": datetime.now().isoformat()
                    },
                    connection_id
                )
            
            elif action == "subscribe_all":
                connection_manager.subscribe(connection_id, {"*"})
                
                await connection_manager.send_personal_message(
                    {
                        "type": "subscribed_all",
                        "message": "Subscribed to all tickers",
                        "timestamp": datetime.now().isoformat()
                    },
                    connection_id
                )
            
            elif action == "refresh_token":
                # Refresh token sin desconectar (Clerk tokens expiran en 60s)
                new_token = data.get("token")
                if new_token and ws_auth_enabled:
                    try:
                        user = await clerk_jwt_verifier.verify_token(new_token)
                        logger.debug(f"ws_token_refreshed user_id={user.id}")
                        await connection_manager.send_personal_message(
                            {
                                "type": "token_refreshed",
                                "success": True,
                                "timestamp": datetime.now().isoformat()
                            },
                            connection_id
                        )
                    except Exception as e:
                        logger.warning(f"ws_token_refresh_failed error={e}")
                        await connection_manager.send_personal_message(
                            {
                                "type": "token_refresh_failed",
                                "error": str(e),
                                "timestamp": datetime.now().isoformat()
                            },
                            connection_id
                        )
            
            elif action == "ping":
                await connection_manager.send_personal_message(
                    {
                        "type": "pong",
                        "timestamp": datetime.now().isoformat()
                    },
                    connection_id
                )
    
    except WebSocketDisconnect:
        connection_manager.disconnect(connection_id)
        logger.info("websocket_disconnected", connection_id=connection_id)
    
    except Exception as e:
        logger.error(
            "websocket_error",
            connection_id=connection_id,
            error=str(e)
        )
        connection_manager.disconnect(connection_id)


# ============================================================================
# Eleven Labs TTS Proxy (para evitar CORS)
# ============================================================================

@app.post("/api/v1/tts/speak")
async def text_to_speech(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user)  # 🔒 Requiere auth - endpoint costoso
):
    """
    Proxy para Eleven Labs TTS - evita problemas de CORS
    PROTEGIDO: Requiere autenticación (endpoint costoso - Eleven Labs $$$)
    """
    logger.info(f"tts_request user_id={user.id}")
    try:
        body = await request.json()
        text = body.get("text", "")
        voice_id = body.get("voice_id", "21m00Tcm4TlvDq8ikWAM")  # Rachel
        language_code = body.get("language_code", "es")  # Forzar español por defecto
        
        if not text:
            raise HTTPException(status_code=400, detail="Text is required")
        
        if not http_clients.elevenlabs:
            raise HTTPException(status_code=503, detail="TTS service not configured")
        
        # Usar cliente Eleven Labs con connection pooling
        audio_content = await http_clients.elevenlabs.text_to_speech(
            text=text,
            voice_id=voice_id,
            language_code=language_code
        )
        
        return Response(
            content=audio_content,
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": "inline",
                "Cache-Control": "no-cache"
            }
        )
            
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="TTS service timeout")
    except httpx.HTTPStatusError as e:
        logger.error(f"Eleven Labs error: {e.response.status_code}")
        raise HTTPException(status_code=e.response.status_code, detail="TTS service error")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"TTS error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "services.api_gateway.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_config=None  # Usar nuestro logger personalizado
    )

