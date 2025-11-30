"""
HTTP Clients - Clientes HTTP compartidos para Scanner Service

APIs utilizadas:
- MarketSession: fallback para estado del mercado
"""

import httpx
from typing import Optional
import structlog

logger = structlog.get_logger(__name__)


# ============================================================================
# Configuración
# ============================================================================

INTERNAL_SERVICE_LIMITS = httpx.Limits(
    max_keepalive_connections=5,
    max_connections=10,
    keepalive_expiry=30.0
)


# ============================================================================
# Cliente para Market Session Service
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
    Gestor centralizado de clientes HTTP para scanner service
    """
    
    def __init__(self):
        self.market_session: Optional[MarketSessionClient] = None
        self._initialized = False
    
    async def initialize(
        self,
        market_session_host: str,
        market_session_port: int
    ):
        """Inicializa todos los clientes"""
        if self._initialized:
            logger.warning("http_clients_already_initialized")
            return
        
        self.market_session = MarketSessionClient(
            market_session_host,
            market_session_port
        )
        
        self._initialized = True
        logger.info("scanner_http_client_manager_initialized")
    
    async def close(self):
        """Cierra todos los clientes"""
        if self.market_session:
            await self.market_session.close()
        
        self._initialized = False
        logger.info("scanner_http_client_manager_closed")


# Singleton global
http_clients = HTTPClientManager()

