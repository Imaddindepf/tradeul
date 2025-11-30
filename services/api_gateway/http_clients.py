"""
HTTP Clients - Clientes HTTP compartidos con connection pooling

Optimizados para BAJA LATENCIA en trading real-time:
- Connection pooling (reutiliza conexiones TCP/TLS)
- HTTP/2 cuando disponible
- Timeouts apropiados para cada tipo de request
- Límites de conexiones configurables

Cada cliente se inicializa UNA VEZ al arrancar el servicio
y se reutiliza durante toda la vida de la aplicación.
"""

import httpx
from typing import Optional, Dict, Any, List
import structlog

logger = structlog.get_logger(__name__)


# ============================================================================
# Configuración de límites de conexión
# ============================================================================

# Límites agresivos para baja latencia
REALTIME_LIMITS = httpx.Limits(
    max_keepalive_connections=50,   # Conexiones persistentes
    max_connections=100,             # Máximo total
    keepalive_expiry=30.0           # Mantener abiertas 30s
)

# Límites para APIs externas (rate limited)
EXTERNAL_API_LIMITS = httpx.Limits(
    max_keepalive_connections=20,
    max_connections=50,
    keepalive_expiry=60.0
)

# Límites para servicios internos (baja latencia crítica)
INTERNAL_SERVICE_LIMITS = httpx.Limits(
    max_keepalive_connections=30,
    max_connections=60,
    keepalive_expiry=120.0  # Más tiempo para servicios internos
)


# ============================================================================
# Cliente para Polygon API
# ============================================================================

class PolygonClient:
    """
    Cliente HTTP para Polygon.io API
    
    Endpoints usados:
    - /v2/snapshot/locale/us/markets/stocks/tickers/{symbol}
    - /v2/aggs/ticker/{symbol}/range/{multiplier}/{timespan}/{from}/{to}
    - /vX/reference/ipos
    """
    
    BASE_URL = "https://api.polygon.io"
    
    def __init__(self, api_key: str, timeout: float = 15.0):
        self.api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=timeout,
            limits=EXTERNAL_API_LIMITS,
            http2=True,  # Habilitar HTTP/2 para mejor rendimiento
            headers={
                "User-Agent": "Tradeul-Scanner/1.0"
            }
        )
        logger.info("polygon_client_initialized", base_url=self.BASE_URL)
    
    async def get_snapshot(self, symbol: str) -> Dict[str, Any]:
        """Obtiene snapshot de un ticker"""
        url = f"/v2/snapshot/locale/us/markets/stocks/tickers/{symbol}"
        response = await self._client.get(url, params={"apiKey": self.api_key})
        response.raise_for_status()
        return response.json()
    
    async def get_aggregates(
        self,
        symbol: str,
        multiplier: int,
        timespan: str,
        from_date: str,
        to_date: str,
        limit: int = 50000
    ) -> Dict[str, Any]:
        """Obtiene datos OHLCV agregados"""
        url = f"/v2/aggs/ticker/{symbol}/range/{multiplier}/{timespan}/{from_date}/{to_date}"
        params = {
            "adjusted": "true",
            "sort": "asc",
            "limit": str(limit),
            "apiKey": self.api_key
        }
        response = await self._client.get(url, params=params)
        response.raise_for_status()
        return response.json()
    
    async def get_ipos(self, limit: int = 1000) -> Dict[str, Any]:
        """Obtiene lista de IPOs"""
        url = "/vX/reference/ipos"
        params = {
            "limit": limit,
            "order": "desc",
            "sort": "listing_date",
            "apiKey": self.api_key
        }
        response = await self._client.get(url, params=params)
        response.raise_for_status()
        return response.json()
    
    async def get_ipos_page(self, next_url: str) -> Dict[str, Any]:
        """Obtiene siguiente página de IPOs"""
        separator = "&" if "?" in next_url else "?"
        full_url = f"{next_url}{separator}apiKey={self.api_key}"
        # Para next_url usamos la URL completa
        response = await self._client.get(full_url)
        response.raise_for_status()
        return response.json()
    
    async def proxy_logo(self, logo_url: str) -> httpx.Response:
        """Proxy para obtener logos con API key"""
        separator = "&" if "?" in logo_url else "?"
        proxied_url = f"{logo_url}{separator}apiKey={self.api_key}"
        # Usamos URL completa ya que puede ser diferente dominio
        async with httpx.AsyncClient(timeout=10.0) as temp_client:
            return await temp_client.get(proxied_url)
    
    async def close(self):
        """Cierra el cliente y libera conexiones"""
        await self._client.aclose()
        logger.info("polygon_client_closed")


