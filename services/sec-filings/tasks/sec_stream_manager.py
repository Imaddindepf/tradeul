"""
SEC Stream Manager

Gestiona el WebSocket de SEC Stream API y la integración con Redis:
- Conexión al WebSocket
- Deduplicación de filings
- Caché en Redis (filings recientes + por ticker)
- Publicación a Redis streams para broadcast al frontend
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import structlog
import redis.asyncio as aioredis
from redis.asyncio import Redis

from .sec_stream_ws_client import SECStreamWebSocketClient

logger = structlog.get_logger(__name__)


class SECStreamManager:
    """
    Gestiona el flujo de filings desde SEC Stream API a Redis
    """
    
    # Redis keys
    STREAM_KEY = "stream:sec:filings"  # Stream para broadcast
    CACHE_LATEST_KEY = "cache:sec:filings:latest"  # Últimos 100 filings
    CACHE_BY_TICKER_PREFIX = "cache:sec:filings:ticker:"  # Filings por ticker
    DEDUP_SET_KEY = "dedup:sec:filings"  # Set para deduplicación
    
    # TTLs
    CACHE_LATEST_SIZE = 500  # Mantener últimos 500 filings en cache
    CACHE_BY_TICKER_SIZE = 100  # Últimos 100 filings por ticker
    DEDUP_TTL = 86400  # 24 horas para deduplicación
    
    def __init__(
        self,
        sec_api_key: str,
        redis_client: Redis,
        stream_url: str = "wss://stream.sec-api.io"
    ):
        """
        Inicializa el manager
        
        Args:
            sec_api_key: SEC API key
            redis_client: Cliente Redis conectado
            stream_url: URL del WebSocket
        """
        self.sec_api_key = sec_api_key
        self.redis = redis_client
        self.stream_url = stream_url
        
        # Cliente WebSocket
        self.ws_client: Optional[SECStreamWebSocketClient] = None
        
        # Estadísticas
        self.stats = {
            "filings_processed": 0,
            "duplicates_skipped": 0,
            "errors": 0,
            "started_at": None
        }
        
        logger.info("sec_stream_manager_initialized")
    
    async def start(self):
        """
        Inicia el manager y conecta al WebSocket
        """
        logger.info("🚀 Starting SEC Stream Manager...")
        
        self.stats["started_at"] = datetime.now().isoformat()
        
        # Crear cliente WebSocket
        self.ws_client = SECStreamWebSocketClient(
            api_key=self.sec_api_key,
            stream_url=self.stream_url,
            on_filing=self._on_filing_received,
            max_reconnect_attempts=999,  # Intentar reconectar indefinidamente
            reconnect_delay=5
        )
        
        # Conectar (blocking)
        await self.ws_client.connect()
    
    async def stop(self):
        """
        Detiene el manager y cierra conexiones
        """
        logger.info("🛑 Stopping SEC Stream Manager...")
        
        if self.ws_client:
            await self.ws_client.close()
        
        logger.info("✅ SEC Stream Manager stopped")
    
    async def _on_filing_received(self, filing_data: Dict[str, Any]):
        """
        Callback cuando se recibe un filing del WebSocket
        
        Args:
            filing_data: Datos completos del filing
        """
        try:
            accession_no = filing_data.get("accessionNo")
            ticker = filing_data.get("ticker")
            form_type = filing_data.get("formType")
            
            if not accession_no:
                logger.warning("filing_missing_accession_no", filing_data=filing_data)
                return
            
            # 1. Deduplicación: verificar si ya procesamos este filing
            is_duplicate = await self._is_duplicate(accession_no)
            if is_duplicate:
                self.stats["duplicates_skipped"] += 1
                logger.debug("duplicate_filing_skipped", accession_no=accession_no)
                return
            
            # 2. Marcar como procesado
            await self._mark_as_processed(accession_no)
            
            # 3. Guardar en cache latest (ZSET ordenado por timestamp)
            await self._cache_in_latest(filing_data)
            
            # 4. Guardar en cache por ticker (si tiene ticker)
            if ticker:
                await self._cache_by_ticker(ticker, filing_data)
            
            # 5. Publicar a Redis Stream para broadcast al frontend
            await self._publish_to_stream(filing_data)
            
            self.stats["filings_processed"] += 1
            
            logger.info(
                "✨ Filing processed",
                accession_no=accession_no,
                ticker=ticker or "N/A",
                form_type=form_type,
                total_processed=self.stats["filings_processed"]
            )
            
        except Exception as e:
            logger.error("filing_processing_error", error=str(e), filing_data=filing_data)
            self.stats["errors"] += 1
    
    async def _is_duplicate(self, accession_no: str) -> bool:
        """
        Verifica si un filing ya fue procesado
        
        Args:
            accession_no: Accession number del filing
            
        Returns:
            True si es duplicado, False si no
        """
        # Usar SISMEMBER para verificación O(1)
        result = await self.redis.sismember(self.DEDUP_SET_KEY, accession_no)
        return bool(result)
    
    async def _mark_as_processed(self, accession_no: str):
        """
        Marca un filing como procesado para deduplicación
        
        Args:
            accession_no: Accession number del filing
        """
        # Agregar al set de deduplicación
        await self.redis.sadd(self.DEDUP_SET_KEY, accession_no)
        # TTL deslizante sobre el set completo: la "limpieza periódica"
        # prometida no existía y el set crecía indefinidamente en Redis.
        await self.redis.expire(self.DEDUP_SET_KEY, self.DEDUP_TTL)
    
    async def _cache_in_latest(self, filing_data: Dict[str, Any]):
        """
        Guarda filing en cache de "latest" usando ZADD
        
        Args:
            filing_data: Datos del filing
        """
        try:
            # Usar filed_at como score para ordenamiento
            filed_at = filing_data.get("filedAt", "")
            
            # Convertir ISO timestamp a Unix timestamp
            if filed_at:
                dt = datetime.fromisoformat(filed_at.replace('Z', '+00:00'))
                score = dt.timestamp()
            else:
                score = datetime.now().timestamp()
            
            # ZADD con score = timestamp
            await self.redis.zadd(
                self.CACHE_LATEST_KEY,
                {json.dumps(filing_data): score}
            )
            
            # Mantener solo los últimos N filings (trim)
            await self.redis.zremrangebyrank(
                self.CACHE_LATEST_KEY,
                0,
                -(self.CACHE_LATEST_SIZE + 1)
            )
            
        except Exception as e:
            logger.error("cache_latest_error", error=str(e))
    
    async def _cache_by_ticker(self, ticker: str, filing_data: Dict[str, Any]):
        """
        Guarda filing en cache por ticker usando ZADD
        
        Args:
            ticker: Ticker symbol
            filing_data: Datos del filing
        """
        try:
            key = f"{self.CACHE_BY_TICKER_PREFIX}{ticker.upper()}"
            
            # Usar filed_at como score
            filed_at = filing_data.get("filedAt", "")
            if filed_at:
                dt = datetime.fromisoformat(filed_at.replace('Z', '+00:00'))
                score = dt.timestamp()
            else:
                score = datetime.now().timestamp()
            
            # ZADD
            await self.redis.zadd(
                key,
                {json.dumps(filing_data): score}
            )
            
            # Mantener solo últimos N filings por ticker
            await self.redis.zremrangebyrank(
                key,
                0,
                -(self.CACHE_BY_TICKER_SIZE + 1)
            )
            
            # TTL de 7 días
            await self.redis.expire(key, 604800)
            
        except Exception as e:
            logger.error("cache_by_ticker_error", error=str(e), ticker=ticker)
    
    async def _publish_to_stream(self, filing_data: Dict[str, Any]):
        """
        Publica filing a Redis Stream para broadcast al frontend
        
        Args:
            filing_data: Datos del filing
        """
        try:
            # Preparar payload para stream
            stream_payload = {
                "type": "filing",
                "data": json.dumps(filing_data),
                "timestamp": datetime.now().isoformat()
            }
            
            # XADD al stream
            await self.redis.xadd(
                self.STREAM_KEY,
                stream_payload,
                maxlen=1000  # Mantener últimos 1000 eventos
            )
            
            logger.debug(
                "filing_published_to_stream",
                accession_no=filing_data.get("accessionNo"),
                ticker=filing_data.get("ticker")
            )
            
        except Exception as e:
            logger.error("publish_to_stream_error", error=str(e))
    
    async def get_latest_filings(self, count: int = 100) -> list:
        """
        Obtiene los últimos N filings del cache
        
        Args:
            count: Cantidad de filings a obtener
            
        Returns:
            Lista de filings (más recientes primero)
        """
        try:
            # ZREVRANGE: obtener por score (más reciente primero)
            results = await self.redis.zrevrange(
                self.CACHE_LATEST_KEY,
                0,
                count - 1,
                withscores=False
            )
            
            # Parsear JSON
            filings = []
            for result in results:
                try:
                    filing = json.loads(result)
                    filings.append(filing)
                except json.JSONDecodeError:
                    continue
            
            return filings
            
        except Exception as e:
            logger.error("get_latest_filings_error", error=str(e))
            return []
    
    async def get_filings_by_ticker(self, ticker: str, count: int = 100) -> list:
        """
        Obtiene filings para un ticker específico
        
        Args:
            ticker: Ticker symbol
            count: Cantidad de filings a obtener
            
        Returns:
            Lista de filings (más recientes primero)
        """
        try:
            key = f"{self.CACHE_BY_TICKER_PREFIX}{ticker.upper()}"
            
            # ZREVRANGE
            results = await self.redis.zrevrange(
                key,
                0,
                count - 1,
                withscores=False
            )
            
            # Parsear JSON
            filings = []
            for result in results:
                try:
                    filing = json.loads(result)
                    filings.append(filing)
                except json.JSONDecodeError:
                    continue
            
            return filings
            
        except Exception as e:
            logger.error("get_filings_by_ticker_error", error=str(e), ticker=ticker)
            return []
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Obtiene estadísticas del manager
        
        Returns:
            Diccionario con estadísticas
        """
        ws_stats = self.ws_client.get_stats() if self.ws_client else {}
        
        return {
            "manager": self.stats,
            "websocket": ws_stats
        }



