"""
Event Bus - Sistema centralizado de eventos para coordinación entre servicios

Usa Redis Pub/Sub para notificaciones en tiempo real cuando:
- Cambia el día de trading
- Cambia la sesión de mercado (pre-market, open, post-market, closed)
- Se completan actualizaciones de datos
"""

from enum import Enum
from typing import Optional, Dict, Any, Callable, Awaitable
from datetime import datetime
import json
import asyncio

from ..utils.redis_client import RedisClient
from ..utils.logger import get_logger

logger = get_logger(__name__)


class EventType(str, Enum):
    """Tipos de eventos del sistema"""
    
    # Eventos de sesión de mercado
    SESSION_CHANGED = "session:changed"
    DAY_CHANGED = "day:changed"
    MARKET_OPENED = "market:opened"
    MARKET_CLOSED = "market:closed"
    
    # Eventos de datos
    DATA_WARMUP_COMPLETED = "data:warmup:completed"
    UNIVERSE_UPDATED = "data:universe:updated"
    SLOTS_SAVED = "data:slots:saved"
    
    # Eventos de servicios
    SERVICE_STARTED = "service:started"
    SERVICE_STOPPED = "service:stopped"

    # Eventos de solicitud de datos (AI Agent)
    DATA_REQUEST = "data:request"           # Solicitud de ingesta de datos
    DATA_REQUEST_COMPLETED = "data:request:completed"  # Datos disponibles
    DATA_REQUEST_FAILED = "data:request:failed"        # Falló la ingesta


