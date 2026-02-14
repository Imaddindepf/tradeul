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
    
    async def get_daily_aggregates(
        self,
        symbol: str,
        from_date: str,
        to_date: str,
        limit: int = 5000
    ) -> Dict[str, Any]:
        """
        Obtiene datos OHLCV diarios de Polygon.
        
        Usado como fallback cuando FMP no tiene datos (warrants, OTC, etc.)
        
        Args:
            symbol: Ticker symbol
            from_date: Fecha inicio YYYY-MM-DD
            to_date: Fecha fin YYYY-MM-DD
            limit: Máximo de resultados
        
        Returns:
            Dict con results[] conteniendo barras diarias
        """
        url = f"/v2/aggs/ticker/{symbol}/range/1/day/{from_date}/{to_date}"
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
    - Query API (Form 4 insider trading)
    """
    
    BASE_URL = "https://api.sec-api.io"
    QUERY_URL = "https://api.sec-api.io"  # Query API para búsquedas generales
    
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
    
    async def search_insider_trading(
        self, 
        ticker: Optional[str] = None,
        insider_cik: Optional[str] = None,
        size: int = 50,
        from_index: int = 0
    ) -> Dict[str, Any]:
        """
        Busca Insider Trading usando el endpoint dedicado de SEC-API.io
        que ya devuelve transacciones parseadas (NO necesita ir a SEC.gov)
        
        Args:
            ticker: Filtrar por ticker de la empresa
            insider_cik: Filtrar por CIK del insider
            size: Número de resultados (max 50)
            from_index: Offset para paginación
        """
        # Construir query para el endpoint /insider-trading
        query_parts = []
        
        if ticker:
            query_parts.append(f'issuer.tradingSymbol:{ticker.upper()}')
        if insider_cik:
            query_parts.append(f'reportingOwner.cik:{insider_cik}')
        
        query = " AND ".join(query_parts) if query_parts else "*"
        
        # Usar el endpoint específico /insider-trading que ya parsea XMLs
        response = await self._client.post(
            f"/insider-trading?token={self.api_key}",
            json={
                "query": query,
                "from": str(from_index),
                "size": str(min(size, 50)),  # Max 50 por request
                "sort": [{"filedAt": {"order": "desc"}}]
            }
        )
        response.raise_for_status()
        return response.json()
    
    async def search_form4(
        self, 
        ticker: Optional[str] = None,
        insider_cik: Optional[str] = None,
        size: int = 50,
        from_index: int = 0
    ) -> Dict[str, Any]:
        """
        DEPRECATED: Use search_insider_trading instead.
        Busca Form 4 usando búsqueda genérica (no incluye transacciones)
        """
        query_parts = ['formType:4', 'NOT formType:"N-4"', 'NOT formType:"4/A"']
        
        if ticker:
            query_parts.append(f'ticker:{ticker.upper()}')
        if insider_cik:
            query_parts.append(f'cik:{insider_cik}')
        
        query = " AND ".join(query_parts)
        
        response = await self._client.post(
            f"?token={self.api_key}",
            json={
                "query": query,
                "from": str(from_index),
                "size": str(size),
                "sort": [{"filedAt": {"order": "desc"}}]
            }
        )
        response.raise_for_status()
        return response.json()
    
    async def parse_form4_xml(self, xml_url: str) -> Dict[str, Any]:
        """
        Parsea el XML de un Form 4 para extraer detalles de las transacciones
        
        Returns:
            Dict con: insider_name, insider_title, is_director, is_officer, 
                      is_ten_percent_owner, transactions[]
        """
        import xml.etree.ElementTree as ET
        
        try:
            # Remove xslF345X05 from URL to get raw XML
            if 'xslF345X05/' in xml_url:
                xml_url = xml_url.replace('xslF345X05/', '')
            
            # Use separate client for SEC.gov requests
            async with httpx.AsyncClient(timeout=15.0) as sec_client:
                headers = {'User-Agent': 'Tradeul/1.0 support@tradeul.com'}
                response = await sec_client.get(xml_url, headers=headers)
                response.raise_for_status()
                xml_content = response.text
            
            root = ET.fromstring(xml_content)
            
            # Extraer info del insider
            owner = root.find('.//reportingOwner')
            result = {
                'insider_name': None,
                'insider_cik': None,
                'insider_title': None,
                'is_director': False,
                'is_officer': False,
                'is_ten_percent_owner': False,
                'transactions': []
            }
            
            if owner:
                name_el = owner.find('.//rptOwnerName')
                cik_el = owner.find('.//rptOwnerCik')
                result['insider_name'] = name_el.text if name_el is not None else None
                result['insider_cik'] = cik_el.text if cik_el is not None else None
                
                rel = owner.find('.//reportingOwnerRelationship')
                if rel:
                    is_dir = rel.find('isDirector')
                    is_off = rel.find('isOfficer')
                    is_ten = rel.find('isTenPercentOwner')
                    title = rel.find('officerTitle')
                    
                    result['is_director'] = is_dir is not None and is_dir.text == '1'
                    result['is_officer'] = is_off is not None and is_off.text == '1'
                    result['is_ten_percent_owner'] = is_ten is not None and is_ten.text == '1'
                    result['insider_title'] = title.text if title is not None else None
            
            # Extraer transacciones non-derivative
            for tx in root.findall('.//nonDerivativeTransaction'):
                transaction = self._parse_transaction(tx)
                if transaction:
                    result['transactions'].append(transaction)
            
            # Extraer transacciones derivative
            for tx in root.findall('.//derivativeTransaction'):
                transaction = self._parse_transaction(tx, is_derivative=True)
                if transaction:
                    result['transactions'].append(transaction)
            
            return result
            
        except Exception as e:
            logger.error("parse_form4_xml_error", url=xml_url, error=str(e))
            return {'transactions': [], 'error': str(e)}
    
    def _parse_transaction(self, tx_element, is_derivative: bool = False) -> Optional[Dict]:
        """Helper para parsear una transacción individual"""
        try:
            def get_value(path):
                el = tx_element.find(path)
                return el.text if el is not None else None
            
            shares = get_value('.//transactionShares/value')
            price = get_value('.//transactionPricePerShare/value')
            acq_disp = get_value('.//transactionAcquiredDisposedCode/value')
            date = get_value('.//transactionDate/value')
            security = get_value('.//securityTitle/value')
            
            # Calcular valor total
            shares_float = float(shares) if shares else 0
            price_float = float(price) if price else 0
            total_value = shares_float * price_float
            
            return {
                'date': date,
                'security': security,
                'transaction_type': 'A' if acq_disp == 'A' else 'D',  # A=Acquired, D=Disposed
                'shares': shares_float,
                'price': price_float,
                'total_value': total_value,
                'is_derivative': is_derivative
            }
        except Exception:
            return None
    
    async def get_form4_clusters(self, days: int = 7, min_count: int = 3) -> Dict[str, Any]:
        """
        Detecta clusters de insider trading (múltiples insiders en la misma empresa)
        
        Args:
            days: Número de días hacia atrás
            min_count: Mínimo de transacciones para considerar cluster
        """
        from datetime import datetime, timedelta
        
        # Calcular fecha de inicio
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        query = f'formType:4 AND NOT formType:"N-4" AND NOT formType:"4/A" AND filedAt:[{start_date} TO *]'
        
        response = await self._client.post(
            f"?token={self.api_key}",
            json={
                "query": query,
                "from": "0",
                "size": "200",
                "sort": [{"filedAt": {"order": "desc"}}]
            }
        )
        response.raise_for_status()
        data = response.json()
        
        # Agrupar por ticker
        from collections import defaultdict
        by_ticker = defaultdict(list)
        
        for filing in data.get('filings', []):
            ticker = filing.get('ticker')
            if ticker:
                # Extraer insider del filing
                insiders = [
                    e.get('companyName', '').replace(' (Reporting)', '')
                    for e in filing.get('entities', [])
                    if 'Reporting' in e.get('companyName', '')
                ]
                for insider in insiders:
                    by_ticker[ticker].append({
                        'insider': insider,
                        'date': filing.get('filedAt', '')[:10],
                        'company': filing.get('companyName', ''),
                        'accessionNo': filing.get('accessionNo'),
                        'url': filing.get('linkToFilingDetails')
                    })
        
        # Filtrar clusters
        clusters = []
        for ticker, trades in by_ticker.items():
            unique_insiders = set(t['insider'] for t in trades)
            if len(trades) >= min_count:
                clusters.append({
                    'ticker': ticker,
                    'company': trades[0]['company'] if trades else '',
                    'total_trades': len(trades),
                    'unique_insiders': len(unique_insiders),
                    'insiders': list(unique_insiders)[:5],  # Top 5 insiders
                    'trades': trades[:10]  # Top 10 trades
                })
        
        # Ordenar por número de trades
        clusters.sort(key=lambda x: x['total_trades'], reverse=True)
        
        return {
            'clusters': clusters[:20],  # Top 20 clusters
            'period_days': days,
            'total_filings': data.get('total', {}).get('value', 0)
        }
    
    # ========================================================================
    # Form 13F - Institutional Holdings
    # ========================================================================
    
    async def search_13f_holdings(
        self,
        ticker: Optional[str] = None,
        cik: Optional[str] = None,
        cusip: Optional[str] = None,
        period_of_report: Optional[str] = None,
        size: int = 50,
        from_index: int = 0
    ) -> Dict[str, Any]:
        """
        Search Form 13F holdings using SEC-API.io
        
        Args:
            ticker: Filter by ticker in holdings
            cik: Filter by fund CIK
            cusip: Filter by CUSIP
            period_of_report: Filter by quarter (e.g., "2024-09-30")
            size: Number of results (max 50)
            from_index: Offset for pagination
        """
        query_parts = []
        
        if ticker:
            query_parts.append(f'holdings.ticker:{ticker.upper()}')
        if cik:
            query_parts.append(f'cik:{cik}')
        if cusip:
            query_parts.append(f'holdings.cusip:{cusip}')
        if period_of_report:
            query_parts.append(f'periodOfReport:{period_of_report}')
        
        query = " AND ".join(query_parts) if query_parts else "*"
        
        response = await self._client.post(
            f"/form-13f/holdings?token={self.api_key}",
            json={
                "query": query,
                "from": str(from_index),
                "size": str(min(size, 50)),
                "sort": [{"filedAt": {"order": "desc"}}]
            }
        )
        response.raise_for_status()
        return response.json()
    
    async def search_13f_cover_pages(
        self,
        cik: Optional[str] = None,
        crd_number: Optional[str] = None,
        fund_name: Optional[str] = None,
        size: int = 50,
        from_index: int = 0
    ) -> Dict[str, Any]:
        """
        Search Form 13F cover pages using SEC-API.io
        
        Args:
            cik: Filter by fund CIK
            crd_number: Filter by CRD number
            fund_name: Search by fund name
            size: Number of results (max 50)
            from_index: Offset for pagination
        """
        query_parts = []
        
        if cik:
            query_parts.append(f'cik:{cik}')
        if crd_number:
            query_parts.append(f'crdNumber:{crd_number}')
        if fund_name:
            query_parts.append(f'filingManager.name:*{fund_name}*')
        
        query = " AND ".join(query_parts) if query_parts else "*"
        
        response = await self._client.post(
            f"/form-13f/cover-pages?token={self.api_key}",
            json={
                "query": query,
                "from": str(from_index),
                "size": str(min(size, 50)),
                "sort": [{"filedAt": {"order": "desc"}}]
            }
        )
        response.raise_for_status()
        return response.json()
    
    async def get_fund_holdings(self, cik: str) -> Dict[str, Any]:
        """
        Get the most recent 13F holdings for a specific fund
        
        Args:
            cik: Fund's CIK number
        """
        return await self.search_13f_holdings(cik=cik, size=1)
    
    async def get_holders_by_ticker(
        self,
        ticker: str,
        period_of_report: Optional[str] = None,
        size: int = 50,
        from_index: int = 0
    ) -> Dict[str, Any]:
        """
        Get all institutional holders for a specific ticker
        
        Args:
            ticker: Stock ticker symbol
            period_of_report: Filter by quarter (e.g., "2024-09-30")
            size: Number of results
            from_index: Offset for pagination
        """
        return await self.search_13f_holdings(
            ticker=ticker,
            period_of_report=period_of_report,
            size=size,
            from_index=from_index
        )
    
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


class FinancialsClient(InternalServiceClient):
    """
    Cliente para financials service.
    
    Extracción de datos financieros XBRL via microservicio separado.
    """
    
    def __init__(self, host: str = "financials", port: int = 8020, timeout: float = 60.0):
        super().__init__(
            service_name="financials",
            base_url=f"http://{host}:{port}",
            timeout=timeout  # Financials puede tardar más
        )
    
    async def get_financials(
        self,
        symbol: str,
        period: str = "annual",
        limit: int = 10,
        refresh: bool = False
    ) -> Dict[str, Any]:
        """Obtiene datos financieros completos"""
        response = await self.get(
            f"/api/v1/financials/{symbol}",
            params={"period": period, "limit": limit, "refresh": str(refresh).lower()}
        )
        response.raise_for_status()
        return response.json()
    
    async def get_segments(self, symbol: str) -> Dict[str, Any]:
        """Obtiene datos de segmentos y geografía"""
        response = await self.get(f"/api/v1/financials/{symbol}/segments")
        response.raise_for_status()
        return response.json()
    
    async def get_income_details(self, symbol: str, years: int = 10) -> Dict[str, Any]:
        """Obtiene detalles del income statement"""
        response = await self.get(
            f"/api/v1/financials/{symbol}/income-details",
            params={"years": years}
        )
        response.raise_for_status()
        return response.json()
    
    async def clear_cache(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Limpia cache de financials"""
        params = {"symbol": symbol} if symbol else {}
        response = await self.post("/api/v1/financials/cache/clear", json=params)
        response.raise_for_status()
        return response.json()
    
    async def health_check(self) -> bool:
        """Verifica si el servicio está activo"""
        try:
            response = await self.get("/health")
            return response.status_code == 200
        except Exception:
            return False


