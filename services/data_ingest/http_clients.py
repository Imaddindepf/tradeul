"""
HTTP Clients - Clientes HTTP compartidos para Data Ingest Service

APIs utilizadas:
- Polygon: snapshots de mercado (CRÍTICO - alta frecuencia)
- MarketSession: fallback para estado del mercado
"""

import httpx
from typing import Optional, Dict, Any
import structlog

logger = structlog.get_logger(__name__)


# ============================================================================
# Configuración de límites optimizada para alta frecuencia
# ============================================================================

POLYGON_LIMITS = httpx.Limits(
    max_keepalive_connections=10,
    max_connections=20,
    keepalive_expiry=60.0  # Mantener conexiones 60s
)

INTERNAL_SERVICE_LIMITS = httpx.Limits(
    max_keepalive_connections=5,
    max_connections=10,
    keepalive_expiry=30.0
)


# ============================================================================
# Cliente para Polygon API (Snapshots)
# ============================================================================

class PolygonClient:
    """
    Cliente HTTP para Polygon.io API - Snapshots
    
    CRÍTICO: Este cliente se usa para obtener snapshots cada pocos segundos.
    Connection pooling reduce latencia significativamente.
    """
    
    BASE_URL = "https://api.polygon.io"
    
    def __init__(self, api_key: str, timeout: float = 30.0):
        self.api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=timeout,
            limits=POLYGON_LIMITS,
            http2=True,
        )
        logger.info("polygon_snapshot_client_initialized")
    
    async def get_all_tickers_snapshot(self) -> Optional[Dict]:
        """
        Obtiene snapshot de todos los tickers
        
        Endpoint: GET /v2/snapshot/locale/us/markets/stocks/tickers
        """
        params = {"apiKey": self.api_key}
        
        try:
            response = await self._client.get(
                "/v2/snapshot/locale/us/markets/stocks/tickers",
                params=params
            )
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                logger.warning("polygon_rate_limited")
                return None
            else:
                logger.error(
                    "polygon_snapshot_error",
                    status_code=response.status_code
                )
                return None
                
        except Exception as e:
            logger.error("polygon_request_error", error=str(e))
            return None
    
    async def close(self):
        await self._client.aclose()
        logger.info("polygon_snapshot_client_closed")


# ============================================================================
# Cliente para Market Session Service (Fallback)
# ============================================================================

class MarketSessionClient:
    """
    Cliente HTTP para Market Session Service interno
    
    Solo se usa como fallback cuando Redis no tiene el estado.
    """
    
    def __init__(self, host: str, port: int, timeout: float = 5.0):
        base_url = f"http://{host}:{port}"
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            limits=INTERNAL_SERVICE_LIMITS,
        )
        logger.info("market_session_client_initialized", base_url=base_url)
    
    async def get_current_session(self) -> Optional[str]:
        """Obtiene la sesión actual del mercado"""
        try:
            response = await self._client.get("/api/session/current")
            if response.status_code == 200:
                data = response.json()
                return data.get("current_session")
            return None
        except Exception as e:
            logger.error("market_session_request_error", error=str(e))
            return None
    
    async def close(self):
        await self._client.aclose()
        logger.info("market_session_client_closed")


# ============================================================================
# Manager de Clientes
# ============================================================================

class HTTPClientManager:
    """
    Gestor centralizado de clientes HTTP para data_ingest
    """
    
    def __init__(self):
        self.polygon: Optional[PolygonClient] = None
        self.market_session: Optional[MarketSessionClient] = None
        self._initialized = False
    
    async def initialize(
        self,
        polygon_api_key: str,
        market_session_host: str,
        market_session_port: int
    ):
        """Inicializa todos los clientes"""
        if self._initialized:
            logger.warning("http_clients_already_initialized")
            return
        
        self.polygon = PolygonClient(polygon_api_key)
        self.market_session = MarketSessionClient(
            market_session_host,
            market_session_port
        )
        
        self._initialized = True
        logger.info("data_ingest_http_client_manager_initialized")
    
    async def close(self):
        """Cierra todos los clientes"""
        if self.polygon:
            await self.polygon.close()
        if self.market_session:
            await self.market_session.close()
        
        self._initialized = False
        logger.info("data_ingest_http_client_manager_closed")


# Singleton global
http_clients = HTTPClientManager()

