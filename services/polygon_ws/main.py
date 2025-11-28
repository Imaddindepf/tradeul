"""
Polygon WebSocket Connector - Main Entry Point

Conecta al WebSocket de Polygon y consume datos en tiempo real:
- Trades
- Quotes (para tickers individuales y watchlists)
- Aggregates (per second para el Scanner)

Se suscribe dinámicamente a:
- Aggregates: tickers filtrados por el Scanner
- Quotes: tickers solicitados por usuarios (TickerSpan, Watchlists)
"""

import asyncio
from datetime import datetime
from typing import Optional, Set
import structlog
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from shared.config.settings import settings
from shared.utils.redis_client import RedisClient
from shared.utils.logger import configure_logging, get_logger
from shared.models.polygon import PolygonTrade, PolygonQuote, PolygonAgg
from ws_client import PolygonWebSocketClient
from subscription_reconciler import SubscriptionReconciler

# Configurar logger
configure_logging(service_name="polygon_ws")
logger = get_logger(__name__)

# ============================================================================
# Global State
# ============================================================================

redis_client: Optional[RedisClient] = None
ws_client: Optional[PolygonWebSocketClient] = None
subscription_task: Optional[asyncio.Task] = None
quote_subscription_task: Optional[asyncio.Task] = None  # Nueva tarea para quotes
reconciler: Optional[SubscriptionReconciler] = None
reconciler_task: Optional[asyncio.Task] = None

# Set de tickers suscritos a Quotes (separado de Aggregates)
quote_subscribed_tickers: Set[str] = set()