# ============================================================================
# Cliente para FMP (Financial Modeling Prep) API
# ============================================================================

class FMPClient:
    """
    Cliente HTTP para Financial Modeling Prep API
    
    Endpoints usados:
    - /stable/profile
    - /stable/ratios
    - /api/v3/analyst-stock-recommendations/{symbol}
    - /api/v4/price-target
    - /api/v3/historical-price-full/{symbol}
    """
    
    BASE_URL = "https://financialmodelingprep.com"
    
    def __init__(self, api_key: str, timeout: float = 30.0):
        self.api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=timeout,
            limits=EXTERNAL_API_LIMITS,
            http2=True,
            headers={
                "User-Agent": "Tradeul-Scanner/1.0"
            }
        )
        logger.info("fmp_client_initialized", base_url=self.BASE_URL)
    
    async def get_profile(self, symbol: str) -> List[Dict]:
        """Obtiene perfil de compañía"""
        response = await self._client.get(
            "/stable/profile",
            params={"symbol": symbol, "apikey": self.api_key}
        )
        response.raise_for_status()
        return response.json()
    
    async def get_ratios(self, symbol: str, limit: int = 1) -> List[Dict]:
        """Obtiene ratios financieros"""
        response = await self._client.get(
            "/stable/ratios",
            params={"symbol": symbol, "limit": limit, "apikey": self.api_key}
        )
        response.raise_for_status()
        return response.json()
    
    async def get_analyst_recommendations(self, symbol: str) -> List[Dict]:
        """Obtiene recomendaciones de analistas"""
        response = await self._client.get(
            f"/api/v3/analyst-stock-recommendations/{symbol}",
            params={"apikey": self.api_key}
        )
        response.raise_for_status()
        return response.json()
    
    async def get_price_targets(self, symbol: str) -> List[Dict]:
        """Obtiene price targets de analistas"""
        response = await self._client.get(
            "/api/v4/price-target",
            params={"symbol": symbol, "apikey": self.api_key}
        )
        response.raise_for_status()
        return response.json()
    
    async def get_historical_prices(self, symbol: str, to_date: str) -> Dict[str, Any]:
        """Obtiene precios históricos diarios"""
        response = await self._client.get(
            f"/api/v3/historical-price-full/{symbol}",
            params={"to": to_date, "apikey": self.api_key}
        )
        response.raise_for_status()
        return response.json()
    
    async def close(self):
        """Cierra el cliente"""
        await self._client.aclose()
        logger.info("fmp_client_closed")


# ============================================================================
# Cliente para SEC-API.io
# ============================================================================

class SECAPIClient:
    """
    Cliente HTTP para SEC-API.io
    
    Endpoints usados:
    - /form-s1-424b4 (IPO prospectus)
    """
    
    BASE_URL = "https://api.sec-api.io"
    
    def __init__(self, api_key: str, timeout: float = 30.0):
        self.api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=timeout,
            limits=EXTERNAL_API_LIMITS,
            headers={
                "Authorization": api_key,
                "Content-Type": "application/json",
                "User-Agent": "Tradeul-Scanner/1.0"
            }
        )
        logger.info("sec_api_client_initialized")
    
    async def search_s1_424b4(self, query: str, size: int = 10) -> Dict[str, Any]:
        """Busca formularios S-1 y 424B4"""
        response = await self._client.post(
            "/form-s1-424b4",
            json={
                "query": query,
                "from": "0",
                "size": str(size),
                "sort": [{"filedAt": {"order": "desc"}}]
            }
        )
        response.raise_for_status()
        return response.json()
    
    async def close(self):
        """Cierra el cliente"""
        await self._client.aclose()
        logger.info("sec_api_client_closed")