# ============================================================================
# SEC EDGAR Client (gratis, sin API key)
# ============================================================================

class SECEdgarClient:
    """
    Cliente para SEC EDGAR API pública (gratis, sin API key).
    
    Usado para:
    - Detección de SPACs (SIC Code 6770 = Blank Checks)
    - Obtener CIK de empresa
    - Obtener SIC Code
    """
    
    BASE_URL = "https://data.sec.gov"
    
    # SIC Code para SPACs (Blank Checks)
    SPAC_SIC_CODE = "6770"
    
    # Palabras clave en nombres de SPACs
    SPAC_NAME_KEYWORDS = [
        'acquisition corp',
        'acquisition company',
        'acquisition co',
        'blank check',
        ' spac',
        'merger corp',
        'merger company',
    ]
    
    def __init__(self, timeout: float = 15.0):
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=timeout,
            limits=EXTERNAL_API_LIMITS,
            headers={
                "User-Agent": "Tradeul/1.0 (support@tradeul.com)",
                "Accept": "application/json"
            }
        )
        logger.info("sec_edgar_client_initialized")
    
    async def get_company_info(self, cik: str) -> Optional[Dict[str, Any]]:
        """
        Obtener información de empresa por CIK.
        
        Returns:
            Dict con name, sic, sicDescription, tickers, etc.
        """
        try:
            cik_padded = str(cik).zfill(10)
            response = await self._client.get(f"/submissions/CIK{cik_padded}.json")
            
            if response.status_code == 200:
                return response.json()
            return None
            
        except Exception as e:
            logger.error("sec_edgar_get_company_failed", cik=cik, error=str(e))
            return None
    
    def _check_spac_keywords(self, name: str) -> bool:
        """Verificar si un nombre contiene palabras clave de SPAC"""
        if not name:
            return False
        name_lower = name.lower()
        return any(kw in name_lower for kw in self.SPAC_NAME_KEYWORDS)
    
    async def _detect_spac_from_filings(self, symbol: str, sec_api_client: 'SECAPIClient') -> Optional[str]:
        """
        Buscar en filings S-4/DEFM14A si la empresa fue un de-SPAC.
        
        Busca filings de merger que mencionen un SPAC.
        
        Returns:
            Nombre del SPAC original si se encuentra, None si no
        """
        try:
            # Buscar S-4, F-4, DEFM14A filings (típicos de SPAC mergers)
            query = {
                "query": {
                    "query_string": {
                        "query": f'ticker:{symbol} AND (formType:"S-4" OR formType:"F-4" OR formType:"DEFM14A")'
                    }
                },
                "from": "0",
                "size": "20",
                "sort": [{"filedAt": {"order": "asc"}}]  # Los más antiguos primero
            }
            
            resp = await sec_api_client._client.post(
                "",
                params={"token": sec_api_client.api_key},
                json=query
            )
            
            if resp.status_code != 200:
                return None
            
            filings = resp.json().get('filings', [])
            
            # Buscar un filing cuyo companyName tenga keywords de SPAC
            for filing in filings:
                company_name = filing.get('companyName', '')
                if self._check_spac_keywords(company_name):
                    # Limpiar el nombre (quitar sufijos como "\ DE")
                    clean_name = company_name.split('\\')[0].strip()
                    return clean_name
            
            return None
            
        except Exception as e:
            logger.debug("detect_spac_from_filings_failed", symbol=symbol, error=str(e))
            return None
    
    async def detect_spac(self, symbol: str, sec_api_client: Optional['SECAPIClient'] = None) -> Dict[str, Any]:
        """
        Detectar si un ticker es un SPAC activo o de-SPAC (post-merger).
        
        Args:
            symbol: Ticker symbol
            sec_api_client: Cliente SEC-API.io para obtener CIK (opcional)
        
        Returns:
            Dict con is_spac, is_de_spac, confidence, sic_code, reason, former_spac_name
        """
        symbol = symbol.upper()
        
        try:
            cik = None
            company_name = None
            
            # Obtener CIK desde SEC-API.io si disponible
            if sec_api_client:
                try:
                    query = f'ticker:{symbol}'
                    data = await sec_api_client._client.post(
                        "",
                        params={"token": sec_api_client.api_key},
                        json={"query": {"query_string": {"query": query}}, "from": "0", "size": "1"}
                    )
                    filings = data.json().get('filings', [])
                    if filings:
                        cik = filings[0].get('cik')
                        company_name = filings[0].get('companyName')
                except Exception as e:
                    logger.debug("spac_detect_sec_api_failed", error=str(e))
            
            if not cik:
                return {
                    "is_spac": False,
                    "is_de_spac": False,
                    "confidence": 0.0,
                    "sic_code": None,
                    "reason": "Could not determine CIK"
                }
            
            # Obtener info de empresa desde SEC EDGAR
            company_info = await self.get_company_info(cik)
            
            if not company_info:
                # Fallback: verificar por nombre
                if self._check_spac_keywords(company_name):
                    return {
                        "is_spac": True,
                        "is_de_spac": False,
                        "confidence": 0.80,
                        "sic_code": None,
                        "reason": f"Name '{company_name}' matches SPAC pattern"
                    }
                
                return {
                    "is_spac": False,
                    "is_de_spac": False,
                    "confidence": 0.0,
                    "sic_code": None,
                    "reason": "Company info not available"
                }
            
            sic_code = company_info.get('sic')
            sic_desc = company_info.get('sicDescription')
            name = company_info.get('name', company_name)
            former_names = company_info.get('formerNames', [])
            
            # 1. Verificar SIC Code 6770 (100% certeza - SPAC activo)
            if sic_code == self.SPAC_SIC_CODE:
                return {
                    "is_spac": True,
                    "is_de_spac": False,
                    "confidence": 1.0,
                    "sic_code": sic_code,
                    "sic_description": sic_desc,
                    "reason": "SIC Code 6770 (Blank Checks)"
                }
            
            # 2. Verificar nombre actual (80% certeza - SPAC activo)
            if self._check_spac_keywords(name):
                return {
                    "is_spac": True,
                    "is_de_spac": False,
                    "confidence": 0.80,
                    "sic_code": sic_code,
                    "sic_description": sic_desc,
                    "reason": f"Name '{name}' matches SPAC pattern"
                }
            
            # 3. Verificar formerNames para detectar de-SPAC (100% certeza)
            for former in former_names:
                former_name = former.get('name', '')
                if self._check_spac_keywords(former_name):
                    logger.info("de_spac_detected", symbol=symbol, former_name=former_name, method="formerNames")
                    return {
                        "is_spac": False,
                        "is_de_spac": True,
                        "confidence": 1.0,
                        "sic_code": sic_code,
                        "sic_description": sic_desc,
                        "former_spac_name": former_name,
                        "merger_date": former.get('to'),
                        "reason": f"De-SPAC: Former name '{former_name}' was a SPAC"
                    }
            
            # 4. Fallback: Buscar en S-4/DEFM14A filings si sec_api_client está disponible
            if sec_api_client:
                spac_from_filings = await self._detect_spac_from_filings(symbol, sec_api_client)
                if spac_from_filings:
                    logger.info("de_spac_detected", symbol=symbol, former_name=spac_from_filings, method="filings")
                    return {
                        "is_spac": False,
                        "is_de_spac": True,
                        "confidence": 0.90,
                        "sic_code": sic_code,
                        "sic_description": sic_desc,
                        "former_spac_name": spac_from_filings,
                        "merger_date": None,
                        "reason": f"De-SPAC: Found SPAC filing '{spac_from_filings}'"
                    }
            
            return {
                "is_spac": False,
                "is_de_spac": False,
                "confidence": 1.0,
                "sic_code": sic_code,
                "sic_description": sic_desc,
                "reason": "Not a SPAC"
            }
            
        except Exception as e:
            logger.error("spac_detect_failed", symbol=symbol, error=str(e))
            return {
                "is_spac": False,
                "is_de_spac": False,
                "confidence": 0.0,
                "sic_code": None,
                "reason": f"Detection error: {str(e)}"
            }
    
    async def close(self):
        """Cierra el cliente HTTP"""
        await self._client.aclose()


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
        self.financials: Optional[FinancialsClient] = None
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
        self.financials = FinancialsClient()
        
        # SEC EDGAR (gratis, sin API key - para detección SPAC)
        self.sec_edgar = SECEdgarClient()
        
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
            self.financials,
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

