"""
Data Provider
Unified access to Redis, Scanner API, Polygon, and TimescaleDB

OPTIMIZACION: Usa cache local en memoria para evitar deserializar
JSON grandes de Redis en cada request.
"""

import json
import asyncio
from typing import Any, Dict, List, Optional
from datetime import datetime
import httpx
import structlog

import sys
sys.path.append('/app')

from shared.utils.redis_client import RedisClient
from shared.config.settings import settings

from .polygon_client import PolygonClient
from .timescale_client import AgentTimescaleClient

logger = structlog.get_logger(__name__)


class LocalCache:
    """
    Caché local en memoria para datos de mercado.
    Se actualiza periódicamente en background, no en cada request.
    
    Esto evita el cuello de botella de deserializar JSON grandes
    de Redis en cada consulta de usuario.
    """
    
    def __init__(self, ttl_seconds: float = 2.0):
        self.ttl = ttl_seconds
        self._data: Dict[str, List[Dict]] = {}
        self._timestamps: Dict[str, datetime] = {}
        self._lock = asyncio.Lock()
    
    def is_stale(self, key: str) -> bool:
        """Verifica si el cache está desactualizado"""
        if key not in self._timestamps:
            return True
        age = (datetime.now() - self._timestamps[key]).total_seconds()
        return age > self.ttl
    
    def get(self, key: str) -> Optional[List[Dict]]:
        """Obtiene datos del cache si no están stale"""
        if self.is_stale(key):
            return None
        return self._data.get(key)
    
    async def set(self, key: str, data: List[Dict]):
        """Actualiza el cache"""
        async with self._lock:
            self._data[key] = data
            self._timestamps[key] = datetime.now()
    
    def clear(self):
        """Limpia todo el cache"""
        self._data.clear()
        self._timestamps.clear()