# ============================================================================
# Cliente para Eleven Labs TTS
# ============================================================================

class ElevenLabsClient:
    """
    Cliente HTTP para Eleven Labs Text-to-Speech
    """
    
    BASE_URL = "https://api.elevenlabs.io/v1"
    
    def __init__(self, api_key: str, timeout: float = 30.0):
        self.api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=timeout,
            limits=EXTERNAL_API_LIMITS,
            headers={
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
                "xi-api-key": api_key,
            }
        )
        logger.info("elevenlabs_client_initialized")
    
    async def text_to_speech(
        self,
        text: str,
        voice_id: str = "21m00Tcm4TlvDq8ikWAM",
        language_code: str = "es"
    ) -> bytes:
        """Convierte texto a audio"""
        response = await self._client.post(
            f"/text-to-speech/{voice_id}",
            json={
                "text": text[:500],  # Limitar a 500 chars
                "model_id": "eleven_multilingual_v2",
                "language_code": language_code,
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75
                }
            }
        )
        response.raise_for_status()
        return response.content
    
    async def close(self):
        """Cierra el cliente"""
        await self._client.aclose()
        logger.info("elevenlabs_client_closed")


# ============================================================================
# Clientes para Servicios Internos
# ============================================================================

class InternalServiceClient:
    """
    Cliente HTTP genérico para servicios internos
    
    Optimizado para MÍNIMA LATENCIA:
    - Connection pooling agresivo
    - Timeouts cortos
    - Sin HTTP/2 (overhead innecesario en red local)
    """
    
    def __init__(self, service_name: str, base_url: str, timeout: float = 5.0):
        self.service_name = service_name
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            limits=INTERNAL_SERVICE_LIMITS,
            # HTTP/1.1 para servicios internos (más simple, menos overhead)
            http2=False,
        )
        logger.info("internal_client_initialized", service=service_name, base_url=base_url)
    
    async def get(self, path: str, params: Optional[Dict] = None) -> httpx.Response:
        """GET request"""
        return await self._client.get(path, params=params)
    
    async def post(self, path: str, json: Optional[Dict] = None) -> httpx.Response:
        """POST request"""
        return await self._client.post(path, json=json)
    
    async def close(self):
        """Cierra el cliente"""
        await self._client.aclose()
        logger.info("internal_client_closed", service=self.service_name)


class MarketSessionClient(InternalServiceClient):
    """Cliente para market_session service"""
    
    def __init__(self, host: str = "market_session", port: int = 8002, timeout: float = 2.0):
        super().__init__(
            service_name="market_session",
            base_url=f"http://{host}:{port}",
            timeout=timeout  # Muy corto - es crítico para latencia
        )
    
    async def get_current_session(self) -> Dict[str, Any]:
        """Obtiene sesión actual del mercado"""
        try:
            response = await self.get("/api/session/current")
            if response.status_code == 200:
                return response.json()
            return {"session": "POST_MARKET"}  # Fallback
        except Exception:
            return {"session": "POST_MARKET"}  # Fallback silencioso