# ============================================================================
# Lifecycle Management
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestión del ciclo de vida de la aplicación"""
    global redis_client, ws_client, subscription_task, quote_subscription_task, reconciler, reconciler_task
    
    logger.info("polygon_ws_service_starting")
    
    # Inicializar Redis
    redis_client = RedisClient()
    await redis_client.connect()
    
    # Inicializar WebSocket Client
    # Ahora usamos Aggregates (Scanner) + Quotes (Tickers individuales/Watchlists)
    ws_client = PolygonWebSocketClient(
        api_key=settings.POLYGON_API_KEY,
        on_trade=None,  # Desactivado - no necesario
        on_quote=handle_quote,  # ✅ ACTIVADO para tickers individuales
        on_aggregate=handle_aggregate  # Para Scanner
    )
    
    # 🔥 PATRÓN PROFESIONAL: Inicializar Reconciler (solo para Aggregates)
    reconciler = SubscriptionReconciler(
        redis_client=redis_client,
        ws_client=ws_client,
        event_types={"A"},  # Solo Aggregates
        interval_seconds=30  # Reconciliar cada 30 segundos
    )
    
    # Iniciar tareas en background
    ws_task = asyncio.create_task(ws_client.connect())
    subscription_task = asyncio.create_task(manage_subscriptions())
    quote_subscription_task = asyncio.create_task(manage_quote_subscriptions())  # ✅ Nueva tarea
    reconciler_task = asyncio.create_task(reconciler.start())
    
    logger.info("polygon_ws_service_started", reconciler_enabled=True, quotes_enabled=True)
    
    yield
    
    # Shutdown
    logger.info("polygon_ws_service_shutting_down")
    
    if reconciler:
        await reconciler.stop()
    
    if reconciler_task:
        reconciler_task.cancel()
        try:
            await reconciler_task
        except asyncio.CancelledError:
            pass
    
    if subscription_task:
        subscription_task.cancel()
        try:
            await subscription_task
        except asyncio.CancelledError:
            pass
    
    if quote_subscription_task:
        quote_subscription_task.cancel()
        try:
            await quote_subscription_task
        except asyncio.CancelledError:
            pass
    
    if ws_client:
        await ws_client.close()
    
    if ws_task:
        ws_task.cancel()
        try:
            await ws_task
        except asyncio.CancelledError:
            pass
    
    if redis_client:
        await redis_client.disconnect()
    
    logger.info("polygon_ws_service_stopped")


# ============================================================================
# FastAPI App
# ============================================================================

app = FastAPI(
    title="Polygon WebSocket Connector",
    description="Conecta al WebSocket de Polygon para datos en tiempo real",
    version="1.0.0",
    lifespan=lifespan
)


# ============================================================================
# WebSocket Message Handlers
# ============================================================================

async def handle_trade(trade: PolygonTrade):
    """
    Procesa un mensaje de Trade del WebSocket
    
    Args:
        trade: Trade de Polygon
    """
    try:
        # Publicar a Redis Stream
        await redis_client.publish_to_stream(
            "stream:realtime:trades",
            {
                'symbol': trade.sym,
                'price': str(trade.p),
                'size': str(trade.s),
                'conditions': ','.join(map(str, trade.c)) if trade.c else '',
                'exchange': str(trade.x),
                'trade_id': trade.i,
                'timestamp': str(trade.t),
                'tape': str(trade.z) if trade.z else ''
            }
        )
        
        logger.debug(
            "trade_published",
            symbol=trade.sym,
            price=trade.p,
            size=trade.s
        )
        
    except Exception as e:
        logger.error(
            "trade_handler_error",
            symbol=trade.sym,
            error=str(e)
        )


async def handle_quote(quote: PolygonQuote):
    """
    Procesa un mensaje de Quote del WebSocket
    
    Args:
        quote: Quote de Polygon
    """
    try:
        # Publicar a Redis Stream
        await redis_client.publish_to_stream(
            "stream:realtime:quotes",
            {
                'symbol': quote.sym,
                'bid_price': str(quote.bp),
                'bid_size': str(quote.bs),
                'ask_price': str(quote.ap),
                'ask_size': str(quote.as_),
                'bid_exchange': str(quote.bx),
                'ask_exchange': str(quote.ax),
                'timestamp': str(quote.t),
                'tape': str(quote.z) if quote.z else ''
            }
        )
        
        logger.debug(
            "quote_published",
            symbol=quote.sym,
            bid=quote.bp,
            ask=quote.ap
        )
        
    except Exception as e:
        logger.error(
            "quote_handler_error",
            symbol=quote.sym,
            error=str(e)
        )


async def handle_aggregate(agg: PolygonAgg):
    """
    Procesa un mensaje de Aggregate del WebSocket
    
    IMPORTANTE: agg.av contiene el volumen ACUMULADO del día.
    Este es el mismo campo que snapshot.min.av.
    
    Args:
        agg: Aggregate de Polygon
    """
    try:
        # Publicar a Redis Stream
        # NOTA: Usamos volume_accumulated (de agg.av) para consistencia
        # con el Analytics Service
        await redis_client.publish_to_stream(
            "stream:realtime:aggregates",
            {
                'symbol': agg.sym,
                'open': str(agg.o),
                'high': str(agg.h),
                'low': str(agg.l),
                'close': str(agg.c),
                'volume': str(agg.v),  # Volumen del segundo
                'volume_accumulated': str(agg.av),  # ← Volumen acumulado del día
                'vwap': str(agg.a),  # Today's VWAP
                'avg_trade_size': str(agg.z),  # Average trade size
                'timestamp_start': str(agg.s),
                'timestamp_end': str(agg.e),
                'otc': 'true' if agg.otc else 'false'
            }
        )
        
        logger.info(
            "aggregate_published",
            symbol=agg.sym,
            close=agg.c,
            volume_accumulated=agg.av
        )
        
    except Exception as e:
        logger.error(
            "aggregate_handler_error",
            symbol=agg.sym,
            error=str(e)
        )


# ============================================================================
# Subscription Management
# ============================================================================

async def manage_subscriptions():
    """
    Gestiona suscripciones dinámicas basadas en tickers que el frontend necesita
    
    Lee del stream `polygon_ws:subscriptions` los tickers que websocket_server
    publica cuando el frontend se suscribe/desuscribe.
    
    IMPORTANTE: Maneja reconexiones re-suscribiendo todos los tickers activos.
    """
    logger.info("subscription_manager_started")
    
    # Stream de entrada: tickers que el frontend necesita (publicado por websocket_server)
    input_stream = "polygon_ws:subscriptions"
    consumer_group = "polygon_ws_subscriptions_group"
    consumer_name = "polygon_ws_subscriptions_consumer"
    
    # Tipos de eventos a suscribir - SOLO AGGREGATES
    event_types = {"A"}  # Solo Aggregates (OHLCV por segundo)
    
    # Set de tickers que DEBEN estar suscritos (persiste entre reconexiones)
    desired_subscriptions: Set[str] = set()
    
    # Track si estábamos autenticados en la iteración anterior
    was_authenticated = False
    
    # Crear consumer group si no existe
    try:
        await redis_client.create_consumer_group(
            input_stream,
            consumer_group,
            mkstream=True
        )
        logger.info(f"Consumer group '{consumer_group}' created")
    except Exception as e:
        logger.debug("consumer_group_already_exists", error=str(e))
    
    # BOOTSTRAP: Leer tickers activos desde el SET (estado actual del scanner)
    # Este es el estado de verdad - más confiable que reconstruir desde stream
    try:
        # Primero: Leer SET con tickers actualmente en categorías del scanner
        active_tickers_raw = await redis_client.client.smembers('polygon_ws:active_tickers')
        active_tickers = {t.decode() if isinstance(t, bytes) else t for t in active_tickers_raw}
        
        if active_tickers:
            desired_subscriptions.update(active_tickers)
            logger.info(
                "bootstrap_from_active_tickers_set",
                total_tickers=len(desired_subscriptions),
                examples=sorted(list(desired_subscriptions))[:10]
            )
        else:
            logger.warning(
                "active_tickers_set_empty",
                message="Scanner no ha procesado tickers aún o mercado cerrado"
            )
        
        # Segundo: Procesar últimos 500 mensajes del stream para cambios muy recientes
        # (esto captura cambios que ocurrieron mientras leíamos el SET)
        results = await redis_client.read_stream_range(
            stream_name=input_stream,
            count=500,  # Solo últimos 500 (cambios recientes)
            start="-",
            end="+"
        )
        
        if results:
            for message_id, data in reversed(results):
                symbol = data.get('symbol', '').upper()
                action = data.get('action', '').lower()
                
                if symbol and action == "subscribe":
                    desired_subscriptions.add(symbol)
                elif symbol and action == "unsubscribe":
                    desired_subscriptions.discard(symbol)
            
            logger.info(
                "applied_recent_changes_from_stream",
                stream_messages=len(results),
                final_total=len(desired_subscriptions)
            )
    except Exception as e:
        logger.error("error_bootstrapping_subscriptions", error=str(e))
    
    while True:
        try:
            # CRÍTICO: Detectar reconexión y re-suscribir a todos los tickers
            if ws_client.is_authenticated and not was_authenticated:
                # Acabamos de reconectar y autenticar
                # SOLUCIÓN: RE-LEER el SET completo para evitar corrupción
                # El desired_subscriptions en memoria puede estar desactualizado
                # debido a race conditions entre unsubscribe/subscribe durante reconexiones
                try:
                    active_tickers_raw = await redis_client.client.smembers('polygon_ws:active_tickers')
                    active_tickers_fresh = {t.decode() if isinstance(t, bytes) else t for t in active_tickers_raw}
                    
                    # Merge con desired_subscriptions existente (por si hay cambios del stream)
                    # pero priorizar el SET como fuente de verdad
                    desired_subscriptions = active_tickers_fresh.copy()
                    
                    logger.info(
                        "re_subscribing_after_reconnection",
                        tickers_count=len(desired_subscriptions),
                        refreshed_from_set=True
                    )
                except Exception as refresh_error:
                    logger.error(
                        "error_refreshing_from_set_on_reconnect",
                        error=str(refresh_error)
                    )
                    # Fallback: usar desired_subscriptions en memoria
                    logger.warning(
                        "using_memory_state_as_fallback",
                        tickers_count=len(desired_subscriptions)
                    )
                
                if desired_subscriptions:
                    await ws_client.subscribe_to_tickers(desired_subscriptions, event_types)
                was_authenticated = True
            elif not ws_client.is_authenticated:
                was_authenticated = False
            
            # Leer mensajes del stream de suscripciones
            messages = await redis_client.read_stream(
                stream_name=input_stream,
                consumer_group=consumer_group,
                consumer_name=consumer_name,
                count=100,
                block=5000  # 5 segundos
            )
            
            if messages:
                message_ids_to_ack = []
                
                for stream_name, stream_messages in messages:
                    for message_id, data in stream_messages:
                        symbol = data.get('symbol', '').upper()
                        action = data.get('action', '').lower()  # "subscribe" o "unsubscribe"
                        
                        if not symbol or not action:
                            message_ids_to_ack.append(message_id)
                            continue
                        
                        if action == "subscribe":
                            # Añadir a desired subscriptions
                            desired_subscriptions.add(symbol)
                            
                            # Suscribir si estamos autenticados y no está ya en Polygon
                            if ws_client.is_authenticated and symbol not in ws_client.subscribed_tickers:
                                await ws_client.subscribe_to_tickers({symbol}, event_types)
                                logger.info(
                                    "ticker_subscribed",
                                    symbol=symbol,
                                    total_subscribed=len(ws_client.subscribed_tickers)
                                )
                        
                        elif action == "unsubscribe":
                            # Quitar de desired subscriptions
                            desired_subscriptions.discard(symbol)
                            
                            # Desuscribir si está suscrito
                            if ws_client.is_authenticated and symbol in ws_client.subscribed_tickers:
                                await ws_client.unsubscribe_from_tickers({symbol}, event_types)
                                logger.info(
                                    "ticker_unsubscribed",
                                    symbol=symbol,
                                    total_subscribed=len(ws_client.subscribed_tickers)
                                )
                        
                        message_ids_to_ack.append(message_id)
                
                # ACK de todos los mensajes procesados
                if message_ids_to_ack:
                    try:
                        await redis_client.xack(
                            input_stream,
                            consumer_group,
                            *message_ids_to_ack
                        )
                    except Exception as e:
                        logger.error("xack_error", error=str(e))
        
        except asyncio.CancelledError:
            logger.info("subscription_manager_cancelled")
            raise
        
        except Exception as e:
            logger.error(
                "subscription_manager_error",
                error=str(e),
                error_type=type(e).__name__
            )
            await asyncio.sleep(5)


# ============================================================================
# Quote Subscription Management (para Tickers Individuales y Watchlists)
# ============================================================================

async def manage_quote_subscriptions():
    """
    Gestiona suscripciones dinámicas de QUOTES para tickers individuales.
    
    Diferente de Aggregates (Scanner), los Quotes son para:
    - TickerSpan: mostrar precio bid/ask en tiempo real de un ticker
    - Watchlists: lista personalizada de tickers del usuario
    
    Usa Redis Pub/Sub para comunicación eficiente:
    - Canal: polygon_ws:quote_commands
    - Mensajes: {"action": "subscribe"|"unsubscribe", "symbols": ["AAPL", "TSLA"]}
    
    Optimización: Solo una conexión a Polygon para todos los usuarios.
    Si 100 usuarios miran AAPL, solo una suscripción a Polygon.
    """
    global quote_subscribed_tickers
    
    logger.info("quote_subscription_manager_started")
    
    # Stream de entrada para comandos de quotes
    input_stream = "polygon_ws:quote_subscriptions"
    consumer_group = "polygon_ws_quotes_group"
    consumer_name = "polygon_ws_quotes_consumer"
    
    # Crear consumer group si no existe
    try:
        await redis_client.create_consumer_group(
            input_stream,
            consumer_group,
            mkstream=True
        )
        logger.info(f"Consumer group '{consumer_group}' created for quotes")
    except Exception as e:
        logger.debug("quotes_consumer_group_already_exists", error=str(e))
    
    # Track de autenticación para re-suscribir
    was_authenticated = False
    
    while True:
        try:
            # Detectar reconexión y re-suscribir a todos los quotes
            if ws_client.is_authenticated and not was_authenticated:
                if quote_subscribed_tickers:
                    logger.info(
                        "re_subscribing_quotes_after_reconnection",
                        count=len(quote_subscribed_tickers)
                    )
                    await ws_client.subscribe_to_tickers(quote_subscribed_tickers, {"Q"})
                was_authenticated = True
            elif not ws_client.is_authenticated:
                was_authenticated = False
            
            # Leer comandos de suscripción de quotes
            messages = await redis_client.read_stream(
                stream_name=input_stream,
                consumer_group=consumer_group,
                consumer_name=consumer_name,
                count=100,
                block=5000  # 5 segundos
            )
            
            if messages:
                message_ids_to_ack = []
                
                for stream_name, stream_messages in messages:
                    for message_id, data in stream_messages:
                        symbol = data.get('symbol', '').upper()
                        action = data.get('action', '').lower()
                        
                        if not symbol or not action:
                            message_ids_to_ack.append(message_id)
                            continue
                        
                        if action == "subscribe":
                            if symbol not in quote_subscribed_tickers:
                                quote_subscribed_tickers.add(symbol)
                                
                                if ws_client.is_authenticated:
                                    await ws_client.subscribe_to_tickers({symbol}, {"Q"})
                                    logger.info(
                                        "quote_subscribed",
                                        symbol=symbol,
                                        total_quotes=len(quote_subscribed_tickers)
                                    )
                        
                        elif action == "unsubscribe":
                            if symbol in quote_subscribed_tickers:
                                quote_subscribed_tickers.discard(symbol)
                                
                                if ws_client.is_authenticated:
                                    await ws_client.unsubscribe_from_tickers({symbol}, {"Q"})
                                    logger.info(
                                        "quote_unsubscribed",
                                        symbol=symbol,
                                        total_quotes=len(quote_subscribed_tickers)
                                    )
                        
                        message_ids_to_ack.append(message_id)
                
                # ACK de todos los mensajes procesados
                if message_ids_to_ack:
                    try:
                        await redis_client.xack(
                            input_stream,
                            consumer_group,
                            *message_ids_to_ack
                        )
                    except Exception as e:
                        logger.error("quote_xack_error", error=str(e))
        
        except asyncio.CancelledError:
            logger.info("quote_subscription_manager_cancelled")
            raise
        
        except Exception as e:
            logger.error(
                "quote_subscription_manager_error",
                error=str(e),
                error_type=type(e).__name__
            )
            await asyncio.sleep(5)


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "polygon_ws",
        "timestamp": datetime.now().isoformat(),
        "ws_connected": ws_client.is_connected if ws_client else False,
        "ws_authenticated": ws_client.is_authenticated if ws_client else False
    }


@app.get("/stats")
async def get_stats():
    """Obtiene estadísticas del servicio"""
    if not ws_client:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    stats = ws_client.get_stats()
    
    return JSONResponse(content=stats)


@app.get("/subscriptions")
async def get_subscriptions():
    """Obtiene las suscripciones activas de Aggregates (Scanner)"""
    if not ws_client:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    return {
        "subscribed_tickers": list(ws_client.subscribed_tickers),
        "count": len(ws_client.subscribed_tickers),
        "is_authenticated": ws_client.is_authenticated
    }


@app.get("/subscriptions/quotes")
async def get_quote_subscriptions():
    """Obtiene las suscripciones activas de Quotes (Tickers individuales)"""
    global quote_subscribed_tickers
    
    if not ws_client:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    return {
        "subscribed_tickers": list(quote_subscribed_tickers),
        "count": len(quote_subscribed_tickers),
        "is_authenticated": ws_client.is_authenticated,
        "type": "quotes"
    }


@app.get("/reconciler/metrics")
async def get_reconciler_metrics():
    """Get subscription reconciler metrics"""
    if not reconciler:
        raise HTTPException(status_code=503, detail="Reconciler not initialized")
    
    return reconciler.get_metrics()


@app.post("/reconciler/force")
async def force_reconciliation():
    """Force immediate reconciliation (useful for debugging)"""
    if not reconciler:
        raise HTTPException(status_code=503, detail="Reconciler not initialized")
    
    await reconciler.force_reconcile()
    return {
        "status": "reconciliation_executed",
        "timestamp": datetime.now().isoformat()
    }


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "services.polygon_ws.main:app",
        host="0.0.0.0",
        port=8006,
        reload=False,
        log_config=None  # Usar nuestro logger personalizado
    )

