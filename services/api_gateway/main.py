"""
API Gateway - Main Entry Point

Gateway principal para el frontend web:
- REST API para consultas
- WebSocket para datos en tiempo real
- Agregación de múltiples servicios
"""

import asyncio
import uuid
from datetime import datetime
from typing import Optional, List
import structlog
import httpx
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from shared.config.settings import settings
from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import configure_logging, get_logger
from ws_manager import ConnectionManager
from routes.user_prefs import router as user_prefs_router, set_timescale_client
from routes.financials import router as financials_router, set_redis_client as set_financials_redis, set_fmp_api_key

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
    
    # Inicializar TimescaleDB (requerido para preferencias de usuario)
    timescale_client = TimescaleClient()
    await timescale_client.connect()
    set_timescale_client(timescale_client)
    logger.info("timescale_connected")
    
    # Configurar router de financials con Redis y FMP API key
    set_financials_redis(redis_client)
    set_fmp_api_key(settings.FMP_API_KEY)
    logger.info("financials_router_configured_fmp")
    
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción: especificar dominios exactos
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registrar routers
app.include_router(user_prefs_router)
app.include_router(financials_router)


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
        # Obtener sesión de mercado actual
        try:
            async with httpx.AsyncClient() as client:
                session_response = await client.get("http://market_session:8002/api/session/current", timeout=2.0)
                if session_response.status_code == 200:
                    session_data = session_response.json()
                    current_session = session_data.get('session', 'POST_MARKET')
                else:
                    current_session = 'POST_MARKET'
        except:
            current_session = 'POST_MARKET'
        
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
        
        # Fallback: intentar leer del stream (por compatibilidad)
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
        # Proxy a ticker-metadata-service
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"http://ticker_metadata:8010/api/v1/metadata/search",
                params={"q": q, "limit": limit}
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(
                    "metadata_search_error",
                    query=q,
                    status=response.status_code
                )
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Search failed: {response.text}"
                )
    
    except httpx.TimeoutException:
        logger.error("metadata_search_timeout", query=q)
        raise HTTPException(status_code=504, detail="Search timeout")
    except httpx.ConnectError:
        logger.error("metadata_search_unavailable", query=q)
        raise HTTPException(status_code=503, detail="Metadata service unavailable")
    except HTTPException:
        raise
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
        
        # Intentar obtener de ticker-metadata-service
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"http://ticker_metadata:8010/api/v1/metadata/{symbol}"
                )
                
                if response.status_code == 200:
                    logger.info("metadata_service_success", symbol=symbol)
                    return response.json()
                elif response.status_code == 404:
                    # El servicio no encontró datos, usar fallback
                    logger.info("metadata_service_404_using_fallback", symbol=symbol)
                else:
                    logger.warning(
                        "metadata_service_error",
                        symbol=symbol,
                        status=response.status_code
                    )
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
        # Agregar API key a la URL
        separator = "&" if "?" in url else "?"
        proxied_url = f"{url}{separator}apiKey={settings.POLYGON_API_KEY}"
        
        # Hacer request al logo
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(proxied_url)
            
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
    limit: int = Query(50, ge=1, le=200, description="Limit results")
):
    """
    Proxy para el servicio de News (Benzinga y futuras fuentes)
    """
    try:
        params = {"limit": limit}
        if ticker:
            params["ticker"] = ticker
        if channels:
            params["channels"] = channels
        if tags:
            params["tags"] = tags
        if author:
            params["author"] = author
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "http://benzinga-news:8015/api/v1/news",
                params=params
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Benzinga news service error: {response.text}"
                )
    
    except httpx.TimeoutException:
        logger.error("news_service_timeout")
        raise HTTPException(status_code=504, detail="News service timeout")
    except httpx.ConnectError:
        logger.error("news_service_unavailable")
        raise HTTPException(status_code=503, detail="News service unavailable")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("news_service_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/news/api/v1/news/latest")
async def proxy_news_latest(limit: int = Query(50, ge=1, le=200)):
    """Proxy para las últimas noticias"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "http://benzinga-news:8015/api/v1/news/latest",
                params={"limit": limit}
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=response.text
                )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Service timeout")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Service unavailable")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("benzinga_latest_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/news/api/v1/news/ticker/{ticker}")
async def proxy_news_by_ticker(ticker: str, limit: int = Query(50, ge=1, le=200)):
    """Proxy para noticias por ticker"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"http://benzinga-news:8015/api/v1/news/ticker/{ticker}",
                params={"limit": limit}
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=response.text
                )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Service timeout")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Service unavailable")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("news_ticker_error", error=str(e), ticker=ticker)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# WebSocket Endpoints
# ============================================================================

@app.websocket("/ws/scanner")
async def websocket_scanner(websocket: WebSocket):
    """
    WebSocket para datos del scanner en tiempo real
    
    El cliente puede enviar comandos:
    - {"action": "subscribe", "symbols": ["AAPL", "TSLA"]}
    - {"action": "unsubscribe", "symbols": ["AAPL"]}
    - {"action": "subscribe_all"}
    
    El servidor envía:
    - {"type": "rvol", "symbol": "AAPL", "data": {...}}
    - {"type": "aggregate", "symbol": "AAPL", "data": {...}}
    """
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

