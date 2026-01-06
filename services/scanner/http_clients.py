"""
HTTP Clients - Clientes HTTP compartidos para Scanner Service

APIs utilizadas:
- MarketSession: fallback para estado del mercado
- Polygon Aggregates: para captura de volumen regular en post-market
"""

import httpx
from typing import Optional, List, Dict
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

# Límites para Polygon API (plan avanzado ~100 req/s)
POLYGON_API_LIMITS = httpx.Limits(
    max_keepalive_connections=50,
    max_connections=100,
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
# Cliente para Polygon Aggregates API
# ============================================================================

class PolygonAggregatesClient:
    """
    Cliente HTTP dedicado para Polygon Aggregates API
    
    Usado para:
    - Captura de volumen de sesión regular (09:30-16:00 ET)
    - Suma de velas de 1 minuto para cálculo preciso de post-market volume
    
    Connection pooling optimizado para requests paralelos.
    """
    
    BASE_URL = "https://api.polygon.io"
    
    def __init__(self, api_key: str, timeout: float = 30.0):
        self.api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=timeout,
            limits=POLYGON_API_LIMITS,
            http2=True,
            headers={"User-Agent": "Tradeul-Scanner/1.0"}
        )
        logger.info("polygon_aggregates_client_initialized")
    
    async def get_minute_aggregates(
        self,
        symbol: str,
        date: str,
        limit: int = 50000
    ) -> List[Dict]:
        """
        Obtiene velas de 1 minuto para un símbolo en una fecha
        
        Endpoint: GET /v2/aggs/ticker/{symbol}/range/1/minute/{from}/{to}
        
        Args:
            symbol: Símbolo del ticker (ej: "NVDA")
            date: Fecha en formato YYYY-MM-DD
            limit: Máximo de velas a retornar (default 50000, suficiente para todo el día)
        
        Returns:
            Lista de velas con estructura:
            [{t: timestamp_ms, o: open, h: high, l: low, c: close, v: volume, vw: vwap, n: trades}, ...]
        """
        url = f"/v2/aggs/ticker/{symbol}/range/1/minute/{date}/{date}"
        params = {
            "adjusted": "true",
            "sort": "asc",
            "limit": str(limit),
            "apiKey": self.api_key
        }
        
        response = await self._client.get(url, params=params)
        response.raise_for_status()
        
        data = response.json()
        return data.get("results", [])
    
    async def close(self):
        """Cierra el cliente HTTP"""
        await self._client.aclose()
        logger.info("polygon_aggregates_client_closed")


# ============================================================================
# Manager de Clientes
# ============================================================================

class HTTPClientManager:
    """
    Gestor centralizado de clientes HTTP para scanner service
    
    Clientes disponibles:
    - market_session: Estado del mercado (fallback)
    - polygon_aggregates: Velas de minuto para post-market volume
    """
    
    def __init__(self):
        self.market_session: Optional[MarketSessionClient] = None
        self.polygon_aggregates: Optional[PolygonAggregatesClient] = None
        self._initialized = False
    
    async def initialize(
        self,
        market_session_host: str,
        market_session_port: int,
        polygon_api_key: Optional[str] = None
    ):
        """
        Inicializa todos los clientes
        
        Args:
            market_session_host: Host del servicio market_session
            market_session_port: Puerto del servicio market_session
            polygon_api_key: API key de Polygon (opcional, se usa settings si no se proporciona)
        """
        if self._initialized:
            logger.warning("http_clients_already_initialized")
            return
        
        # Market Session Client
        self.market_session = MarketSessionClient(
            market_session_host,
            market_session_port
        )
        
        # Polygon Aggregates Client
        # Importar settings aquí para evitar circular imports
        if polygon_api_key:
            api_key = polygon_api_key
        else:
            from shared.config.settings import settings
            api_key = settings.polygon_api_key
        
        self.polygon_aggregates = PolygonAggregatesClient(api_key)
        
        self._initialized = True
        logger.info("scanner_http_client_manager_initialized")
    
    async def close(self):
        """Cierra todos los clientes"""
        if self.market_session:
            await self.market_session.close()
        
        if self.polygon_aggregates:
            await self.polygon_aggregates.close()
        
        self._initialized = False
        logger.info("scanner_http_client_manager_closed")


# Singleton global
http_clients = HTTPClientManager()
