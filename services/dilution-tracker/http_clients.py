"""
HTTP Clients - Clientes HTTP compartidos para Dilution Tracker

Similar a api_gateway pero más específico para este servicio:
- SEC.gov para filings directos
- SEC-API.io para búsquedas avanzadas
- Polygon para datos de mercado
- FMP para financieros
"""

import httpx
from typing import Optional, Dict, Any, List
import structlog

logger = structlog.get_logger(__name__)


# ============================================================================
# Configuración de límites
# ============================================================================

# Para APIs externas con rate limiting
EXTERNAL_API_LIMITS = httpx.Limits(
    max_keepalive_connections=20,
    max_connections=50,
    keepalive_expiry=60.0
)

# Para SEC.gov (más conservador por rate limiting estricto)
SEC_GOV_LIMITS = httpx.Limits(
    max_keepalive_connections=5,
    max_connections=10,
    keepalive_expiry=30.0
)


# ============================================================================
# Cliente para SEC.gov (filings directos)
# ============================================================================

class SECGovClient:
    """
    Cliente HTTP para SEC.gov
    
    Endpoints usados:
    - /cgi-bin/browse-edgar (búsqueda de filings)
    - /cgi-bin/viewer (filing content)
    - /Archives/edgar/data/{cik}/{accession}
    - /files/company_tickers.json
    """
    
    BASE_URL = "https://www.sec.gov"
    EFTS_URL = "https://efts.sec.gov"
    
    def __init__(self, timeout: float = 30.0):
        # Headers requeridos por SEC.gov
        self.headers = {
            "User-Agent": "Tradeul Scanner contact@tradeul.com",
            "Accept": "application/json, text/html",
            "Accept-Encoding": "gzip, deflate"
        }
        
        self._client = httpx.AsyncClient(
            timeout=timeout,
            limits=SEC_GOV_LIMITS,
            headers=self.headers,
            follow_redirects=True,
        )
        
        self._efts_client = httpx.AsyncClient(
            base_url=self.EFTS_URL,
            timeout=timeout,
            limits=SEC_GOV_LIMITS,
            headers=self.headers,
        )
        
        logger.info("sec_gov_client_initialized")
    
    async def get_company_tickers(self) -> Optional[Dict]:
        """Obtiene el mapping de tickers a CIK"""
        url = f"{self.BASE_URL}/files/company_tickers.json"
        try:
            response = await self._client.get(url)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error("sec_gov_company_tickers_error", error=str(e))
            return None
    
    async def search_filings(self, cik: str) -> Optional[Dict]:
        """Busca filings por CIK usando browse-edgar"""
        url = f"{self.BASE_URL}/cgi-bin/browse-edgar"
        params = {
            "action": "getcompany",
            "CIK": cik,
            "type": "",
            "dateb": "",
            "owner": "include",
            "count": "100",
            "output": "atom"
        }
        try:
            response = await self._client.get(url, params=params)
            response.raise_for_status()
            return {"content": response.text, "status": response.status_code}
        except Exception as e:
            logger.error("sec_gov_search_error", cik=cik, error=str(e))
            return None
    
    async def get_filing_content(self, url: str) -> Optional[str]:
        """Obtiene contenido de un filing específico"""
        try:
            response = await self._client.get(url)
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.error("sec_gov_filing_error", url=url, error=str(e))
            return None
    
    async def full_text_search(self, query: str, form_types: List[str], start_date: str, end_date: str) -> Optional[Dict]:
        """Búsqueda de texto completo en EFTS"""
        params = {
            "q": query,
            "dateRange": "custom",
            "startdt": start_date,
            "enddt": end_date,
            "forms": ",".join(form_types),
        }
        try:
            response = await self._efts_client.get("/LATEST/search-index", params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error("sec_efts_search_error", query=query, error=str(e))
            return None
    
    async def close(self):
        await self._client.aclose()
        await self._efts_client.aclose()
        logger.info("sec_gov_client_closed")


# ============================================================================
# Cliente para SEC-API.io
# ============================================================================

class SECAPIClient:
    """
    Cliente HTTP para SEC-API.io (búsquedas avanzadas)
    
    Usado para búsquedas estructuradas de S-1, 424B4, etc.
    """
    
    BASE_URL = "https://api.sec-api.io"
    
    def __init__(self, api_key: str, timeout: float = 60.0):
        self.api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=timeout,
            limits=EXTERNAL_API_LIMITS,
            headers={
                "Authorization": api_key,
                "Content-Type": "application/json",
            }
        )
        logger.info("sec_api_client_initialized")
    
    async def query_api(self, query: Dict[str, Any]) -> Optional[Dict]:
        """Ejecuta query a SEC-API"""
        try:
            params = {"token": self.api_key}
            response = await self._client.post("/", json=query, params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error("sec_api_query_error", error=str(e))
            return None
    
    async def get_filings(self, cik: str, form_type: str = None) -> Optional[Dict]:
        """Obtiene filings por CIK"""
        query = {
            "query": {
                "query_string": {
                    "query": f"cik:{cik}" + (f" AND formType:\"{form_type}\"" if form_type else "")
                }
            },
            "from": "0",
            "size": "50",
            "sort": [{"filedAt": {"order": "desc"}}]
        }
        return await self.query_api(query)
    
    async def close(self):
        await self._client.aclose()
        logger.info("sec_api_client_closed")


# ============================================================================
# Cliente para Polygon API
# ============================================================================

class PolygonClient:
    """
    Cliente HTTP para Polygon.io
    
    Usado para snapshots y datos de mercado.
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
        logger.info("polygon_client_initialized")
    
    async def get_snapshot(self, ticker: str) -> Optional[Dict]:
        """Obtiene snapshot de un ticker"""
        url = f"/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}"
        try:
            response = await self._client.get(url, params={"apiKey": self.api_key})
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error("polygon_snapshot_error", ticker=ticker, error=str(e))
            return None
    
    async def get_financials(self, ticker: str, limit: int = 10) -> Optional[Dict]:
        """Obtiene datos financieros de Polygon"""
        url = f"/vX/reference/financials"
        params = {
            "ticker": ticker,
            "limit": limit,
            "apiKey": self.api_key
        }
        try:
            response = await self._client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error("polygon_financials_error", ticker=ticker, error=str(e))
            return None
    
    async def close(self):
        await self._client.aclose()
        logger.info("polygon_client_closed")


# ============================================================================
# Cliente para FMP API
# ============================================================================

class FMPClient:
    """
    Cliente HTTP para Financial Modeling Prep API
    
    Usado para datos financieros, filings, y holders.
    """
    
    BASE_URL_V3 = "https://financialmodelingprep.com/api/v3"
    BASE_URL_V4 = "https://financialmodelingprep.com/api/v4"
    
    def __init__(self, api_key: str, timeout: float = 30.0):
        self.api_key = api_key
        self._client = httpx.AsyncClient(
            timeout=timeout,
            limits=EXTERNAL_API_LIMITS,
            http2=True,
        )
        logger.info("fmp_client_initialized")
    
    async def get(
        self,
        endpoint: str,
        params: Optional[Dict] = None,
        version: str = "v3"
    ) -> Optional[Any]:
        """GET request genérico a FMP"""
        base_url = self.BASE_URL_V4 if version == "v4" else self.BASE_URL_V3
        url = f"{base_url}/{endpoint}"
        
        if params is None:
            params = {}
        params['apikey'] = self.api_key
        
        try:
            response = await self._client.get(url, params=params)
            
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, dict) and "Error Message" in data:
                    logger.warning("fmp_error_response", endpoint=endpoint, error=data["Error Message"])
                    return None
                return data
            
            elif response.status_code == 429:
                logger.warning("fmp_rate_limited", endpoint=endpoint)
                return None
            
            else:
                logger.error("fmp_error", endpoint=endpoint, status_code=response.status_code)
                return None
                
        except httpx.TimeoutException:
            logger.error("fmp_timeout", endpoint=endpoint)
            return None
        except Exception as e:
            logger.error("fmp_exception", endpoint=endpoint, error=str(e))
            return None
    
    async def close(self):
        await self._client.aclose()
        logger.info("fmp_client_closed")


# ============================================================================
# Manager de Clientes
# ============================================================================

class HTTPClientManager:
    """
    Gestor centralizado de clientes HTTP para dilution-tracker
    """
    
    def __init__(self):
        self.sec_gov: Optional[SECGovClient] = None
        self.sec_api: Optional[SECAPIClient] = None
        self.polygon: Optional[PolygonClient] = None
        self.fmp: Optional[FMPClient] = None
        self._initialized = False
    
    async def initialize(
        self,
        polygon_api_key: str,
        fmp_api_key: str,
        sec_api_key: Optional[str] = None,
    ):
        """Inicializa todos los clientes"""
        if self._initialized:
            logger.warning("http_clients_already_initialized")
            return
        
        self.sec_gov = SECGovClient()
        self.polygon = PolygonClient(polygon_api_key)
        self.fmp = FMPClient(fmp_api_key)
        
        if sec_api_key:
            self.sec_api = SECAPIClient(sec_api_key)
        
        self._initialized = True
        logger.info("dilution_http_client_manager_initialized")
    
    async def close(self):
        """Cierra todos los clientes"""
        clients = [self.sec_gov, self.sec_api, self.polygon, self.fmp]
        
        for client in clients:
            if client:
                try:
                    await client.close()
                except Exception as e:
                    logger.error("client_close_error", error=str(e))
        
        self._initialized = False
        logger.info("dilution_http_client_manager_closed")


# Singleton global
http_clients = HTTPClientManager()

