"""
Post-Market Volume Capture System

Sistema de captura de volumen de sesión regular para cálculo preciso de post-market volume.

ARQUITECTURA:
- Event-Driven: Reacciona a SESSION_CHANGED (MARKET_OPEN → POST_MARKET)
- Lazy Loading: Fetchea nuevos tickers bajo demanda durante post-market
- Parallel Fetch: Usa semaphore para control de concurrencia (50 concurrent)
- Multi-level Cache: memoria → Redis → API

FLUJO:
1. A las 16:00:01 ET (SESSION_CHANGED): Captura volumen regular de todos los tickers del scanner
2. Durante post-market: Lazy fetch para nuevos tickers que entran al scanner
3. Scanner usa regular_volume para calcular: postmarket_volume = current_volume - regular_volume

NOTA: Polygon day.v NO se congela a las 16:00, por lo que necesitamos sumar velas de minuto
para obtener el volumen exacto de la sesión regular (09:30-16:00 ET).
"""

import asyncio
import time
from datetime import datetime, timezone, date
from typing import Optional, Dict, List, Set, Any

import sys
sys.path.append('/app')

from shared.utils.redis_client import RedisClient
from shared.utils.logger import get_logger
from shared.config.settings import settings

logger = get_logger(__name__)


class PostMarketVolumeCapture:
    """
    Sistema de captura de volumen de sesión regular
    
    Patrones aplicados:
    - Event-Driven: reacciona a SESSION_CHANGED
    - Lazy Loading: fetchea nuevos tickers bajo demanda
    - Parallel Fetch: usa semaphore para control de concurrencia
    - Multi-level Cache: memoria → Redis → API
    """
    
    # Redis key prefixes
    REDIS_PREFIX = "scanner:postmarket"
    
    # Rate limiting
    MAX_CONCURRENT_REQUESTS = 50  # Plan avanzado de Polygon permite ~100 req/s
    REQUEST_TIMEOUT = 30.0
    MAX_RETRIES = 3
    RETRY_DELAY_BASE = 1.0  # Exponential backoff: 1s, 2s, 4s
    
    # Regular market hours in UTC (09:30-16:00 ET = 14:30-21:00 UTC)
    REGULAR_HOURS_START_UTC = 14.5   # 14:30 UTC
    REGULAR_HOURS_END_UTC = 21.0     # 21:00 UTC
    
    def __init__(
        self,
        redis_client: RedisClient,
        polygon_client: 'PolygonAggregatesClient',
        max_concurrent: int = MAX_CONCURRENT_REQUESTS
    ):
        """
        Inicializa el sistema de captura
        
        Args:
            redis_client: Cliente de Redis para cache persistente
            polygon_client: Cliente HTTP para Polygon API
            max_concurrent: Máximo de requests concurrentes a Polygon
        """
        self.redis = redis_client
        self.polygon = polygon_client
        self.semaphore = asyncio.Semaphore(max_concurrent)
        
        # Local cache (fastest access, cleared on day change)
        self._local_cache: Dict[str, int] = {}
        
        # Set de símbolos capturados (para lazy loading detection)
        self._captured_symbols: Set[str] = set()
        
        # Trading date actual (se actualiza en cada captura)
        self._trading_date: Optional[str] = None
        
        # Stats
        self._stats = {
            'initial_capture_count': 0,
            'lazy_fetch_count': 0,
            'cache_hits': 0,
            'api_calls': 0,
            'errors': 0
        }
        
        logger.info(
            "postmarket_capture_initialized",
            max_concurrent=max_concurrent
        )
    
    # =========================================================================
    # PUBLIC API
    # =========================================================================
    
    async def on_session_changed_to_postmarket(
        self,
        symbols: List[str],
        trading_date: str
    ) -> Dict[str, int]:
        """
        Handler principal: Captura volumen regular cuando el mercado cierra
        
        Se ejecuta UNA VEZ a las ~16:00:01 ET cuando SESSION_CHANGED detecta
        la transición MARKET_OPEN → POST_MARKET.
        
        Args:
            symbols: Lista de símbolos actualmente en el scanner
            trading_date: Fecha de trading (YYYY-MM-DD)
        
        Returns:
            Dict[symbol, regular_volume] para todos los símbolos capturados
        """
        logger.info(
            "🌙 postmarket_capture_starting",
            symbols_count=len(symbols),
            trading_date=trading_date
        )
        
        # Actualizar fecha de trading y limpiar cache del día anterior
        if self._trading_date != trading_date:
            self._clear_local_cache()
            self._trading_date = trading_date
        
        start_time = time.time()
        
        # Capturar en paralelo con semaphore
        results = await self._capture_batch_parallel(symbols, trading_date)
        
        # Actualizar stats
        success_count = sum(1 for v in results.values() if v is not None)
        self._stats['initial_capture_count'] = success_count
        
        duration = time.time() - start_time
        
        logger.info(
            "✅ postmarket_capture_completed",
            total_symbols=len(symbols),
            success_count=success_count,
            failed_count=len(symbols) - success_count,
            duration_sec=round(duration, 2),
            symbols_per_second=round(len(symbols) / duration, 1) if duration > 0 else 0
        )
        
        return results
    
    async def get_regular_volume(self, symbol: str) -> Optional[int]:
        """
        Obtiene el volumen de la sesión regular de un símbolo
        
        Orden de búsqueda:
        1. Local cache (fastest)
        2. Redis cache
        3. API lazy fetch (para nuevos tickers)
        
        Args:
            symbol: Símbolo del ticker
        
        Returns:
            Volumen de la sesión regular (09:30-16:00 ET) o None si no disponible
        """
        if not self._trading_date:
            logger.warning("get_regular_volume_no_trading_date", symbol=symbol)
            return None
        
        # 1. Local cache (fastest)
        if symbol in self._local_cache:
            self._stats['cache_hits'] += 1
            return self._local_cache[symbol]
        
        # 2. Redis cache
        redis_key = self._get_redis_key(symbol)
        try:
            cached = await self.redis.get(redis_key)
            if cached is not None:
                volume = int(cached)
                self._local_cache[symbol] = volume
                self._captured_symbols.add(symbol)
                self._stats['cache_hits'] += 1
                return volume
        except Exception as e:
            logger.error("redis_get_error", symbol=symbol, error=str(e))
        
        # 3. Lazy fetch desde API (nuevo ticker entrando al scanner)
        if symbol not in self._captured_symbols:
            logger.info(
                "🔄 lazy_fetch_new_ticker",
                symbol=symbol,
                reason="not_in_captured_symbols"
            )
            
            volume = await self._fetch_single_volume(symbol)
            
            if volume is not None:
                self._local_cache[symbol] = volume
                self._captured_symbols.add(symbol)
                self._stats['lazy_fetch_count'] += 1
                
                # Guardar en Redis
                await self._save_to_redis(symbol, volume)
                
                return volume
        
        return None
    
    async def is_symbol_captured(self, symbol: str) -> bool:
        """Verifica si un símbolo ya tiene volumen regular capturado"""
        if symbol in self._captured_symbols:
            return True
        
        # Verificar en Redis
        redis_key = self._get_redis_key(symbol)
        try:
            exists = await self.redis.client.exists(redis_key)
            if exists:
                self._captured_symbols.add(symbol)
                return True
        except Exception:
            pass
        
        return False
    
    def set_trading_date(self, trading_date: str) -> None:
        """
        Establece la fecha de trading (llamado desde main.py al recibir SESSION_CHANGED)
        
        Args:
            trading_date: Fecha en formato YYYY-MM-DD
        """
        if self._trading_date != trading_date:
            logger.info(
                "trading_date_changed",
                old_date=self._trading_date,
                new_date=trading_date
            )
            self._clear_local_cache()
            self._trading_date = trading_date
    
    def clear_for_new_day(self) -> None:
        """Limpia cache local para nuevo día de trading"""
        self._clear_local_cache()
        logger.info("postmarket_cache_cleared_for_new_day")
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estadísticas del sistema"""
        return {
            **self._stats,
            'local_cache_size': len(self._local_cache),
            'captured_symbols_count': len(self._captured_symbols),
            'trading_date': self._trading_date
        }
    
    # =========================================================================
    # INTERNAL METHODS
    # =========================================================================
    
    async def _capture_batch_parallel(
        self,
        symbols: List[str],
        trading_date: str
    ) -> Dict[str, int]:
        """
        Captura volumen regular para un batch de símbolos en paralelo
        
        Usa asyncio.gather con semaphore para controlar concurrencia
        """
        async def capture_with_semaphore(symbol: str) -> tuple:
            """Wrapper para controlar concurrencia"""
            async with self.semaphore:
                volume = await self._fetch_single_volume_with_retry(symbol, trading_date)
                return (symbol, volume)
        
        # Ejecutar todas las tareas en paralelo
        tasks = [capture_with_semaphore(symbol) for symbol in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Procesar resultados
        volumes: Dict[str, int] = {}
        
        for result in results:
            if isinstance(result, Exception):
                logger.error("batch_capture_exception", error=str(result))
                self._stats['errors'] += 1
                continue
            
            symbol, volume = result
            if volume is not None:
                volumes[symbol] = volume
                self._local_cache[symbol] = volume
                self._captured_symbols.add(symbol)
                
                # Guardar en Redis (fire-and-forget para no bloquear)
                asyncio.create_task(self._save_to_redis(symbol, volume))
        
        return volumes
    
    async def _fetch_single_volume_with_retry(
        self,
        symbol: str,
        trading_date: Optional[str] = None
    ) -> Optional[int]:
        """
        Fetch con retry y exponential backoff
        """
        date_to_use = trading_date or self._trading_date
        if not date_to_use:
            return None
        
        for attempt in range(self.MAX_RETRIES):
            try:
                volume = await self._fetch_single_volume(symbol, date_to_use)
                return volume
            
            except Exception as e:
                delay = self.RETRY_DELAY_BASE * (2 ** attempt)
                
                if attempt < self.MAX_RETRIES - 1:
                    logger.warning(
                        "fetch_retry",
                        symbol=symbol,
                        attempt=attempt + 1,
                        delay=delay,
                        error=str(e)
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "fetch_failed_all_retries",
                        symbol=symbol,
                        attempts=self.MAX_RETRIES,
                        error=str(e)
                    )
                    self._stats['errors'] += 1
        
        return None
    
    async def _fetch_single_volume(
        self,
        symbol: str,
        trading_date: Optional[str] = None
    ) -> Optional[int]:
        """
        Fetch volumen de sesión regular desde Polygon Aggregates API
        
        Llama a: GET /v2/aggs/ticker/{symbol}/range/1/minute/{date}/{date}
        Filtra velas de 09:30-16:00 ET y suma volúmenes
        """
        date_to_use = trading_date or self._trading_date
        if not date_to_use:
            return None
        
        self._stats['api_calls'] += 1
        
        try:
            # Llamar a Polygon API
            bars = await self.polygon.get_minute_aggregates(symbol, date_to_use)
            
            if not bars:
                logger.debug("no_bars_returned", symbol=symbol, date=date_to_use)
                return 0
            
            # Sumar volumen de horas regulares
            regular_volume = self._sum_regular_hours_volume(bars)
            
            logger.debug(
                "volume_fetched",
                symbol=symbol,
                bars_count=len(bars),
                regular_volume=regular_volume
            )
            
            return regular_volume
        
        except Exception as e:
            logger.error(
                "polygon_aggregates_error",
                symbol=symbol,
                date=date_to_use,
                error=str(e)
            )
            raise
    
    def _sum_regular_hours_volume(self, bars: List[Dict]) -> int:
        """
        Suma volumen de velas entre 09:30-16:00 ET (14:30-21:00 UTC)
        
        IMPORTANTE: Las velas de Polygon tienen timestamp al INICIO de la vela.
        - Vela de 14:30 UTC contiene datos de 14:30-14:31
        - Vela de 20:59 UTC contiene datos de 20:59-21:00 (última de regular hours)
        
        Args:
            bars: Lista de velas de 1 minuto desde Polygon
        
        Returns:
            Suma de volúmenes de la sesión regular
        """
        total_volume = 0
        
        for bar in bars:
            timestamp_ms = bar.get('t', 0)
            if not timestamp_ms:
                continue
            
            # Convertir a datetime UTC
            ts = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
            hour_decimal = ts.hour + ts.minute / 60
            
            # Filtrar horas regulares: 14:30 - 21:00 UTC = 09:30 - 16:00 ET
            # Nota: incluimos hasta 20:59 porque es la última vela que termina a las 21:00
            if self.REGULAR_HOURS_START_UTC <= hour_decimal < self.REGULAR_HOURS_END_UTC:
                volume = bar.get('v', 0)
                if volume:
                    total_volume += int(volume)
        
        return total_volume
    
    async def _save_to_redis(self, symbol: str, volume: int) -> None:
        """Guarda volumen en Redis con TTL de 24 horas"""
        redis_key = self._get_redis_key(symbol)
        try:
            await self.redis.set(redis_key, volume, ex=86400)  # TTL 24 horas
        except Exception as e:
            logger.error("redis_save_error", symbol=symbol, error=str(e))
    
    def _get_redis_key(self, symbol: str) -> str:
        """Genera key de Redis para un símbolo"""
        date_str = self._trading_date or datetime.now().strftime('%Y%m%d')
        # Formato: scanner:postmarket:regular_vol:20260105:NVDA
        return f"{self.REDIS_PREFIX}:regular_vol:{date_str.replace('-', '')}:{symbol}"
    
    def _clear_local_cache(self) -> None:
        """Limpia cache local"""
        self._local_cache.clear()
        self._captured_symbols.clear()
        self._stats = {
            'initial_capture_count': 0,
            'lazy_fetch_count': 0,
            'cache_hits': 0,
            'api_calls': 0,
            'errors': 0
        }


class PolygonAggregatesClient:
    """
    Cliente HTTP dedicado para Polygon Aggregates API
    
    Separado del cliente general para mejor control de rate limiting
    y connection pooling específico para este caso de uso.
    """
    
    BASE_URL = "https://api.polygon.io"
    
    def __init__(self, api_key: str, timeout: float = 30.0):
        import httpx
        
        self.api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=timeout,
            limits=httpx.Limits(
                max_connections=100,
                max_keepalive_connections=50,
                keepalive_expiry=30.0
            ),
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
            limit: Máximo de velas a retornar (default 50000)
        
        Returns:
            Lista de velas con estructura: [{t, o, h, l, c, v, vw, n}, ...]
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
    
    async def close(self) -> None:
        """Cierra el cliente HTTP"""
        await self._client.aclose()
        logger.info("polygon_aggregates_client_closed")