class TickerMetadataClient(InternalServiceClient):
    """Cliente para ticker_metadata service"""
    
    def __init__(self, host: str = "ticker_metadata", port: int = 8010, timeout: float = 5.0):
        super().__init__(
            service_name="ticker_metadata",
            base_url=f"http://{host}:{port}",
            timeout=timeout
        )
    
    async def search(self, query: str, limit: int = 10) -> Dict[str, Any]:
        """Busca tickers por símbolo o nombre"""
        response = await self.get(
            "/api/v1/metadata/search",
            params={"q": query, "limit": limit}
        )
        response.raise_for_status()
        return response.json()
    
    async def get_metadata(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Obtiene metadata de un ticker"""
        response = await self.get(f"/api/v1/metadata/{symbol}")
        if response.status_code == 200:
            return response.json()
        return None


class BenzingaNewsClient(InternalServiceClient):
    """Cliente para benzinga-news service"""
    
    def __init__(self, host: str = "benzinga-news", port: int = 8015, timeout: float = 10.0):
        super().__init__(
            service_name="benzinga_news",
            base_url=f"http://{host}:{port}",
            timeout=timeout
        )
    
    async def get_news(
        self,
        ticker: Optional[str] = None,
        channels: Optional[str] = None,
        tags: Optional[str] = None,
        author: Optional[str] = None,
        limit: int = 50
    ) -> Dict[str, Any]:
        """Obtiene noticias con filtros"""
        params = {"limit": limit}
        if ticker:
            params["ticker"] = ticker
        if channels:
            params["channels"] = channels
        if tags:
            params["tags"] = tags
        if author:
            params["author"] = author
        
        response = await self.get("/api/v1/news", params=params)
        response.raise_for_status()
        return response.json()
    
    async def get_latest(self, limit: int = 50) -> Dict[str, Any]:
        """Obtiene últimas noticias"""
        response = await self.get("/api/v1/news/latest", params={"limit": limit})
        response.raise_for_status()
        return response.json()
    
    async def get_by_ticker(self, ticker: str, limit: int = 50) -> Dict[str, Any]:
        """Obtiene noticias por ticker"""
        response = await self.get(f"/api/v1/news/ticker/{ticker}", params={"limit": limit})
        response.raise_for_status()
        return response.json()


# ============================================================================
# Gestor de Clientes HTTP
# ============================================================================

class HTTPClientManager:
    """
    Gestor centralizado de todos los clientes HTTP
    
    Se inicializa una vez en el lifespan de FastAPI
    y proporciona acceso a todos los clientes.
    """
    
    def __init__(self):
        self.polygon: Optional[PolygonClient] = None
        self.fmp: Optional[FMPClient] = None
        self.sec_api: Optional[SECAPIClient] = None
        self.elevenlabs: Optional[ElevenLabsClient] = None
        self.market_session: Optional[MarketSessionClient] = None
        self.ticker_metadata: Optional[TickerMetadataClient] = None
        self.benzinga_news: Optional[BenzingaNewsClient] = None
        self._initialized = False
    
    async def initialize(
        self,
        polygon_api_key: str,
        fmp_api_key: str,
        sec_api_key: Optional[str] = None,
        elevenlabs_api_key: Optional[str] = None,
    ):
        """Inicializa todos los clientes"""
        if self._initialized:
            logger.warning("http_clients_already_initialized")
            return
        
        # APIs externas
        self.polygon = PolygonClient(polygon_api_key)
        self.fmp = FMPClient(fmp_api_key)
        
        if sec_api_key:
            self.sec_api = SECAPIClient(sec_api_key)
        
        if elevenlabs_api_key:
            self.elevenlabs = ElevenLabsClient(elevenlabs_api_key)
        
        # Servicios internos
        self.market_session = MarketSessionClient()
        self.ticker_metadata = TickerMetadataClient()
        self.benzinga_news = BenzingaNewsClient()
        
        self._initialized = True
        logger.info("http_client_manager_initialized")
    
    async def close(self):
        """Cierra todos los clientes"""
        clients = [
            self.polygon,
            self.fmp,
            self.sec_api,
            self.elevenlabs,
            self.market_session,
            self.ticker_metadata,
            self.benzinga_news,
        ]
        
        for client in clients:
            if client:
                try:
                    await client.close()
                except Exception as e:
                    logger.error("client_close_error", error=str(e))
        
        self._initialized = False
        logger.info("http_client_manager_closed")


# Singleton global
http_clients = HTTPClientManager()