class DataProvider:
    """
    Proveedor de datos unificado para el AI Agent.
    
    Fuentes soportadas:
    - scanner: Tickers filtrados del scanner
    - gappers_up, gappers_down, etc.: Categorías del scanner
    - snapshot: Snapshot completo del mercado
    - metadata:{symbol}: Metadata de un ticker específico
    """
    
    # Mapeo de categorías a endpoints
    CATEGORY_ENDPOINTS = {
        'gappers_up': '/api/categories/gappers_up',
        'gappers_down': '/api/categories/gappers_down',
        'momentum_up': '/api/categories/momentum_up',
        'momentum_down': '/api/categories/momentum_down',
        'anomalies': '/api/categories/anomalies',
        'high_volume': '/api/categories/high_volume',
        'new_highs': '/api/categories/new_highs',
        'new_lows': '/api/categories/new_lows',
        'winners': '/api/categories/winners',
        'losers': '/api/categories/losers',
        'reversals': '/api/categories/reversals',
        'post_market': '/api/categories/post_market',
    }
    
    def __init__(
        self,
        redis_client: RedisClient,
        scanner_base_url: str = "http://scanner:8005"
    ):
        """
        Inicializa el proveedor de datos.
        
        Args:
            redis_client: Cliente de Redis
            scanner_base_url: URL base del servicio scanner
        """
        self.redis = redis_client
        self.scanner_url = scanner_base_url
        self._http_client: Optional[httpx.AsyncClient] = None
        
        # Cache local para evitar deserializar JSON grandes en cada request
        self._cache = LocalCache(ttl_seconds=2.0)
        self._cache_update_task: Optional[asyncio.Task] = None
        
        # Clientes adicionales para datos historicos y SEC
        self._polygon: Optional[PolygonClient] = None
        self._timescale: Optional[AgentTimescaleClient] = None
    
    async def initialize(self):
        """Inicializa todos los clientes"""
        self._http_client = httpx.AsyncClient(timeout=30.0)
        
        # Iniciar background task para actualizar cache
        self._cache_update_task = asyncio.create_task(self._cache_updater_loop())
        logger.info("data_provider_cache_updater_started")
        
        # Inicializar Polygon client
        try:
            self._polygon = PolygonClient()
            logger.info("polygon_client_initialized")
        except Exception as e:
            logger.warning("polygon_client_init_failed", error=str(e))
        
        # Inicializar TimescaleDB client
        try:
            self._timescale = AgentTimescaleClient()
            await self._timescale.connect()
            logger.info("timescale_client_initialized")
        except Exception as e:
            logger.warning("timescale_client_init_failed", error=str(e))
    
    async def close(self):
        """Cierra el cliente HTTP y detiene el cache updater"""
        if self._cache_update_task:
            self._cache_update_task.cancel()
            try:
                await self._cache_update_task
            except asyncio.CancelledError:
                pass
        
        if self._http_client:
            await self._http_client.aclose()
    
    async def _cache_updater_loop(self):
        """
        Background task que actualiza el cache local periódicamente.
        Esto evita que cada request de usuario tenga que ir a Redis.
        """
        while True:
            try:
                # Actualizar scanner:filtered (fuente más usada)
                data = await self._fetch_scanner_filtered_from_redis()
                if data:
                    await self._cache.set('scanner', data)
                
                await asyncio.sleep(1.5)  # Actualizar cada 1.5 segundos
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("cache_updater_error", error=str(e))
                await asyncio.sleep(5)
    
    async def _fetch_scanner_filtered_from_redis(self) -> List[Dict[str, Any]]:
        """Obtiene datos de scanner:filtered directamente de Redis"""
        try:
            data = await self.redis.get(f"{settings.key_prefix_scanner}:filtered")
            if data:
                if isinstance(data, list):
                    return data
                elif isinstance(data, str):
                    return json.loads(data)
            return []
        except Exception as e:
            logger.error("error_fetching_scanner_from_redis", error=str(e))
            return []
    
    async def get_source_data(self, source: str) -> List[Dict[str, Any]]:
        """
        Obtiene datos de una fuente.
        
        Args:
            source: Nombre de la fuente
        
        Returns:
            Lista de diccionarios con los datos
        """
        logger.info("fetching_data", source=source)
        
        if source == 'scanner':
            return await self._get_scanner_filtered()
        
        elif source in self.CATEGORY_ENDPOINTS:
            return await self._get_category(source)
        
        elif source == 'snapshot':
            return await self._get_full_snapshot()
        
        elif source.startswith('metadata:'):
            symbol = source.split(':')[1]
            data = await self._get_ticker_metadata(symbol)
            return [data] if data else []
        
        else:
            logger.warning("unknown_source", source=source)
            return []
    
    async def _get_scanner_filtered(self) -> List[Dict[str, Any]]:
        """
        Obtiene tickers filtrados del scanner.
        
        OPTIMIZACIÓN: Usa caché local en memoria primero.
        El background task actualiza el cache cada 1.5 segundos.
        """
        # 1. Intentar desde caché local (sin deserialización)
        cached = self._cache.get('scanner')
        if cached is not None:
            return cached
        
        # 2. Fallback: ir a Redis directamente
        try:
            data = await self._fetch_scanner_filtered_from_redis()
            if data:
                await self._cache.set('scanner', data)
                return data
            
            # 3. Último recurso: llamar al API
            return await self._fetch_from_scanner('/api/scanner/filtered')
        
        except Exception as e:
            logger.error("error_getting_scanner_filtered", error=str(e))
            return []
    
    async def _get_category(self, category: str) -> List[Dict[str, Any]]:
        """Obtiene tickers de una categoria desde Redis o Scanner API"""
        try:
            # Intentar desde Redis primero
            redis_key = f"{settings.key_prefix_scanner}:categories:{category}"
            data = await self.redis.get(redis_key)
            
            if data:
                # Redis puede tener lista directa o dict con 'tickers'
                if isinstance(data, dict) and 'tickers' in data:
                    return data['tickers']
                elif isinstance(data, list):
                    return data
                elif isinstance(data, str):
                    parsed = json.loads(data)
                    if isinstance(parsed, dict) and 'tickers' in parsed:
                        return parsed['tickers']
                    return parsed if isinstance(parsed, list) else []
            
            # Fallback: llamar al API
            endpoint = self.CATEGORY_ENDPOINTS.get(category)
            if endpoint:
                response = await self._fetch_from_scanner(endpoint)
                # API devuelve {category, count, limit, tickers}
                if isinstance(response, dict) and 'tickers' in response:
                    return response['tickers']
                elif isinstance(response, list):
                    return response
                return []
            
            return []
        
        except Exception as e:
            logger.error("error_getting_category", category=category, error=str(e))
            return []
    
    async def _get_full_snapshot(self) -> List[Dict[str, Any]]:
        """Obtiene el snapshot completo del mercado"""
        try:
            # Leer desde stream de snapshots
            # El snapshot raw tiene ~11k tickers
            data = await self.redis.get("snapshots:latest")
            
            if data:
                if isinstance(data, dict) and 'tickers' in data:
                    return data['tickers']
                elif isinstance(data, list):
                    return data
            
            return []
        
        except Exception as e:
            logger.error("error_getting_snapshot", error=str(e))
            return []
    
    async def _get_ticker_metadata(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Obtiene metadata de un ticker específico"""
        try:
            redis_key = f"{settings.key_prefix_metadata}:{symbol}"
            data = await self.redis.get(redis_key)
            
            if data:
                return data if isinstance(data, dict) else json.loads(data)
            
            return None
        
        except Exception as e:
            logger.error("error_getting_metadata", symbol=symbol, error=str(e))
            return None
    
    async def _fetch_from_scanner(self, endpoint: str, params: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """Hace una llamada HTTP al servicio scanner"""
        try:
            if not self._http_client:
                await self.initialize()
            
            url = f"{self.scanner_url}{endpoint}"
            response = await self._http_client.get(url, params=params or {})
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(
                    "scanner_api_error",
                    endpoint=endpoint,
                    status=response.status_code
                )
                return []
        
        except Exception as e:
            logger.error("scanner_http_error", endpoint=endpoint, error=str(e))
            return []
    
    async def get_market_status(self) -> Dict[str, Any]:
        """Obtiene el estado actual del mercado"""
        try:
            data = await self.redis.get(f"{settings.key_prefix_market}:session:status")
            return data or {}
        except Exception as e:
            logger.error("error_getting_market_status", error=str(e))
            return {}
    
    async def get_category_stats(self) -> Dict[str, int]:
        """Obtiene estadisticas de categorias"""
        try:
            response = await self._fetch_from_scanner('/api/categories/stats')
            if isinstance(response, dict):
                return response
            return {}
        except Exception as e:
            logger.error("error_getting_category_stats", error=str(e))
            return {}
    
    # =============================================
    # POLYGON - DATOS HISTORICOS
    # =============================================
    
    async def get_bars(
        self,
        symbol: str,
        days: int = 5,
        timeframe: str = "1h"
    ) -> List[Dict[str, Any]]:
        """
        Obtiene barras OHLCV historicas desde Polygon.
        
        Args:
            symbol: Ticker symbol
            days: Dias hacia atras
            timeframe: 1min, 5min, 15min, 30min, 1h, 4h, 1d
        
        Returns:
            Lista de barras
        """
        if not self._polygon:
            logger.warning("polygon_not_available")
            return []
        
        return await self._polygon.get_bars(symbol, days, timeframe)
    
    async def get_ticker_details(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Obtiene detalles fundamentales desde Polygon"""
        if not self._polygon:
            return None
        return await self._polygon.get_ticker_details(symbol)
    
    # =============================================
    # TIMESCALE - SEC Y DILUCION
    # =============================================
    
    async def get_dilution_profile(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene perfil de dilucion completo.
        
        Incluye: warrants, ATMs, shelf registrations
        """
        if not self._timescale:
            logger.warning("timescale_not_available")
            return None
        
        return await self._timescale.get_dilution_profile(symbol)
    
    async def get_sec_filings(
        self,
        symbol: str,
        form_types: List[str] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Obtiene SEC filings de un ticker.
        
        Args:
            symbol: Ticker
            form_types: ['8-K', '10-K', 'S-1', etc.]
            limit: Max resultados
        """
        if not self._timescale:
            return []
        
        return await self._timescale.get_sec_filings(symbol, form_types, limit)
    
    async def get_warrants(self, symbol: str) -> List[Dict[str, Any]]:
        """Obtiene warrants de un ticker"""
        if not self._timescale:
            return []
        return await self._timescale.get_warrants(symbol)
    
    async def get_tickers_with_warrants(self) -> List[Dict[str, Any]]:
        """Obtiene tickers que tienen warrants activos"""
        if not self._timescale:
            return []
        return await self._timescale.get_tickers_with_warrants()
    
    async def get_tickers_with_atm(self) -> List[Dict[str, Any]]:
        """Obtiene tickers con ATM offerings activos"""
        if not self._timescale:
            return []
        return await self._timescale.get_tickers_with_atm()

