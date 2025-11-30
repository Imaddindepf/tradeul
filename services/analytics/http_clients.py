"""
HTTP Clients - Clientes HTTP compartidos para Analytics Service

APIs utilizadas:
- Polygon: datos intraday para recovery
"""

import httpx
from typing import Optional, Dict
import structlog

logger = structlog.get_logger(__name__)


# ============================================================================
# Configuración
# ============================================================================

POLYGON_LIMITS = httpx.Limits(
    max_keepalive_connections=10,
    max_connections=20,
    keepalive_expiry=60.0
)


# ============================================================================
# Cliente para Polygon API
# ============================================================================

class PolygonClient:
    """
    Cliente HTTP para Polygon.io API - Datos Intraday
    
    Usado para recuperar datos de high/low en restart.
    """
    
    BASE_URL = "https://api.polygon.io"
    
    def __init__(self, api_key: str, timeout: float = 10.0):
        self.api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=timeout,
            limits=POLYGON_LIMITS,
            http2=True,
        )
        logger.info("polygon_intraday_client_initialized")
    
    async def get_minute_aggregates(
        self,
        symbol: str,
        from_ts: int,
        to_ts: int
    ) -> Optional[Dict]:
        """
        Obtiene aggregates de 1 minuto para un símbolo
        
        Args:
            symbol: Ticker symbol
            from_ts: Unix timestamp (ms) inicio
            to_ts: Unix timestamp (ms) fin
        """
        endpoint = f"/v2/aggs/ticker/{symbol}/range/1/minute/{from_ts}/{to_ts}"
        params = {
            "apiKey": self.api_key,
            "adjusted": "true",
            "sort": "asc"
        }
        
        try:
            response = await self._client.get(endpoint, params=params)
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(
                    "polygon_aggregates_error",
                    symbol=symbol,
                    status=response.status_code
                )
                return None
        except Exception as e:
            logger.error("polygon_request_error", symbol=symbol, error=str(e))
            return None
    
    async def close(self):
        await self._client.aclose()
        logger.info("polygon_intraday_client_closed")


# ============================================================================
# Manager de Clientes
# ============================================================================

class HTTPClientManager:
    """
    Gestor centralizado de clientes HTTP para analytics service
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
        logger.info("analytics_http_client_manager_initialized")
    
    async def close(self):
        """Cierra todos los clientes"""
        if self.polygon:
            await self.polygon.close()
        
        self._initialized = False
        logger.info("analytics_http_client_manager_closed")


# Singleton global
http_clients = HTTPClientManager()

