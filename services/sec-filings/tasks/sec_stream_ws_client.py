"""
SEC Stream API WebSocket Client

Cliente asíncrono para conectar al WebSocket de SEC Stream API y manejar:
- Autenticación
- Reconexión automática
- Procesamiento de filings en tiempo real
- Publicación a Redis streams
"""

import asyncio
import json
from datetime import datetime
from typing import Optional, Dict, Any, Callable
import structlog
import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

logger = structlog.get_logger(__name__)


class SECStreamWebSocketClient:
    """
    Cliente WebSocket para SEC Stream API
    
    Maneja conexión, autenticación, reconexión automática y procesamiento
    de filings en tiempo real.
    """
    
    def __init__(
        self,
        api_key: str,
        stream_url: str = "wss://stream.sec-api.io",
        on_filing: Optional[Callable] = None,
        max_reconnect_attempts: int = 10,
        reconnect_delay: int = 5,
        ping_timeout: int = 30
    ):
        """
        Inicializa el cliente WebSocket
        
        Args:
            api_key: SEC API key
            stream_url: URL base del WebSocket
            on_filing: Callback para cada filing recibido
            max_reconnect_attempts: Intentos máximos de reconexión
            reconnect_delay: Delay entre intentos (segundos)
            ping_timeout: Timeout para ping/pong (segundos)
        """
        self.api_key = api_key
        self.stream_url = f"{stream_url}?apiKey={api_key}"
        self.on_filing = on_filing
        self.max_reconnect_attempts = max_reconnect_attempts
        self.reconnect_delay = reconnect_delay
        self.ping_timeout = ping_timeout
        
        # Estado de la conexión
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.is_connected = False
        
        # Control de reconexión
        self.reconnect_attempts = 0
        self.should_reconnect = True
        
        # Estadísticas
        self.stats = {
            "filings_received": 0,
            "errors": 0,
            "reconnections": 0,
            "last_message_time": None,
            "connected_at": None,
            "uptime_seconds": 0
        }
        
        logger.info("sec_stream_ws_client_initialized")
    
    async def connect(self):
        """
        Conecta al WebSocket de SEC Stream API
        
        Maneja reconexión automática y ping/pong para keepalive.
        """
        while self.should_reconnect:
            try:
                logger.info("connecting_to_sec_stream_ws", url="wss://stream.sec-api.io")
                
                # Conectar al WebSocket
                # SEC Stream requiere que respondamos a ping con pong
                self.ws = await websockets.connect(
                    self.stream_url,
                    ping_interval=None,  # No auto ping (SEC maneja esto)
                    ping_timeout=self.ping_timeout,
                    close_timeout=10
                )
                
                self.is_connected = True
                self.reconnect_attempts = 0
                self.stats["connected_at"] = datetime.now().isoformat()
                
                logger.info("✅ Connected to SEC Stream API WebSocket")
                
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
    
    async def _process_messages(self):
        """
        Procesa mensajes entrantes del WebSocket
        
        SEC Stream envía:
        - Mensajes de filings (JSON array stringificado)
        - Pings (cada 25 segundos)
        """
        async for message in self.ws:
            try:
                # SEC Stream envía mensajes de texto (JSON stringificado)
                if isinstance(message, str):
                    await self._handle_filing_message(message)
                
                # Manejar pings (SEC requiere pong en 5 segundos)
                elif isinstance(message, bytes):
                    # websockets library maneja ping/pong automáticamente
                    pass
                
                # Actualizar timestamp del último mensaje
                self.stats["last_message_time"] = datetime.now().isoformat()
                
            except json.JSONDecodeError as e:
                logger.error("json_decode_error", error=str(e), message=message[:200])
                self.stats["errors"] += 1
                
            except Exception as e:
                logger.error(
                    "message_processing_error",
                    error=str(e),
                    error_type=type(e).__name__
                )
                self.stats["errors"] += 1
    
    async def _handle_filing_message(self, message: str):
        """
        Procesa un mensaje de filing
        
        Args:
            message: JSON array stringificado con filings
        """
        try:
            # Parsear mensaje: es un array de filings
            filings_data = json.loads(message)
            
            if not isinstance(filings_data, list):
                logger.warning("unexpected_message_format", message=message[:200])
                return
            
            # Procesar cada filing
            for filing_data in filings_data:
                await self._handle_filing(filing_data)
            
            self.stats["filings_received"] += len(filings_data)
            
            logger.info(
                "📄 SEC filings received",
                count=len(filings_data),
                total_received=self.stats["filings_received"]
            )
            
        except Exception as e:
            logger.error("filing_message_error", error=str(e))
            self.stats["errors"] += 1
    
    async def _handle_filing(self, filing_data: Dict[str, Any]):
        """
        Procesa un filing individual
        
        Args:
            filing_data: Datos del filing
        """
        try:
            # Extraer campos clave
            accession_no = filing_data.get("accessionNo", "N/A")
            ticker = filing_data.get("ticker")
            form_type = filing_data.get("formType", "N/A")
            company_name = filing_data.get("companyName", "N/A")
            filed_at = filing_data.get("filedAt", "N/A")
            
            logger.debug(
                "📋 Filing received",
                accession_no=accession_no,
                ticker=ticker or "N/A",
                form_type=form_type,
                company=company_name[:40]
            )
            
            # Llamar callback si está definido
            if self.on_filing:
                await self.on_filing(filing_data)
                
        except Exception as e:
            logger.error("filing_processing_error", error=str(e), filing_data=filing_data)
            self.stats["errors"] += 1
    
    async def _handle_reconnection(self):
        """Maneja la lógica de reconexión"""
        self.is_connected = False
        
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
            "reconnecting_to_sec_stream",
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
        
        logger.info("sec_stream_websocket_closed")
    
    def get_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas del cliente"""
        return {
            **self.stats,
            "is_connected": self.is_connected,
            "reconnect_attempts": self.reconnect_attempts
        }



