"""
Polygon WebSocket Client

Cliente asíncrono para conectar al WebSocket de Polygon y manejar:
- Autenticación
- Suscripciones dinámicas
- Reconexión automática
- Procesamiento de mensajes
"""

import asyncio
import json
from datetime import datetime
from typing import Set, Optional, Callable, Dict, Any
import structlog
import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from shared.config.settings import settings
from shared.models.polygon import PolygonTrade, PolygonQuote, PolygonAgg

logger = structlog.get_logger(__name__)


class PolygonWebSocketClient:
    """
    Cliente WebSocket para Polygon
    
    Maneja conexión, autenticación, suscripciones y reconexión automática.
    """
    
    # WebSocket URL de Polygon
    WS_URL = "wss://socket.polygon.io/stocks"
    
    # Tipos de eventos soportados
    EVENT_TRADE = "T"
    EVENT_QUOTE = "Q"
    EVENT_AGGREGATE = "A"
    
    def __init__(
        self,
        api_key: str,
        on_trade: Optional[Callable] = None,
        on_quote: Optional[Callable] = None,
        on_aggregate: Optional[Callable] = None,
        max_reconnect_attempts: int = 10,
        reconnect_delay: int = 5
    ):
        """
        Inicializa el cliente WebSocket
        
        Args:
            api_key: API key de Polygon
            on_trade: Callback para trades
            on_quote: Callback para quotes
            on_aggregate: Callback para aggregates
            max_reconnect_attempts: Intentos máximos de reconexión
            reconnect_delay: Delay entre intentos (segundos)
        """
        self.api_key = api_key
        self.on_trade = on_trade
        self.on_quote = on_quote
        self.on_aggregate = on_aggregate
        self.max_reconnect_attempts = max_reconnect_attempts
        self.reconnect_delay = reconnect_delay
        
        # Estado de la conexión
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.is_connected = False
        self.is_authenticated = False
        
        # Suscripciones activas
        self.subscribed_tickers: Set[str] = set()
        
        # Control de reconexión
        self.reconnect_attempts = 0
        self.should_reconnect = True
        
        # Estadísticas
        self.stats = {
            "trades_received": 0,
            "quotes_received": 0,
            "aggregates_received": 0,
            "errors": 0,
            "reconnections": 0,
            "last_message_time": None
        }
        
        logger.info("polygon_ws_client_initialized")
    
    async def connect(self):
        """
        Conecta al WebSocket de Polygon
        
        Maneja autenticación y reconexión automática.
        """
        while self.should_reconnect:
            try:
                logger.info("connecting_to_polygon_ws", url=self.WS_URL)
                
                # Conectar al WebSocket
                self.ws = await websockets.connect(
                    self.WS_URL,
                    ping_interval=30,
                    ping_timeout=10,
                    close_timeout=10
                )
                
                self.is_connected = True
                self.reconnect_attempts = 0
                
                logger.info("connected_to_polygon_ws")
                
                # Autenticar
                await self._authenticate()
                
                # Procesar mensajes
                await self._process_messages()
                
            except ConnectionClosed as e:
                logger.warning(
                    "connection_closed",
                    code=e.code,
                    reason=e.reason
                )
                await self._handle_reconnection()
                
            except WebSocketException as e:
                logger.error(
                    "websocket_error",
                    error=str(e),
                    error_type=type(e).__name__
                )
                await self._handle_reconnection()
                
            except Exception as e:
                logger.error(
                    "unexpected_error",
                    error=str(e),
                    error_type=type(e).__name__
                )
                self.stats["errors"] += 1
                await self._handle_reconnection()
    
    async def _authenticate(self):
        """Autentica con el servidor de Polygon"""
        auth_message = {
            "action": "auth",
            "params": self.api_key
        }
        
        await self.ws.send(json.dumps(auth_message))
        
        # Esperar respuesta de autenticación
        response = await self.ws.recv()
        response_data = json.loads(response)
        
        # Polygon puede responder con "auth_success" o "connected"
        if response_data[0].get("status") in ["auth_success", "connected", "success"]:
            self.is_authenticated = True
            logger.info("authenticated_successfully", response=response_data[0])
        else:
            logger.error("authentication_failed", response=response_data)
            raise Exception("Failed to authenticate with Polygon WebSocket")
    
    async def _process_messages(self):
        """
        Procesa mensajes entrantes del WebSocket
        
        Maneja Trades, Quotes y Aggregates.
        """
        async for message in self.ws:
            try:
                # Parsear mensaje
                data = json.loads(message)
                
                if not isinstance(data, list):
                    continue
                
                # Procesar cada evento
                for event in data:
                    ev_type = event.get("ev")
                    
                    if ev_type == self.EVENT_TRADE:
                        await self._handle_trade(event)
                    
                    elif ev_type == self.EVENT_QUOTE:
                        await self._handle_quote(event)
                    
                    elif ev_type == self.EVENT_AGGREGATE:
                        await self._handle_aggregate(event)
                    
                    elif ev_type == "status":
                        logger.debug("status_message", message=event.get("message"))
                    
                # Actualizar timestamp del último mensaje
                self.stats["last_message_time"] = datetime.now().isoformat()
                
            except json.JSONDecodeError as e:
                logger.error("json_decode_error", error=str(e), message=message)
                self.stats["errors"] += 1
                
            except Exception as e:
                logger.error(
                    "message_processing_error",
                    error=str(e),
                    error_type=type(e).__name__
                )
                self.stats["errors"] += 1
    
    async def _handle_trade(self, data: Dict[str, Any]):
        """Procesa un mensaje de Trade"""
        try:
            trade = PolygonTrade(**data)
            self.stats["trades_received"] += 1
            
            if self.on_trade:
                await self.on_trade(trade)
                
        except Exception as e:
            logger.error("trade_processing_error", error=str(e), data=data)
            self.stats["errors"] += 1
    
    async def _handle_quote(self, data: Dict[str, Any]):
        """Procesa un mensaje de Quote"""
        try:
            quote = PolygonQuote(**data)
            self.stats["quotes_received"] += 1
            
            if self.on_quote:
                await self.on_quote(quote)
                
        except Exception as e:
            logger.error("quote_processing_error", error=str(e), data=data)
            self.stats["errors"] += 1
    
    async def _handle_aggregate(self, data: Dict[str, Any]):
        """Procesa un mensaje de Aggregate"""
        try:
            aggregate = PolygonAgg(**data)
            self.stats["aggregates_received"] += 1
            
            if self.on_aggregate:
                await self.on_aggregate(aggregate)
                
        except Exception as e:
            logger.error("aggregate_processing_error", error=str(e), data=data)
            self.stats["errors"] += 1
    
    async def subscribe_to_tickers(self, tickers: Set[str], event_types: Set[str]):
        """
        Suscribe a uno o más tickers
        
        Args:
            tickers: Set de símbolos (ej: {"AAPL", "TSLA"})
            event_types: Set de tipos de eventos (ej: {"T", "Q", "A"})
        """
        if not self.is_authenticated:
            logger.warning("not_authenticated_cannot_subscribe")
            return
        
        # Construir mensaje de suscripción
        # Formato: "T.AAPL,Q.AAPL,A.AAPL,T.TSLA,Q.TSLA,A.TSLA"
        subscriptions = []
        for ticker in tickers:
            for event_type in event_types:
                subscriptions.append(f"{event_type}.{ticker}")
        
        subscribe_message = {
            "action": "subscribe",
            "params": ",".join(subscriptions)
        }
        
        await self.ws.send(json.dumps(subscribe_message))
        
        # Actualizar suscripciones activas
        self.subscribed_tickers.update(tickers)
        
        logger.info(
            "subscribed_to_tickers",
            tickers_count=len(tickers),
            event_types=list(event_types),
            total_subscriptions=len(subscriptions)
        )
    
    async def unsubscribe_from_tickers(self, tickers: Set[str], event_types: Set[str]):
        """
        Desuscribe de uno o más tickers
        
        Args:
            tickers: Set de símbolos a desuscribir
            event_types: Set de tipos de eventos
        """
        if not self.is_authenticated:
            logger.warning("not_authenticated_cannot_unsubscribe")
            return
        
        # Construir mensaje de desuscripción
        unsubscriptions = []
        for ticker in tickers:
            for event_type in event_types:
                unsubscriptions.append(f"{event_type}.{ticker}")
        
        unsubscribe_message = {
            "action": "unsubscribe",
            "params": ",".join(unsubscriptions)
        }
        
        await self.ws.send(json.dumps(unsubscribe_message))
        
        # Actualizar suscripciones activas
        self.subscribed_tickers.difference_update(tickers)
        
        logger.info(
            "unsubscribed_from_tickers",
            tickers_count=len(tickers),
            event_types=list(event_types)
        )
    
    async def update_subscriptions(self, new_tickers: Set[str], event_types: Set[str]):
        """
        Actualiza suscripciones dinámicamente
        
        Desuscribe de tickers antiguos y suscribe a nuevos.
        
        Args:
            new_tickers: Nuevo set de tickers
            event_types: Tipos de eventos
        """
        # Calcular diferencias
        to_unsubscribe = self.subscribed_tickers - new_tickers
        to_subscribe = new_tickers - self.subscribed_tickers
        
        # Desuscribir de tickers antiguos
        if to_unsubscribe:
            await self.unsubscribe_from_tickers(to_unsubscribe, event_types)
        
        # Suscribir a nuevos tickers
        if to_subscribe:
            await self.subscribe_to_tickers(to_subscribe, event_types)
        
        logger.info(
            "subscriptions_updated",
            unsubscribed=len(to_unsubscribe),
            subscribed=len(to_subscribe),
            total_active=len(self.subscribed_tickers)
        )
    
    async def _handle_reconnection(self):
        """Maneja la lógica de reconexión"""
        self.is_connected = False
        self.is_authenticated = False
        
        if self.reconnect_attempts >= self.max_reconnect_attempts:
            logger.error(
                "max_reconnect_attempts_reached",
                attempts=self.reconnect_attempts
            )
            self.should_reconnect = False
            return
        
        self.reconnect_attempts += 1
        self.stats["reconnections"] += 1
        
        delay = self.reconnect_delay * self.reconnect_attempts
        logger.info(
            "reconnecting",
            attempt=self.reconnect_attempts,
            delay_seconds=delay
        )
        
        await asyncio.sleep(delay)
    
    async def close(self):
        """Cierra la conexión del WebSocket"""
        self.should_reconnect = False
        
        if self.ws and not self.ws.closed:
            await self.ws.close()
        
        self.is_connected = False
        self.is_authenticated = False
        
        logger.info("websocket_closed")
    
    def get_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas del cliente"""
        return {
            **self.stats,
            "is_connected": self.is_connected,
            "is_authenticated": self.is_authenticated,
            "subscribed_tickers_count": len(self.subscribed_tickers),
            "reconnect_attempts": self.reconnect_attempts
        }

