"""
HTTP Clients - Clientes HTTP compartidos para Market Session Service

APIs utilizadas:
- Polygon: market status y holidays
"""

import httpx
from typing import Optional, Dict
import structlog

logger = structlog.get_logger(__name__)


# ============================================================================
# Configuración
# ============================================================================

POLYGON_LIMITS = httpx.Limits(
    max_keepalive_connections=5,
    max_connections=10,
    keepalive_expiry=60.0
)


# ============================================================================
# Cliente para Polygon API (Market Status)
# ============================================================================

class PolygonClient:
    """
    Cliente HTTP para Polygon.io API - Market Status
    
    Endpoints:
    - /v1/marketstatus/upcoming (holidays)
    - /v1/marketstatus/now (current status)
    """
    
    BASE_URL = "https://api.polygon.io"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=10.0,
            limits=POLYGON_LIMITS,
            http2=True,
        )
        logger.info("polygon_market_status_client_initialized")
    
    async def get_upcoming_holidays(self) -> Optional[Dict]:
        """Obtiene próximos días festivos del mercado"""
        params = {"apiKey": self.api_key}
        
        try:
            response = await self._client.get(
                "/v1/marketstatus/upcoming",
                params=params
            )
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(
                    "polygon_holidays_error",
                    status=response.status_code
                )
                return None
        except Exception as e:
            logger.error("polygon_request_error", error=str(e))
            return None
    
    async def get_market_status_now(self) -> Optional[Dict]:
        """Obtiene estado actual del mercado"""
        params = {"apiKey": self.api_key}
        
        try:
            response = await self._client.get(
                "/v1/marketstatus/now",
                params=params,
                timeout=5.0  # Timeout más corto para status
            )
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(
                    "polygon_status_error",
                    status=response.status_code
                )
                return None
        except Exception as e:
            logger.error("polygon_status_request_error", error=str(e))
            return None
    
    async def close(self):
        await self._client.aclose()
        logger.info("polygon_market_status_client_closed")


# ============================================================================
# Manager de Clientes
# ============================================================================

class HTTPClientManager:
    """
    Gestor centralizado de clientes HTTP para market_session service
    """
    
    def __init__(self):
        self.polygon: Optional[PolygonClient] = None
        self._initialized = False
    
    async def initialize(self, polygon_api_key: str):
        """Inicializa todos los clientes"""
        if self._initialized:
            logger.warning("http_clients_already_initialized")
            return
        
        self.polygon = PolygonClient(polygon_api_key)
        
        self._initialized = True
        logger.info("market_session_http_client_manager_initialized")
    
    async def close(self):
        """Cierra todos los clientes"""
        if self.polygon:
            await self.polygon.close()
        
        self._initialized = False
        logger.info("market_session_http_client_manager_closed")


# Singleton global
http_clients = HTTPClientManager()