class Event:
    """Representa un evento del sistema"""
    
    def __init__(
        self,
        event_type: EventType,
        data: Optional[Dict[str, Any]] = None,
        timestamp: Optional[datetime] = None
    ):
        self.event_type = event_type
        self.data = data or {}
        self.timestamp = timestamp or datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte el evento a diccionario para serialización"""
        return {
            'event_type': self.event_type.value,
            'data': self.data,
            'timestamp': self.timestamp.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Event':
        """Crea un evento desde un diccionario"""
        return cls(
            event_type=EventType(data['event_type']),
            data=data.get('data', {}),
            timestamp=datetime.fromisoformat(data['timestamp'])
        )
    
    def to_json(self) -> str:
        """Serializa el evento a JSON"""
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_json(cls, json_str: str) -> 'Event':
        """Deserializa un evento desde JSON"""
        data = json.loads(json_str)
        return cls.from_dict(data)


EventHandler = Callable[[Event], Awaitable[None]]


class EventBus:
    """
    Bus de eventos centralizado usando Redis Pub/Sub
    
    Permite a los servicios:
    - Publicar eventos cuando ocurren cambios importantes
    - Suscribirse a eventos para reaccionar automáticamente
    - Coordinación automática entre servicios
    """
    
    def __init__(self, redis_client: RedisClient, service_name: str):
        """
        Inicializa el event bus
        
        Args:
            redis_client: Cliente de Redis
            service_name: Nombre del servicio (para logging)
        """
        self.redis = redis_client
        self.service_name = service_name
        self.handlers: Dict[EventType, list[EventHandler]] = {}
        self.pubsub: Optional[Any] = None
        self.listener_task: Optional[asyncio.Task] = None
    
    async def publish(self, event: Event) -> None:
        """
        Publica un evento al bus
        
        Args:
            event: Evento a publicar
        """
        try:
            channel = f"events:{event.event_type.value}"
            await self.redis.client.publish(channel, event.to_json())
            
            logger.info(
                "event_published",
                service=self.service_name,
                event_type=event.event_type.value,
                data=event.data
            )
        except Exception as e:
            logger.error(
                "event_publish_error",
                service=self.service_name,
                event_type=event.event_type.value,
                error=str(e)
            )
    
    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """
        Suscribe un handler a un tipo de evento
        
        Args:
            event_type: Tipo de evento
            handler: Función async que maneja el evento
        """
        if event_type not in self.handlers:
            self.handlers[event_type] = []
        
        self.handlers[event_type].append(handler)
        
        logger.info(
            "event_handler_registered",
            service=self.service_name,
            event_type=event_type.value,
            handlers_count=len(self.handlers[event_type])
        )
    
    async def start_listening(self) -> None:
        """
        Inicia el listener de eventos
        
        Debe llamarse después de registrar todos los handlers
        """
        if self.listener_task:
            logger.warning("event_listener_already_running", service=self.service_name)
            return
        
        # Crear Pub/Sub
        self.pubsub = self.redis.client.pubsub()
        
        # Suscribirse a todos los canales de eventos registrados
        channels = [f"events:{event_type.value}" for event_type in self.handlers.keys()]
        
        if not channels:
            logger.warning("no_event_handlers_registered", service=self.service_name)
            return
        
        for channel in channels:
            await self.pubsub.subscribe(channel)
        
        logger.info(
            "event_listener_started",
            service=self.service_name,
            channels=channels
        )
        
        # Iniciar tarea de escucha
        self.listener_task = asyncio.create_task(self._listen_loop())
    
    async def _listen_loop(self) -> None:
        """Loop principal de escucha de eventos"""
        try:
            while True:
                try:
                    # Esperar mensajes
                    message = await self.pubsub.get_message(
                        ignore_subscribe_messages=True,
                        timeout=1.0
                    )
                    
                    if message and message['type'] == 'message':
                        await self._handle_message(message)
                    
                    await asyncio.sleep(0.01)  # Pequeño delay para no saturar CPU
                    
                except asyncio.CancelledError:
                    logger.info("event_listener_cancelled", service=self.service_name)
                    break
                    
                except Exception as e:
                    logger.error(
                        "event_listener_error",
                        service=self.service_name,
                        error=str(e)
                    )
                    await asyncio.sleep(1)  # Esperar antes de reintentar
        
        finally:
            if self.pubsub:
                await self.pubsub.close()
    
    async def _handle_message(self, message: Dict[str, Any]) -> None:
        """Maneja un mensaje recibido"""
        try:
            # Parsear evento
            event = Event.from_json(message['data'])
            
            # Obtener handlers
            handlers = self.handlers.get(event.event_type, [])
            
            if not handlers:
                logger.debug(
                    "no_handlers_for_event",
                    service=self.service_name,
                    event_type=event.event_type.value
                )
                return
            
            logger.info(
                "event_received",
                service=self.service_name,
                event_type=event.event_type.value,
                data=event.data,
                handlers_count=len(handlers)
            )
            
            # Ejecutar todos los handlers
            for handler in handlers:
                try:
                    await handler(event)
                except Exception as e:
                    logger.error(
                        "event_handler_error",
                        service=self.service_name,
                        event_type=event.event_type.value,
                        error=str(e)
                    )
        
        except Exception as e:
            logger.error(
                "event_message_handling_error",
                service=self.service_name,
                error=str(e),
                message=str(message)
            )
    
    async def stop_listening(self) -> None:
        """Detiene el listener de eventos"""
        if self.listener_task:
            self.listener_task.cancel()
            try:
                await self.listener_task
            except asyncio.CancelledError:
                pass
            
            self.listener_task = None
            
            logger.info("event_listener_stopped", service=self.service_name)


# Helpers para crear eventos comunes

def create_day_changed_event(
    new_date: str,
    previous_date: str,
    session: str
) -> Event:
    """Crea evento de cambio de día"""
    return Event(
        event_type=EventType.DAY_CHANGED,
        data={
            'new_date': new_date,
            'previous_date': previous_date,
            'session': session
        }
    )


def create_session_changed_event(
    new_session: str,
    previous_session: str,
    trading_date: str
) -> Event:
    """Crea evento de cambio de sesión"""
    return Event(
        event_type=EventType.SESSION_CHANGED,
        data={
            'new_session': new_session,
            'previous_session': previous_session,
            'trading_date': trading_date
        }
    )


def create_warmup_completed_event(
    tickers_loaded: int,
    duration_seconds: float
) -> Event:
    """Crea evento de warmup completado"""
    return Event(
        event_type=EventType.DATA_WARMUP_COMPLETED,
        data={
            'tickers_loaded': tickers_loaded,
            'duration_seconds': duration_seconds
        }
    )


def create_slots_saved_event(
    symbols_count: int,
    slots_count: int,
    trading_date: str
) -> Event:
    """Crea evento de slots guardados"""
    return Event(
        event_type=EventType.SLOTS_SAVED,
        data={
            'symbols_count': symbols_count,
            'slots_count': slots_count,
            'trading_date': trading_date
        }
    )

