"""
WebSocket Router for Job Notifications
======================================
Maneja conexiones WebSocket para notificaciones en tiempo real
cuando los jobs de scraping completan.
"""

import asyncio
import json
from typing import Dict, Set
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import redis.asyncio as aioredis

from shared.config.settings import settings
from shared.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["websocket"])


class ConnectionManager:
    """
    Gestiona conexiones WebSocket activas.
    Soporta suscripción a tickers específicos.
    """
    
    def __init__(self):
        # ticker -> set de WebSockets suscritos
        self.subscriptions: Dict[str, Set[WebSocket]] = {}
        # WebSocket -> set de tickers a los que está suscrito
        self.connections: Dict[WebSocket, Set[str]] = {}
        self._pubsub_task = None
        self._redis = None
    
    async def connect(self, websocket: WebSocket) -> None:
        """Acepta una nueva conexión WebSocket."""
        await websocket.accept()
        self.connections[websocket] = set()
        logger.info("websocket_connected", total_connections=len(self.connections))
    
    def disconnect(self, websocket: WebSocket) -> None:
        """Maneja desconexión de WebSocket."""
        # Remover de todas las suscripciones
        if websocket in self.connections:
            for ticker in self.connections[websocket]:
                if ticker in self.subscriptions:
                    self.subscriptions[ticker].discard(websocket)
                    if not self.subscriptions[ticker]:
                        del self.subscriptions[ticker]
            del self.connections[websocket]
        
        logger.info("websocket_disconnected", total_connections=len(self.connections))
    
    async def subscribe(self, websocket: WebSocket, ticker: str) -> None:
        """Suscribe un WebSocket a notificaciones de un ticker."""
        ticker = ticker.upper()
        
        if ticker not in self.subscriptions:
            self.subscriptions[ticker] = set()
        
        self.subscriptions[ticker].add(websocket)
        
        if websocket in self.connections:
            self.connections[websocket].add(ticker)
        
        logger.debug("websocket_subscribed", ticker=ticker)
    
    async def unsubscribe(self, websocket: WebSocket, ticker: str) -> None:
        """Cancela suscripción de un WebSocket a un ticker."""
        ticker = ticker.upper()
        
        if ticker in self.subscriptions:
            self.subscriptions[ticker].discard(websocket)
            if not self.subscriptions[ticker]:
                del self.subscriptions[ticker]
        
        if websocket in self.connections:
            self.connections[websocket].discard(ticker)
        
        logger.debug("websocket_unsubscribed", ticker=ticker)
    
    async def notify_ticker(self, ticker: str, data: dict) -> None:
        """Notifica a todos los WebSockets suscritos a un ticker."""
        ticker = ticker.upper()
        
        if ticker not in self.subscriptions:
            return
        
        message = json.dumps({
            "type": "job_complete",
            "ticker": ticker,
            "data": data,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        dead_connections = []
        
        for websocket in self.subscriptions[ticker]:
            try:
                await websocket.send_text(message)
            except Exception as e:
                logger.warning("websocket_send_failed", error=str(e))
                dead_connections.append(websocket)
        
        # Limpiar conexiones muertas
        for ws in dead_connections:
            self.disconnect(ws)
    
    async def broadcast(self, data: dict) -> None:
        """Envía mensaje a TODAS las conexiones activas."""
        message = json.dumps(data)
        
        dead_connections = []
        
        for websocket in self.connections.keys():
            try:
                await websocket.send_text(message)
            except Exception:
                dead_connections.append(websocket)
        
        for ws in dead_connections:
            self.disconnect(ws)
    
    async def start_pubsub_listener(self) -> None:
        """
        Inicia listener de Redis Pub/Sub para recibir notificaciones
        de jobs completados y reenviarlas a WebSockets.
        """
        if self._pubsub_task is not None:
            return  # Ya está corriendo
        
        self._redis = await aioredis.from_url(
            f"redis://:{settings.redis_password}@{settings.REDIS_HOST}:{settings.REDIS_PORT}/0",
            encoding="utf-8",
            decode_responses=True
        )
        
        pubsub = self._redis.pubsub()
        await pubsub.subscribe("dilution:job:complete")
        
        logger.info("pubsub_listener_started", channel="dilution:job:complete")
        
        async def listener():
            try:
                async for message in pubsub.listen():
                    if message["type"] == "message":
                        try:
                            data = json.loads(message["data"])
                            ticker = data.get("ticker")
                            if ticker:
                                await self.notify_ticker(ticker, data.get("result", {}))
                        except json.JSONDecodeError:
                            continue
            except asyncio.CancelledError:
                await pubsub.unsubscribe("dilution:job:complete")
                await self._redis.close()
                logger.info("pubsub_listener_stopped")
        
        self._pubsub_task = asyncio.create_task(listener())
    
    async def stop_pubsub_listener(self) -> None:
        """Detiene el listener de Pub/Sub."""
        if self._pubsub_task:
            self._pubsub_task.cancel()
            try:
                await self._pubsub_task
            except asyncio.CancelledError:
                pass
            self._pubsub_task = None


# Instancia global del manager
manager = ConnectionManager()


@router.websocket("/ws/jobs")
async def websocket_job_notifications(websocket: WebSocket):
    """
    WebSocket para recibir notificaciones de jobs completados.
    
    **Protocolo:**
    
    1. Cliente envía mensaje de suscripción:
    ```json
    {"action": "subscribe", "ticker": "MULN"}
    ```
    
    2. Cliente puede suscribirse a múltiples tickers
    
    3. Cuando un job completa, cliente recibe:
    ```json
    {
        "type": "job_complete",
        "ticker": "MULN",
        "data": {
            "status": "completed",
            "has_warrants": true,
            "has_atm": true,
            "duration_seconds": 45.2
        },
        "timestamp": "2024-01-15T10:31:30Z"
    }
    ```
    
    4. Cliente puede cancelar suscripción:
    ```json
    {"action": "unsubscribe", "ticker": "MULN"}
    ```
    
    **Ejemplo JavaScript:**
    ```javascript
    const ws = new WebSocket('wss://dilution.tradeul.com/ws/jobs');
    
    ws.onopen = () => {
        ws.send(JSON.stringify({ action: 'subscribe', ticker: 'MULN' }));
    };
    
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'job_complete') {
            console.log(`${data.ticker} analysis ready!`);
            // Refresh UI or show notification
        }
    };
    ```
    """
    await manager.connect(websocket)
    
    # Asegurar que el listener de Pub/Sub está corriendo
    await manager.start_pubsub_listener()
    
    try:
        while True:
            # Recibir mensajes del cliente
            data = await websocket.receive_text()
            
            try:
                message = json.loads(data)
                action = message.get("action")
                ticker = message.get("ticker", "").upper()
                
                if action == "subscribe" and ticker:
                    await manager.subscribe(websocket, ticker)
                    await websocket.send_text(json.dumps({
                        "type": "subscribed",
                        "ticker": ticker
                    }))
                    
                elif action == "unsubscribe" and ticker:
                    await manager.unsubscribe(websocket, ticker)
                    await websocket.send_text(json.dumps({
                        "type": "unsubscribed",
                        "ticker": ticker
                    }))
                    
                elif action == "ping":
                    await websocket.send_text(json.dumps({
                        "type": "pong",
                        "timestamp": datetime.utcnow().isoformat()
                    }))
                    
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "Invalid JSON"
                }))
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error("websocket_error", error=str(e))
        manager.disconnect(websocket)

