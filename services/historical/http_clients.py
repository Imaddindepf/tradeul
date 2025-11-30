"""
HTTP Clients - Clientes HTTP compartidos para Historical Service

APIs utilizadas:
- FMP (Financial Modeling Prep): float data, quotes, profiles
- Polygon: ticker details, aggregates
"""

import httpx
from typing import Optional, Dict, Any, List
import structlog

logger = structlog.get_logger(__name__)


# ============================================================================
# Configuración de límites
# ============================================================================

EXTERNAL_API_LIMITS = httpx.Limits(
    max_keepalive_connections=20,
    max_connections=50,
    keepalive_expiry=60.0
)


# ============================================================================
# Cliente para FMP API
# ============================================================================

class FMPClient:
    """
    Cliente HTTP para Financial Modeling Prep API
    
    Endpoints usados:
    - /api/v3/available-traded/list
    - /stable/shares-float-all
    - /api/v3/quote (batch y single)
    - /api/v3/profile (batch y single)
    """
    
    BASE_URL = "https://financialmodelingprep.com"
    
    def __init__(self, api_key: str, timeout: float = 30.0):
        self.api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=timeout,
            limits=EXTERNAL_API_LIMITS,
            http2=True,
        )
        logger.info("fmp_client_initialized", base_url=self.BASE_URL)
    
    async def get(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Any]:
        """GET request genérico a FMP"""
        if params is None:
            params = {}
        params['apikey'] = self.api_key
        
        try:
            response = await self._client.get(endpoint, params=params)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            logger.error("fmp_request_error", endpoint=endpoint, error=str(e))
            return None
    
    async def get_available_traded(self) -> Optional[List[Dict]]:
        """Obtiene lista de tickers disponibles para trading"""
        return await self.get("/api/v3/available-traded/list")
    
    async def get_float_all(self, page: int = 0, limit: int = 1000) -> Optional[List[Dict]]:
        """Obtiene datos de float paginados"""
        return await self.get(f"/stable/shares-float-all", params={"page": page, "limit": limit})
    
    async def get_batch_quotes(self, symbols: List[str]) -> Optional[List[Dict]]:
        """Obtiene quotes para múltiples símbolos (max 100)"""
        symbols_str = ",".join(symbols[:100])
        return await self.get(f"/api/v3/quote/{symbols_str}")
    
    async def get_batch_profiles(self, symbols: List[str]) -> Optional[List[Dict]]:
        """Obtiene profiles para múltiples símbolos (max 100)"""
        symbols_str = ",".join(symbols[:100])
        return await self.get(f"/api/v3/profile/{symbols_str}")
    
    async def get_quote(self, symbol: str) -> Optional[List[Dict]]:
        """Obtiene quote para un símbolo"""
        return await self.get(f"/api/v3/quote/{symbol}")
    
    async def get_profile(self, symbol: str) -> Optional[List[Dict]]:
        """Obtiene profile para un símbolo"""
        return await self.get(f"/api/v3/profile/{symbol}")
    
    async def close(self):
        await self._client.aclose()
        logger.info("fmp_client_closed")


# ============================================================================
# Cliente para Polygon API
# ============================================================================

class PolygonClient:
    """
    Cliente HTTP para Polygon.io API
    
    Endpoints usados:
    - /v3/reference/tickers/{ticker}
    - /v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{from}/{to}
    """
    
    BASE_URL = "https://api.polygon.io"
    
    def __init__(self, api_key: str, timeout: float = 15.0):
        self.api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=timeout,
            limits=EXTERNAL_API_LIMITS,
            http2=True,
        )
        logger.info("polygon_client_initialized", base_url=self.BASE_URL)
    
    async def get(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """GET request genérico a Polygon"""
        if params is None:
            params = {}
        params['apiKey'] = self.api_key
        
        try:
            response = await self._client.get(endpoint, params=params)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            logger.error("polygon_request_error", endpoint=endpoint, error=str(e))
            return None
    
    async def get_ticker_details(self, symbol: str) -> Optional[Dict]:
        """Obtiene detalles de un ticker"""
        data = await self.get(f"/v3/reference/tickers/{symbol}")
        return data.get("results") if data else None
    
    async def get_aggregates(
        self,
        symbol: str,
        multiplier: int,
        timespan: str,
        from_date: str,
        to_date: str,
        adjusted: bool = True
    ) -> Optional[Dict]:
        """Obtiene datos OHLCV agregados"""
        endpoint = f"/v2/aggs/ticker/{symbol}/range/{multiplier}/{timespan}/{from_date}/{to_date}"
        params = {
            "adjusted": str(adjusted).lower(),
            "sort": "asc"
        }
        return await self.get(endpoint, params)
    
    async def close(self):
        await self._client.aclose()
        logger.info("polygon_client_closed")


# ============================================================================
# Manager de Clientes
# ============================================================================

class HTTPClientManager:
    """
    Gestor centralizado de clientes HTTP para historical service
    """
    
    def __init__(self):
        self.fmp: Optional[FMPClient] = None
        self.polygon: Optional[PolygonClient] = None
        self._initialized = False
    
    async def initialize(self, fmp_api_key: str, polygon_api_key: str):
        """Inicializa todos los clientes"""
        if self._initialized:
            logger.warning("http_clients_already_initialized")
            return
        
        self.fmp = FMPClient(fmp_api_key)
        self.polygon = PolygonClient(polygon_api_key)
        
        self._initialized = True
        logger.info("historical_http_client_manager_initialized")
    
    async def close(self):
        """Cierra todos los clientes"""
        if self.fmp:
            await self.fmp.close()
        if self.polygon:
            await self.polygon.close()
        
        self._initialized = False
        logger.info("historical_http_client_manager_closed")


# Singleton global
http_clients = HTTPClientManager()

