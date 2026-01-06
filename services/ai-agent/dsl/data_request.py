"""
Data Request System for AI Agent

Maneja el flujo cuando se solicitan datos que no están disponibles:
1. Detecta datos faltantes
2. Dispara evento de solicitud de ingesta
3. Retorna respuesta especial para el frontend
4. Permite callback cuando los datos estén disponibles
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import asyncio

import structlog

logger = structlog.get_logger(__name__)


class DataRequestType(str, Enum):
    """Tipos de solicitud de datos"""
    TICKER_BARS = "ticker_bars"           # Barras OHLCV de un ticker
    TICKER_SNAPSHOT = "ticker_snapshot"   # Snapshot actual de un ticker
    TICKER_METADATA = "ticker_metadata"   # Metadata fundamental
    SEC_FILINGS = "sec_filings"           # SEC filings
    DILUTION_PROFILE = "dilution_profile" # Perfil de dilución


class DataRequestStatus(str, Enum):
    """Estado de la solicitud"""
    PENDING = "pending"       # Esperando procesamiento
    PROCESSING = "processing" # En proceso de ingesta
    COMPLETED = "completed"   # Datos disponibles
    FAILED = "failed"         # Falló la ingesta
    CACHED = "cached"         # Datos ya estaban en cache


@dataclass
class DataRequest:
    """Representa una solicitud de datos"""
    request_id: str
    request_type: DataRequestType
    symbol: str
    params: Dict[str, Any] = field(default_factory=dict)
    status: DataRequestStatus = DataRequestStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "request_type": self.request_type.value,
            "symbol": self.symbol,
            "params": self.params,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error
        }


@dataclass
class MissingDataResult:
    """
    Resultado especial cuando los datos no están disponibles.
    
    El frontend puede usar esto para:
    - Mostrar mensaje "Solicitando datos..."
    - Esperar el callback cuando estén disponibles
    - Reintentar la consulta automáticamente
    """
    request: DataRequest
    message: str
    can_retry: bool = True
    estimated_wait_seconds: int = 5
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "missing_data",
            "request": self.request.to_dict(),
            "message": self.message,
            "can_retry": self.can_retry,
            "estimated_wait_seconds": self.estimated_wait_seconds
        }


class DataRequestManager:
    """
    Gestiona las solicitudes de datos faltantes.
    
    - Verifica si los datos existen
    - Si no, dispara evento de ingesta
    - Trackea solicitudes pendientes
    - Notifica cuando los datos están disponibles
    """
    
    def __init__(self, data_provider, event_bus=None):
        self.data_provider = data_provider
        self.event_bus = event_bus
        self.pending_requests: Dict[str, DataRequest] = {}
        self._request_counter = 0
    
    def _generate_request_id(self) -> str:
        self._request_counter += 1
        return f"req_{datetime.now().strftime('%Y%m%d%H%M%S')}_{self._request_counter}"
    
    async def check_and_request_ticker_data(
        self,
        symbol: str,
        data_type: DataRequestType = DataRequestType.TICKER_SNAPSHOT
    ) -> tuple[bool, Optional[MissingDataResult]]:
        """
        Verifica si tenemos datos de un ticker y si no, solicita ingesta.
        
        Returns:
            (data_exists, missing_data_result)
            - Si data_exists=True, los datos están disponibles
            - Si data_exists=False, missing_data_result tiene info de la solicitud
        """
        symbol = symbol.upper()
        
        # 1. Verificar si el ticker está en el scanner/cache
        exists = await self._check_ticker_exists(symbol)
        
        if exists:
            logger.debug("ticker_data_exists", symbol=symbol)
            return True, None
        
        # 2. No existe - crear solicitud de ingesta
        logger.info("ticker_data_missing", symbol=symbol, data_type=data_type.value)
        
        request = DataRequest(
            request_id=self._generate_request_id(),
            request_type=data_type,
            symbol=symbol,
            params={"source": "polygon"}
        )
        
        # 3. Guardar en pendientes
        self.pending_requests[request.request_id] = request
        
        # 4. Disparar evento de solicitud
        if self.event_bus:
            await self._publish_data_request(request)
        
        # 5. Retornar resultado de datos faltantes
        result = MissingDataResult(
            request=request,
            message=f"El ticker {symbol} no está en el scanner actual. Solicitando datos de Polygon...",
            can_retry=True,
            estimated_wait_seconds=3
        )
        
        return False, result
    
    async def check_ticker_bars(
        self,
        symbol: str,
        days: int = 5,
        timeframe: str = "1h"
    ) -> tuple[bool, Optional[Any], Optional[MissingDataResult]]:
        """
        Verifica si tenemos barras de un ticker.
        
        A diferencia del snapshot, las barras siempre vienen de Polygon,
        así que este método:
        1. Intenta obtener las barras
        2. Si falla o está vacío, dispara solicitud
        
        Returns:
            (success, data, missing_data_result)
        """
        symbol = symbol.upper()
        
        try:
            # Intentar obtener barras de Polygon
            bars = await self.data_provider.get_bars(symbol, days, timeframe)
            
            if bars and len(bars) > 0:
                return True, bars, None
            
            # Sin datos - puede ser ticker inválido o sin historial
            logger.warning("no_bars_for_ticker", symbol=symbol, days=days, timeframe=timeframe)
            
            request = DataRequest(
                request_id=self._generate_request_id(),
                request_type=DataRequestType.TICKER_BARS,
                symbol=symbol,
                params={"days": days, "timeframe": timeframe}
            )
            
            result = MissingDataResult(
                request=request,
                message=f"No hay datos históricos disponibles para {symbol}. Verificando si el ticker existe...",
                can_retry=True,
                estimated_wait_seconds=5
            )
            
            return False, None, result
            
        except Exception as e:
            logger.error("error_fetching_bars", symbol=symbol, error=str(e))
            
            request = DataRequest(
                request_id=self._generate_request_id(),
                request_type=DataRequestType.TICKER_BARS,
                symbol=symbol,
                params={"days": days, "timeframe": timeframe},
                status=DataRequestStatus.FAILED,
                error=str(e)
            )
            
            result = MissingDataResult(
                request=request,
                message=f"Error obteniendo datos de {symbol}: {str(e)}",
                can_retry=True,
                estimated_wait_seconds=10
            )
            
            return False, None, result
    
    async def _check_ticker_exists(self, symbol: str) -> bool:
        """Verifica si un ticker existe en el scanner o metadata"""
        try:
            # Opción 1: Buscar en scanner
            scanner_data = await self.data_provider.get_source_data('scanner')
            for ticker in scanner_data:
                if ticker.get('symbol', '').upper() == symbol:
                    return True
            
            # Opción 2: Buscar en metadata
            metadata = await self.data_provider.redis.get(f"metadata:{symbol}")
            if metadata:
                return True
            
            return False
            
        except Exception as e:
            logger.error("error_checking_ticker", symbol=symbol, error=str(e))
            return False
    
    async def _publish_data_request(self, request: DataRequest) -> None:
        """Publica evento de solicitud de datos"""
        try:
            from shared.events import Event, EventType
            
            event = Event(
                event_type=EventType.DATA_REQUEST,
                data={
                    "request_id": request.request_id,
                    "request_type": request.request_type.value,
                    "symbol": request.symbol,
                    "params": request.params
                }
            )
            
            await self.event_bus.publish(event)
            logger.info("data_request_published", request_id=request.request_id, symbol=request.symbol)
            
        except Exception as e:
            logger.error("error_publishing_data_request", error=str(e))
    
    def mark_completed(self, request_id: str, success: bool = True, error: str = None):
        """Marca una solicitud como completada"""
        if request_id in self.pending_requests:
            request = self.pending_requests[request_id]
            request.status = DataRequestStatus.COMPLETED if success else DataRequestStatus.FAILED
            request.completed_at = datetime.now()
            request.error = error
            
            # Limpiar de pendientes después de un tiempo
            # (en producción usaríamos un TTL)
            del self.pending_requests[request_id]


# ============================================================================
# Funciones DSL para el agente
# ============================================================================

async def smart_get_ticker_data(
    symbol: str,
    data_provider,
    event_bus=None
) -> tuple[Optional[Dict], Optional[MissingDataResult]]:
    """
    Función inteligente que obtiene datos de un ticker.
    
    Si el ticker no está disponible, dispara solicitud de ingesta
    y retorna MissingDataResult para que el frontend lo maneje.
    
    Usage en DSL:
        data, missing = await smart_get_ticker_data('AAPL', data_provider)
        if missing:
            display_missing_data(missing)  # Muestra "Solicitando datos..."
        else:
            display_table(data, "AAPL Info")
    """
    manager = DataRequestManager(data_provider, event_bus)
    exists, missing = await manager.check_and_request_ticker_data(symbol)
    
    if not exists:
        return None, missing
    
    # Obtener datos del scanner
    scanner_data = await data_provider.get_source_data('scanner')
    for ticker in scanner_data:
        if ticker.get('symbol', '').upper() == symbol.upper():
            return ticker, None
    
    return None, missing


async def smart_get_bars(
    symbol: str,
    days: int,
    timeframe: str,
    data_provider,
    event_bus=None
) -> tuple[Optional[Any], Optional[MissingDataResult]]:
    """
    Función inteligente que obtiene barras OHLCV.
    
    Si no hay datos, dispara solicitud y retorna MissingDataResult.
    """
    manager = DataRequestManager(data_provider, event_bus)
    success, data, missing = await manager.check_ticker_bars(symbol, days, timeframe)
    
    if success:
        return data, None
    
    return None, missing

