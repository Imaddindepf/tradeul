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
from typing import Optional, Set, List
import structlog
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from shared.config.settings import settings
from shared.utils.redis_client import RedisClient
from shared.utils.logger import configure_logging, get_logger
from shared.utils.redis_stream_manager import (
    initialize_stream_manager,
    get_stream_manager
)
from shared.models.polygon import PolygonTrade, PolygonQuote, PolygonAgg, PolygonLuld
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
catalyst_subscription_task: Optional[asyncio.Task] = None  # Tarea para catalyst alerts
luld_subscription_task: Optional[asyncio.Task] = None  # Tarea para LULD subscription
luld_subscribed: bool = False  # Flag para LULD subscription
nasdaq_rss_task: Optional[asyncio.Task] = None  # Tarea para NASDAQ RSS polling
reconciler: Optional[SubscriptionReconciler] = None
reconciler_task: Optional[asyncio.Task] = None

# Set de tickers suscritos a Quotes (separado de Aggregates)
quote_subscribed_tickers: Set[str] = set()

# Set de tickers suscritos temporalmente para Catalyst Alerts (Aggregates sin reconciler)
catalyst_subscribed_tickers: Set[str] = set()


# ============================================================================
# Lifecycle Management
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestión del ciclo de vida de la aplicación"""
    global redis_client, ws_client, subscription_task, quote_subscription_task, catalyst_subscription_task, luld_subscription_task, reconciler, reconciler_task
    
    logger.info("polygon_ws_service_starting")
    
    # Inicializar Redis
    redis_client = RedisClient()
    await redis_client.connect()
    
    # Inicializar Stream Manager para publicar eventos de halts
    stream_manager = initialize_stream_manager(redis_client)
    await stream_manager.start()
    
    # Inicializar WebSocket Client
    # Ahora usamos Aggregates (Scanner) + Quotes (Tickers individuales/Watchlists) + LULD (todo mercado)
    ws_client = PolygonWebSocketClient(
        api_key=settings.POLYGON_API_KEY,
        on_trade=None,  # Desactivado - no necesario
        on_quote=handle_quote,  # ✅ ACTIVADO para tickers individuales
        on_aggregate=handle_aggregate,  # Para Scanner
        on_luld=handle_luld  # ✅ LULD para halts/pauses de TODO el mercado
    )
    
    # 🔥 PATRÓN PROFESIONAL: Inicializar Reconciler (solo para Aggregates)
    # IMPORTANTE: Excluimos catalyst_subscribed_tickers para no desuscribir
    # tickers que están siendo monitoreados temporalmente por el catalyst engine
    reconciler = SubscriptionReconciler(
        redis_client=redis_client,
        ws_client=ws_client,
        event_types={"A"},  # Solo Aggregates
        interval_seconds=30,  # Reconciliar cada 30 segundos
        exclude_sets=[catalyst_subscribed_tickers]  # No tocar suscripciones de catalyst
    )
    
    # Iniciar tareas en background
    ws_task = asyncio.create_task(ws_client.connect())
    subscription_task = asyncio.create_task(manage_subscriptions())
    quote_subscription_task = asyncio.create_task(manage_quote_subscriptions())
    catalyst_subscription_task = asyncio.create_task(manage_catalyst_subscriptions())
    luld_subscription_task = asyncio.create_task(manage_luld_subscription())  # LULD para todo el mercado
    nasdaq_rss_task = asyncio.create_task(poll_nasdaq_rss_halts())  # RSS feed de alta frecuencia
    reconciler_task = asyncio.create_task(reconciler.start())
    
    logger.info(
        "polygon_ws_service_started",
        reconciler_enabled=True,
        quotes_enabled=True,
        catalyst_enabled=True,
        luld_enabled=True,
        nasdaq_rss_enabled=True
    )
    
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
    
    if catalyst_subscription_task:
        catalyst_subscription_task.cancel()
        try:
            await catalyst_subscription_task
        except asyncio.CancelledError:
            pass
    
    if luld_subscription_task:
        luld_subscription_task.cancel()
        try:
            await luld_subscription_task
        except asyncio.CancelledError:
            pass
    
    if nasdaq_rss_task:
        nasdaq_rss_task.cancel()
        try:
            await nasdaq_rss_task
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
    
    # Stop Stream Manager
    await stream_manager.stop()
    
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
                # Trades: usar 'n' si existe (minute aggs), sino calcular desde volume/avg_trade_size
                'trades': str(getattr(agg, 'n', 0) or (int(agg.v / agg.z) if agg.z > 0 else 0)),
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


def _determine_halt_reason(indicators: List[int]) -> str:
    """
    Determina la razón del halt basándose en indicadores LULD
    
    Returns:
        Código de razón (T1, T5, LUDP, etc.) o descripción
    """
    # Mapeo de indicadores a razones
    if 17 in indicators:  # Halted
        # Por defecto asumimos volatility pause (LUDP) ya que es lo más común en LULD
        return "LUDP"
    return "UNKNOWN"


async def _publish_halt_event(halt_data: dict, event_type: str):
    """
    Publica un evento de halt/resume al stream para que el scanner lo procese.
    
    El scanner consumirá estos eventos, enriquecerá con métricas (market_cap, 
    rvol, free_float, etc.) y los mostrará como una categoría especial.
    
    Args:
        halt_data: Diccionario con datos del halt
        event_type: "HALT" o "RESUME"
    """
    import json
    from datetime import datetime
    
    try:
        stream_manager = get_stream_manager()
        
        # Preparar payload para el stream
        # Usamos JSON string porque Redis streams solo soportan strings
        stream_data = {
            "event_type": event_type,
            "symbol": halt_data['symbol'],
            "data": json.dumps(halt_data),
            "timestamp": str(datetime.utcnow().isoformat())
        }
        
        await stream_manager.xadd(
            settings.stream_halt_events,
            stream_data
        )
        
        logger.debug(
            "halt_event_published",
            symbol=halt_data['symbol'],
            event_type=event_type,
            stream=settings.stream_halt_events
        )
        
    except Exception as e:
        # No fallar el flujo principal si hay error publicando al stream
        logger.error(
            "halt_event_publish_failed",
            symbol=halt_data['symbol'],
            event_type=event_type,
            error=str(e)
        )


async def _update_halt_state(luld: PolygonLuld, event_type: str):
    """
    Actualiza el estado de halts en Redis y publica al stream para el scanner.
    
    Mantiene dos estructuras:
    1. halts:active - Hash con halts activos (para consulta rápida)
    2. halts:history:{date} - Hash con historial del día (para tabla completa)
    
    Además publica eventos al stream:halt:events para que el scanner
    los procese y enriquezca con métricas adicionales.
    
    Args:
        luld: Mensaje LULD
        event_type: "HALT", "RESUME" u otro
    """
    from datetime import datetime
    import json
    
    symbol = luld.sym
    # Polygon WebSocket envía timestamps en nanosegundos, convertir a milisegundos
    # Un timestamp en nanosegundos tiene ~19 dígitos, milisegundos tiene ~13
    raw_timestamp = luld.t
    if raw_timestamp > 1e15:  # Si es mayor que 10^15, es nanosegundos
        timestamp_ms = raw_timestamp // 1_000_000  # Convertir ns a ms
    else:
        timestamp_ms = raw_timestamp
    today = datetime.utcnow().strftime('%Y-%m-%d')
    
    # Keys de Redis
    active_key = "halts:active"
    history_key = f"halts:history:{today}"
    
    if event_type == "HALT":
        # Nuevo halt detectado
        halt_data = {
            'symbol': symbol,
            'halt_time': timestamp_ms,
            'halt_reason': _determine_halt_reason(luld.indicators),
            'halt_reason_desc': ','.join(luld.get_indicator_names()),
            'status': 'HALTED',
            'resume_time': None,
            'duration_seconds': None,
            'upper_band': luld.upper_band,
            'lower_band': luld.lower_band,
            'indicators': luld.indicators,
        }
        
        # Guardar en halts activos
        await redis_client.client.hset(active_key, symbol, json.dumps(halt_data))
        
        # Guardar en historial (key = symbol:timestamp para soportar múltiples halts del mismo ticker)
        history_id = f"{symbol}:{timestamp_ms}"
        await redis_client.client.hset(history_key, history_id, json.dumps(halt_data))
        
        # Expirar historial a las 24h
        await redis_client.client.expire(history_key, 86400)
        
        # 🔥 Publicar evento al stream para el scanner
        await _publish_halt_event(halt_data, event_type)
        
        logger.info(
            "halt_state_created",
            symbol=symbol,
            reason=halt_data['halt_reason'],
            timestamp=timestamp_ms
        )
        
    elif event_type == "RESUME":
        # Buscar el halt activo para este símbolo
        existing = await redis_client.client.hget(active_key, symbol)
        
        if existing:
            halt_data = json.loads(existing)
            halt_time = halt_data.get('halt_time', 0)
            
            # Calcular duración
            duration_ms = timestamp_ms - halt_time if halt_time else 0
            duration_seconds = int(duration_ms / 1000) if duration_ms > 0 else 0
            
            # Actualizar estado
            halt_data['status'] = 'RESUMED'
            halt_data['resume_time'] = timestamp_ms
            halt_data['duration_seconds'] = duration_seconds
            
            # Actualizar en historial
            history_id = f"{symbol}:{halt_time}"
            await redis_client.client.hset(history_key, history_id, json.dumps(halt_data))
            
            # Eliminar de halts activos
            await redis_client.client.hdel(active_key, symbol)
            
            # 🔥 Publicar evento al stream para el scanner
            await _publish_halt_event(halt_data, event_type)
            
            logger.info(
                "halt_state_resumed",
                symbol=symbol,
                duration_seconds=duration_seconds,
                timestamp=timestamp_ms
            )
        else:
            # Resume sin halt previo (puede pasar si se reinició el servicio)
            logger.warning(
                "resume_without_halt",
                symbol=symbol,
                timestamp=timestamp_ms
            )


async def handle_luld(luld: PolygonLuld):
    """
    Procesa mensajes LULD (Limit Up-Limit Down) del WebSocket
    
    LULD proporciona:
    - Price bands (upper/lower limits)
    - Halt/Pause detection
    - Resume notifications
    - Limit state entries/exits
    
    Publicamos a Redis Stream + mantenemos estado de halts para:
    - Mostrar tablas de halts/resumes en tiempo real
    - Alertar sobre securities cerca de sus límites
    - Detectar volatility pauses
    
    Args:
        luld: LULD message de Polygon
    """
    try:
        # Determinar el tipo de evento para logging
        event_type = "normal"
        if luld.is_halted:
            event_type = "HALT"
            logger.warning(
                "luld_halt_detected",
                symbol=luld.sym,
                upper_band=luld.upper_band,
                lower_band=luld.lower_band,
                indicators=luld.get_indicator_names()
            )
            # Actualizar estado de halts
            await _update_halt_state(luld, event_type)
            
        elif luld.is_resuming:
            event_type = "RESUME"
            logger.info(
                "luld_resume_detected",
                symbol=luld.sym,
                upper_band=luld.upper_band,
                lower_band=luld.lower_band,
                indicators=luld.get_indicator_names()
            )
            # Actualizar estado de halts
            await _update_halt_state(luld, event_type)
            
        elif luld.is_at_lower_band or luld.is_at_upper_band:
            event_type = "LIMIT_STATE"
            logger.debug(
                "luld_limit_state",
                symbol=luld.sym,
                at_lower=luld.is_at_lower_band,
                at_upper=luld.is_at_upper_band
            )
        
        # Publicar a Redis Stream (solo eventos significativos para reducir volumen)
        if event_type in ("HALT", "RESUME", "LIMIT_STATE"):
            await redis_client.publish_to_stream(
                "stream:realtime:luld",
                {
                    'symbol': luld.sym,
                    'upper_band': str(luld.upper_band),
                    'lower_band': str(luld.lower_band),
                    'band_width_percent': str(round(luld.band_width_percent, 2)),
                    'indicators': ','.join(map(str, luld.indicators)),
                    'indicator_names': ','.join(luld.get_indicator_names()),
                    'is_halted': 'true' if luld.is_halted else 'false',
                    'is_resuming': 'true' if luld.is_resuming else 'false',
                    'is_at_lower_band': 'true' if luld.is_at_lower_band else 'false',
                    'is_at_upper_band': 'true' if luld.is_at_upper_band else 'false',
                    'event_type': event_type,
                    'timestamp': str(luld.t)
                }
            )
        
    except Exception as e:
        logger.error(
            "luld_handler_error",
            symbol=luld.sym,
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
# Catalyst Subscription Management (para Catalyst Alert Engine)
# ============================================================================

async def manage_catalyst_subscriptions():
    """
    Gestiona suscripciones temporales de AGGREGATES para el Catalyst Alert Engine.
    
    Diferente del Scanner (que usa reconciler), estas suscripciones son:
    - Temporales: solo mientras se monitorea una noticia (típicamente 3 min)
    - Sin reconciler: no hay SET de source of truth
    - Independientes: no afectan al scanner ni a quotes
    
    Stream de entrada: polygon_ws:catalyst_subscriptions
    Mensajes: {"action": "subscribe"|"unsubscribe", "symbol": "AKTX", "source": "catalyst_engine"}
    
    NOTA: Usa Aggregates (A) porque necesita precio OHLCV en tiempo real.
    """
    global catalyst_subscribed_tickers
    
    logger.info("catalyst_subscription_manager_started")
    
    # Stream de entrada para comandos de catalyst
    input_stream = "polygon_ws:catalyst_subscriptions"
    consumer_group = "polygon_ws_catalyst_group"
    consumer_name = "polygon_ws_catalyst_consumer"
    
    # Tipo de evento: Aggregates (para precio en tiempo real)
    event_types = {"A"}
    
    # Crear consumer group si no existe
    try:
        await redis_client.create_consumer_group(
            input_stream,
            consumer_group,
            mkstream=True
        )
        logger.info(f"Consumer group '{consumer_group}' created for catalyst")
    except Exception as e:
        logger.debug("catalyst_consumer_group_already_exists", error=str(e))
    
    # Track de autenticación para re-suscribir
    was_authenticated = False
    
    while True:
        try:
            # Detectar reconexión y re-suscribir a todos los tickers de catalyst
            if ws_client.is_authenticated and not was_authenticated:
                if catalyst_subscribed_tickers:
                    logger.info(
                        "re_subscribing_catalyst_after_reconnection",
                        count=len(catalyst_subscribed_tickers),
                        tickers=list(catalyst_subscribed_tickers)[:10]
                    )
                    await ws_client.subscribe_to_tickers(catalyst_subscribed_tickers, event_types)
                was_authenticated = True
            elif not ws_client.is_authenticated:
                was_authenticated = False
            
            # Leer comandos de suscripción de catalyst
            messages = await redis_client.read_stream(
                stream_name=input_stream,
                consumer_group=consumer_group,
                consumer_name=consumer_name,
                count=100,
                block=2000  # 2 segundos (más rápido para alertas)
            )
            
            if messages:
                message_ids_to_ack = []
                
                for stream_name, stream_messages in messages:
                    for message_id, data in stream_messages:
                        symbol = data.get('symbol', '').upper()
                        action = data.get('action', '').lower()
                        source = data.get('source', 'unknown')
                        
                        if not symbol or not action:
                            message_ids_to_ack.append(message_id)
                            continue
                        
                        if action == "subscribe":
                            # Solo añadir si no está ya suscrito (evitar duplicados)
                            # NOTA: No verificamos ws_client.subscribed_tickers porque
                            # el scanner podría tenerlo ya suscrito, y eso está bien
                            if symbol not in catalyst_subscribed_tickers:
                                catalyst_subscribed_tickers.add(symbol)
                                
                                # Solo suscribir en Polygon si NO está ya suscrito por el scanner
                                if ws_client.is_authenticated and symbol not in ws_client.subscribed_tickers:
                                    await ws_client.subscribe_to_tickers({symbol}, event_types)
                                    logger.info(
                                        "catalyst_ticker_subscribed",
                                        symbol=symbol,
                                        source=source,
                                        total_catalyst=len(catalyst_subscribed_tickers)
                                    )
                                else:
                                    logger.debug(
                                        "catalyst_ticker_already_subscribed_by_scanner",
                                        symbol=symbol,
                                        source=source
                                    )
                        
                        elif action == "unsubscribe":
                            if symbol in catalyst_subscribed_tickers:
                                catalyst_subscribed_tickers.discard(symbol)
                                
                                # Solo desuscribir si:
                                # 1. Estamos autenticados
                                # 2. Está suscrito en Polygon
                                # 3. NO está en las suscripciones del scanner (para no afectarlo)
                                if (ws_client.is_authenticated and 
                                    symbol in ws_client.subscribed_tickers):
                                    
                                    # Verificar si el scanner lo necesita
                                    scanner_tickers = await redis_client.client.smembers('polygon_ws:active_tickers')
                                    scanner_tickers = {t.decode() if isinstance(t, bytes) else t for t in scanner_tickers}
                                    
                                    if symbol not in scanner_tickers:
                                        await ws_client.unsubscribe_from_tickers({symbol}, event_types)
                                        logger.info(
                                            "catalyst_ticker_unsubscribed",
                                            symbol=symbol,
                                            source=source,
                                            total_catalyst=len(catalyst_subscribed_tickers)
                                        )
                                    else:
                                        logger.debug(
                                            "catalyst_ticker_kept_for_scanner",
                                            symbol=symbol,
                                            source=source
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
                        logger.error("catalyst_xack_error", error=str(e))
        
        except asyncio.CancelledError:
            logger.info("catalyst_subscription_manager_cancelled")
            raise
        
        except Exception as e:
            logger.error(
                "catalyst_subscription_manager_error",
                error=str(e),
                error_type=type(e).__name__
            )
            await asyncio.sleep(2)


async def manage_luld_subscription():
    """
    Gestiona la suscripción a LULD.* (Limit Up-Limit Down) para TODO el mercado.
    
    LULD es un stream muy ligero (~3-10 msg/s durante market hours) que proporciona:
    - Price bands (upper/lower limits) de todas las acciones
    - Detección de halts y pauses
    - Notificaciones de resume
    - Limit state entries/exits
    
    Esta tarea:
    1. Espera a que el WebSocket esté autenticado
    2. Se suscribe a LULD.*
    3. Maneja reconexiones (re-suscribe automáticamente)
    """
    global luld_subscribed
    
    logger.info("luld_subscription_manager_started")
    
    while True:
        try:
            # Esperar a que estemos autenticados
            if ws_client and ws_client.is_authenticated:
                # Si no estamos suscritos, suscribirse
                if not luld_subscribed:
                    logger.info("subscribing_to_luld_all_market")
                    success = await ws_client.subscribe_luld_all()
                    
                    if success:
                        luld_subscribed = True
                        logger.info(
                            "luld_subscription_active",
                            stream="LULD.*",
                            description="Receiving halts, resumes, and price bands for entire market"
                        )
                    else:
                        logger.warning("luld_subscription_failed_will_retry")
            
            else:
                # No estamos autenticados, resetear el flag
                if luld_subscribed:
                    logger.info("luld_subscription_lost_due_to_disconnect")
                    luld_subscribed = False
            
            # Check cada 2 segundos
            await asyncio.sleep(2)
            
        except asyncio.CancelledError:
            logger.info("luld_subscription_manager_cancelled")
            raise
        
        except Exception as e:
            logger.error(
                "luld_subscription_manager_error",
                error=str(e),
                error_type=type(e).__name__
            )
            luld_subscribed = False
            await asyncio.sleep(5)


# ============================================================================
# NASDAQ RSS Halts Poller (High-frequency, non-blocking)
# ============================================================================

async def poll_nasdaq_rss_halts():
    """
    High-frequency polling del RSS feed oficial de NASDAQ Trader.
    
    Complementa el LULD WebSocket de Polygon:
    - LULD: tiempo real pero solo NASDAQ-listed y no siempre reporta todos
    - RSS: cobertura completa de NYSE + NASDAQ, todos los tipos de halt
    
    URL: https://www.nasdaqtrader.com/rss.aspx?feed=tradehalts
    
    Polling cada 5 segundos para máxima frecuencia sin ser abusivo.
    Los datos se combinan con LULD en Redis, deduplicando por symbol:timestamp.
    """
    import aiohttp
    import xml.etree.ElementTree as ET
    from datetime import datetime
    import json
    
    logger.info("nasdaq_rss_halts_poller_started")
    
    RSS_URL = "https://www.nasdaqtrader.com/rss.aspx?feed=tradehalts"
    POLL_INTERVAL = 5  # segundos - alta frecuencia
    
    # Namespace para tags NASDAQ
    NS = {'ndaq': 'http://www.nasdaqtrader.com/'}
    
    # Track de halts ya procesados para detectar nuevos
    processed_halt_keys: set = set()
    
    # Session HTTP reutilizable (más eficiente)
    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=10),
        headers={'User-Agent': 'Tradeul/1.0'}
    ) as session:
        
        while True:
            try:
                async with session.get(RSS_URL) as response:
                    if response.status != 200:
                        logger.warning(
                            "nasdaq_rss_http_error",
                            status=response.status
                        )
                        await asyncio.sleep(POLL_INTERVAL)
                        continue
                    
                    xml_text = await response.text()
                
                # Parse XML
                root = ET.fromstring(xml_text)
                channel = root.find('channel')
                
                if channel is None:
                    await asyncio.sleep(POLL_INTERVAL)
                    continue
                
                # Obtener número total de items
                num_items_el = channel.find('ndaq:numItems', NS)
                num_items = int(num_items_el.text) if num_items_el is not None else 0
                
                today = datetime.now().strftime('%Y-%m-%d')
                halts_today = []
                new_halts_count = 0
                
                for item in channel.findall('item'):
                    # Extraer campos con namespace ndaq
                    halt_date = _get_xml_text(item, 'ndaq:HaltDate', NS, '').strip()
                    halt_time = _get_xml_text(item, 'ndaq:HaltTime', NS, '').strip()
                    symbol = _get_xml_text(item, 'ndaq:IssueSymbol', NS, '').strip()
                    issue_name = _get_xml_text(item, 'ndaq:IssueName', NS, '').strip()
                    market = _get_xml_text(item, 'ndaq:Market', NS, '').strip()
                    reason_code = _get_xml_text(item, 'ndaq:ReasonCode', NS, '').strip()
                    pause_price = _get_xml_text(item, 'ndaq:PauseThresholdPrice', NS, '').strip()
                    resume_date = _get_xml_text(item, 'ndaq:ResumptionDate', NS, '').strip()
                    resume_quote_time = _get_xml_text(item, 'ndaq:ResumptionQuoteTime', NS, '').strip()
                    resume_trade_time = _get_xml_text(item, 'ndaq:ResumptionTradeTime', NS, '').strip()
                    
                    if not symbol or not halt_date:
                        continue
                    
                    # Normalizar fecha a ISO
                    try:
                        halt_date_iso = datetime.strptime(halt_date.strip(), '%m/%d/%Y').strftime('%Y-%m-%d')
                    except:
                        halt_date_iso = halt_date
                    
                    # Solo procesar halts de hoy
                    if halt_date_iso != today:
                        continue
                    
                    # Parse timestamps
                    halt_ts = _parse_halt_datetime(halt_date, halt_time)
                    resume_ts = _parse_halt_datetime(resume_date, resume_trade_time) if resume_trade_time else None
                    
                    # Determinar status
                    is_resumed = bool(resume_trade_time and resume_trade_time.strip())
                    status = 'RESUMED' if is_resumed else 'HALTED'
                    
                    # Calcular duración si ya resumió
                    duration_seconds = None
                    if halt_ts and resume_ts:
                        duration_seconds = int((resume_ts - halt_ts) / 1000)
                    
                    # Key único para deduplicación
                    halt_key = f"{symbol}:{halt_ts}"
                    
                    halt_event = {
                        'symbol': symbol,
                        'halt_time': halt_ts,
                        'halt_reason': reason_code or 'UNKNOWN',
                        'halt_reason_desc': _get_halt_reason_desc(reason_code),
                        'status': status,
                        'resume_time': resume_ts,
                        'duration_seconds': duration_seconds,
                        'upper_band': None,
                        'lower_band': None,
                        'indicators': None,
                        'company_name': issue_name,
                        'exchange': market,
                        'source': 'nasdaq_rss',
                        'pause_threshold_price': float(pause_price) if pause_price else None,
                    }
                    
                    halts_today.append(halt_event)
                    
                    # Detectar nuevos halts para logging y publicar al stream
                    if halt_key not in processed_halt_keys:
                        processed_halt_keys.add(halt_key)
                        new_halts_count += 1
                        
                        # 🔥 Publicar evento al stream para el scanner
                        event_type = "HALT" if status == 'HALTED' else "RESUME"
                        await _publish_halt_event(halt_event, event_type)
                        
                        if status == 'HALTED':
                            logger.warning(
                                "nasdaq_rss_halt_detected",
                                symbol=symbol,
                                reason=reason_code,
                                exchange=market,
                                time=halt_time
                            )
                
                # Guardar en Redis (combina con LULD data)
                if redis_client and halts_today:
                    # Hash con historial del día - key incluye source para no pisar LULD
                    history_key = f"halts:history:{today}"
                    
                    for halt in halts_today:
                        # Key único: symbol:timestamp:source
                        entry_key = f"{halt['symbol']}:{halt['halt_time']}:rss"
                        await redis_client.client.hset(
                            history_key,
                            entry_key,
                            json.dumps(halt)
                        )
                    
                    # TTL de 24 horas
                    await redis_client.client.expire(history_key, 86400)
                    
                    # Actualizar halts activos
                    active_halts = {h['symbol']: json.dumps(h) for h in halts_today if h['status'] == 'HALTED'}
                    if active_halts:
                        await redis_client.client.hset("halts:active", mapping=active_halts)
                    
                    # Limpiar halts que ya resumieron
                    for halt in halts_today:
                        if halt['status'] == 'RESUMED':
                            await redis_client.client.hdel("halts:active", halt['symbol'])
                
                if new_halts_count > 0:
                    logger.info(
                        "nasdaq_rss_poll_complete",
                        total_today=len(halts_today),
                        new_detected=new_halts_count,
                        rss_items=num_items
                    )
                
                await asyncio.sleep(POLL_INTERVAL)
                
            except asyncio.CancelledError:
                logger.info("nasdaq_rss_halts_poller_cancelled")
                raise
            
            except ET.ParseError as e:
                logger.error(
                    "nasdaq_rss_parse_error",
                    error=str(e)
                )
                await asyncio.sleep(POLL_INTERVAL)
            
            except Exception as e:
                logger.error(
                    "nasdaq_rss_poller_error",
                    error=str(e),
                    error_type=type(e).__name__
                )
                await asyncio.sleep(POLL_INTERVAL)


def _get_xml_text(element, tag: str, namespaces: dict, default: str = '') -> str:
    """Helper para extraer texto de un elemento XML con namespace."""
    el = element.find(tag, namespaces)
    return el.text if el is not None and el.text else default


def _parse_halt_datetime(date_str: str, time_str: str) -> int:
    """Parse fecha/hora de NASDAQ RSS a timestamp en milisegundos."""
    from datetime import datetime
    
    if not date_str or not time_str:
        return 0
    
    try:
        # Formato: MM/DD/YYYY y HH:MM:SS
        dt_str = f"{date_str.strip()} {time_str.strip()}"
        dt = datetime.strptime(dt_str, '%m/%d/%Y %H:%M:%S')
        return int(dt.timestamp() * 1000)
    except:
        return 0


def _get_halt_reason_desc(code: str) -> str:
    """Obtiene descripción legible del código de halt."""
    HALT_REASONS = {
        'LUDP': 'Volatility Pause (LULD)',
        'LUDS': 'Volatility Pause (Straddle)',
        'T1': 'News Pending',
        'T2': 'News Released',
        'T3': 'News & Resumption Times',
        'T5': 'Single Stock Trading Pause',
        'T6': 'Extraordinary Activity',
        'T7': 'Quotation Only Period',
        'T8': 'ETF Halt',
        'T12': 'Information Requested',
        'H4': 'Non-Compliance',
        'H9': 'Filings Not Current',
        'H10': 'SEC Trading Suspension',
        'H11': 'Regulatory Concern',
        'MWC1': 'Market-Wide Circuit Breaker L1',
        'MWC2': 'Market-Wide Circuit Breaker L2',
        'MWC3': 'Market-Wide Circuit Breaker L3',
        'IPO1': 'IPO Not Yet Trading',
        'M1': 'Corporate Action',
        'M2': 'Quotation Not Available',
        'O1': 'Market Operations',
        'D': 'Deficient - Below Listing Requirements',
    }
    return HALT_REASONS.get(code, code or 'Unknown')


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


@app.get("/subscriptions/catalyst")
async def get_catalyst_subscriptions():
    """Obtiene las suscripciones activas de Catalyst (temporales para alertas)"""
    global catalyst_subscribed_tickers
    
    if not ws_client:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    return {
        "subscribed_tickers": list(catalyst_subscribed_tickers),
        "count": len(catalyst_subscribed_tickers),
        "is_authenticated": ws_client.is_authenticated,
        "type": "catalyst_aggregates"
    }


@app.get("/subscriptions/luld")
async def get_luld_subscription():
    """Obtiene el estado de la suscripción a LULD (Limit Up-Limit Down)"""
    global luld_subscribed
    
    if not ws_client:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    stats = ws_client.get_stats()
    
    return {
        "subscribed": luld_subscribed,
        "stream": "LULD.*" if luld_subscribed else None,
        "is_authenticated": ws_client.is_authenticated,
        "type": "luld_all_market",
        "stats": {
            "luld_received": stats.get("luld_received", 0),
            "luld_halts": stats.get("luld_halts", 0),
            "luld_resumes": stats.get("luld_resumes", 0)
        },
        "description": "Limit Up-Limit Down price bands, halts, and resumes for entire market"
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
# Halts Endpoints
# ============================================================================

@app.get("/halts/active")
async def get_active_halts():
    """
    Obtiene los halts activos actualmente (tickers que están halted ahora mismo).
    
    Returns:
        Lista de halts activos con todos los detalles
    """
    import json
    
    if not redis_client:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    try:
        active_key = "halts:active"
        raw_halts = await redis_client.client.hgetall(active_key)
        
        halts = []
        for symbol, data_bytes in raw_halts.items():
            symbol_str = symbol.decode() if isinstance(symbol, bytes) else symbol
            data_str = data_bytes.decode() if isinstance(data_bytes, bytes) else data_bytes
            halt_data = json.loads(data_str)
            halt_data['symbol'] = symbol_str
            halts.append(halt_data)
        
        # Ordenar por halt_time (más reciente primero)
        halts.sort(key=lambda x: x.get('halt_time', 0), reverse=True)
        
        return {
            "halts": halts,
            "count": len(halts),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error("get_active_halts_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/halts/history")
async def get_halts_history(date: Optional[str] = None):
    """
    Obtiene el historial de halts del día (combinando LULD WebSocket + NASDAQ RSS).
    
    Fuentes combinadas:
    - LULD WebSocket: tiempo real de Polygon (NASDAQ-listed)
    - NASDAQ RSS: feed oficial de alta frecuencia (NYSE + NASDAQ completo)
    
    Los datos se deduplicar por symbol + timestamp para evitar duplicados.
    
    Args:
        date: Fecha en formato YYYY-MM-DD (opcional, default: hoy)
    
    Returns:
        Lista completa de halts del día con sus estados
    """
    import json
    
    if not redis_client:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    try:
        # Usar fecha proporcionada o fecha actual
        target_date = date or datetime.now().strftime('%Y-%m-%d')
        
        # Leer del historial combinado (LULD + RSS)
        history_key = f"halts:history:{target_date}"
        raw_history = await redis_client.client.hgetall(history_key)
        
        # Deduplicar por symbol:halt_time (RSS tiene prioridad por ser más completo)
        halt_map = {}  # key: "symbol:halt_time" -> halt_data
        
        for history_id, data_bytes in raw_history.items():
            history_id_str = history_id.decode() if isinstance(history_id, bytes) else history_id
            data_str = data_bytes.decode() if isinstance(data_bytes, bytes) else data_bytes
            halt_data = json.loads(data_str)
            
            symbol = halt_data.get('symbol', '')
            halt_time = halt_data.get('halt_time', 0)
            source = halt_data.get('source', 'luld')
            
            # Key para deduplicación (sin la fuente)
            dedup_key = f"{symbol}:{halt_time}"
            
            # Si ya existe, preferir RSS sobre LULD (más completo)
            if dedup_key in halt_map:
                existing_source = halt_map[dedup_key].get('source', 'luld')
                if source == 'nasdaq_rss' and existing_source == 'luld':
                    halt_map[dedup_key] = halt_data
            else:
                halt_map[dedup_key] = halt_data
        
        halts = list(halt_map.values())
        
        # Ordenar por halt_time (más reciente primero)
        halts.sort(key=lambda x: x.get('halt_time', 0), reverse=True)
        
        # Estadísticas por fuente
        total_halts = len(halts)
        active_halts = sum(1 for h in halts if h.get('status') == 'HALTED')
        resumed_halts = sum(1 for h in halts if h.get('status') == 'RESUMED')
        from_rss = sum(1 for h in halts if h.get('source') == 'nasdaq_rss')
        from_luld = sum(1 for h in halts if h.get('source', 'luld') == 'luld')
        
        return {
            "date": target_date,
            "halts": halts,
            "stats": {
                "total": total_halts,
                "active": active_halts,
                "resumed": resumed_halts,
                "sources": {
                    "nasdaq_rss": from_rss,
                    "luld_websocket": from_luld
                }
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error("get_halts_history_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/halts/{symbol}")
async def get_halt_status(symbol: str):
    """
    Obtiene el estado de halt de un ticker específico.
    
    Args:
        symbol: Símbolo del ticker
    
    Returns:
        Estado actual de halt (si existe)
    """
    import json
    
    if not redis_client:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    try:
        symbol_upper = symbol.upper()
        active_key = "halts:active"
        
        raw_data = await redis_client.client.hget(active_key, symbol_upper)
        
        if raw_data:
            data_str = raw_data.decode() if isinstance(raw_data, bytes) else raw_data
            halt_data = json.loads(data_str)
            return {
                "symbol": symbol_upper,
                "is_halted": True,
                "halt_data": halt_data,
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {
                "symbol": symbol_upper,
                "is_halted": False,
                "halt_data": None,
                "timestamp": datetime.now().isoformat()
            }
        
    except Exception as e:
        logger.error("get_halt_status_error", symbol=symbol, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


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

