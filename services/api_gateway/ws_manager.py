"""
WebSocket Connection Manager

Maneja las conexiones WebSocket y las suscripciones de tickers
"""

import structlog
from typing import Dict, Set
from fastapi import WebSocket

logger = structlog.get_logger(__name__)


class ConnectionManager:
    """
    Maneja conexiones WebSocket y suscripciones de clientes
    """
    
    def __init__(self):
        # connection_id -> WebSocket
        self.active_connections: Dict[str, WebSocket] = {}
        
        # connection_id -> Set[symbol]
        # Usa "*" para indicar suscripción a todos los tickers
        self.subscriptions: Dict[str, Set[str]] = {}
    
    async def connect(self, websocket: WebSocket, connection_id: str):
        """Acepta una nueva conexión WebSocket"""
        await websocket.accept()
        self.active_connections[connection_id] = websocket
        self.subscriptions[connection_id] = set()
        
        logger.info(
            "client_connected",
            connection_id=connection_id,
            active_connections=len(self.active_connections)
        )
    
    def disconnect(self, connection_id: str):
        """Desconecta un cliente"""
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]
        
        if connection_id in self.subscriptions:
            del self.subscriptions[connection_id]
        
        logger.info(
            "client_disconnected",
            connection_id=connection_id,
            active_connections=len(self.active_connections)
        )
    
    def subscribe(self, connection_id: str, symbols: Set[str]):
        """Suscribe un cliente a uno o más símbolos"""
        if connection_id in self.subscriptions:
            self.subscriptions[connection_id].update(symbols)
            
            logger.info(
                "client_subscribed",
                connection_id=connection_id,
                symbols=list(symbols),
                total_subscriptions=len(self.subscriptions[connection_id])
            )
    
    def unsubscribe(self, connection_id: str, symbols: Set[str]):
        """Desuscribe un cliente de uno o más símbolos"""
        if connection_id in self.subscriptions:
            self.subscriptions[connection_id] -= symbols
            
            logger.info(
                "client_unsubscribed",
                connection_id=connection_id,
                symbols=list(symbols),
                total_subscriptions=len(self.subscriptions[connection_id])
            )
    
    async def send_personal_message(self, message: dict, connection_id: str):
        """Envía un mensaje a un cliente específico"""
        if connection_id in self.active_connections:
            try:
                websocket = self.active_connections[connection_id]
                await websocket.send_json(message)
            except Exception as e:
                logger.error(
                    "send_message_error",
                    connection_id=connection_id,
                    error=str(e)
                )
                # Opcional: desconectar si hay error persistente
                self.disconnect(connection_id)
    
    async def broadcast_to_subscribers(self, message: dict, symbol: str):
        """
        Envía un mensaje a todos los clientes suscritos a un símbolo específico
        
        Args:
            message: El mensaje a enviar (dict con type, symbol, data, etc.)
            symbol: El símbolo del ticker (ej: "AAPL")
        """
        disconnected = []
        sent_count = 0
        
        for connection_id, subscribed_symbols in self.subscriptions.items():
            # Enviar si está suscrito al símbolo específico o a todos ("*")
            if "*" in subscribed_symbols or symbol in subscribed_symbols:
                if connection_id in self.active_connections:
                    try:
                        websocket = self.active_connections[connection_id]
                        await websocket.send_json(message)
                        sent_count += 1
                    except Exception as e:
                        logger.error(
                            "broadcast_error",
                            connection_id=connection_id,
                            symbol=symbol,
                            error=str(e)
                        )
                        disconnected.append(connection_id)
        
        # Limpiar conexiones muertas
        for connection_id in disconnected:
            self.disconnect(connection_id)
        
        # Log solo si se envió a alguien (para no saturar logs)
        if sent_count > 0:
            logger.debug(
                "message_broadcasted",
                symbol=symbol,
                message_type=message.get("type"),
                sent_to=sent_count
            )
    
    async def broadcast_to_all(self, message: dict):
        """Envía un mensaje a todos los clientes conectados"""
        disconnected = []
        
        for connection_id, websocket in self.active_connections.items():
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(
                    "broadcast_all_error",
                    connection_id=connection_id,
                    error=str(e)
                )
                disconnected.append(connection_id)
        
        # Limpiar conexiones muertas
        for connection_id in disconnected:
            self.disconnect(connection_id)
        
        logger.debug(
            "message_broadcast_to_all",
            message_type=message.get("type"),
            total_connections=len(self.active_connections)
        )
    
    def get_stats(self) -> dict:
        """Retorna estadísticas de las conexiones"""
        total_subscriptions = sum(len(subs) for subs in self.subscriptions.values())
        subscribed_all_count = sum(1 for subs in self.subscriptions.values() if "*" in subs)
        
        return {
            "active_connections": len(self.active_connections),
            "total_subscriptions": total_subscriptions,
            "subscribed_to_all": subscribed_all_count
        }

