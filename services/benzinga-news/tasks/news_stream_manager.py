"""
Benzinga News Stream Manager

Gestiona el polling de Benzinga News y la integración con Redis:
- Polling periódico a la API
- Deduplicación de noticias
- Caché en Redis (noticias recientes + por ticker)
- Publicación a Redis streams para broadcast al frontend
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import structlog
import redis.asyncio as aioredis
from redis.asyncio import Redis

from .benzinga_client import BenzingaNewsClient
from models.news import BenzingaArticle

logger = structlog.get_logger(__name__)


class BenzingaNewsStreamManager:
    """
    Gestiona el flujo de noticias desde Benzinga API a Redis
    Similar a SECStreamManager pero con polling en lugar de WebSocket
    """
    
    # Redis keys
    STREAM_KEY = "stream:benzinga:news"  # Stream para broadcast
    CACHE_LATEST_KEY = "cache:benzinga:news:latest"  # Últimas noticias
    CACHE_BY_TICKER_PREFIX = "cache:benzinga:news:ticker:"  # Noticias por ticker
    DEDUP_SET_KEY = "dedup:benzinga:news"  # Set para deduplicación
    LAST_POLL_KEY = "benzinga:news:last_poll"  # Timestamp del último poll
    
    # Configuración
    CACHE_LATEST_SIZE = 2000  # Mantener últimas 2000 noticias
    CACHE_BY_TICKER_SIZE = 500  # Últimas 500 noticias por ticker
    DEDUP_TTL = 86400 * 7  # 7 días para deduplicación
    
    def __init__(
        self,
        api_key: str,
        redis_client: Redis,
        poll_interval: int = 5  # Segundos entre polls
    ):
        """
        Inicializa el manager
        
        Args:
            api_key: Polygon.io API key
            redis_client: Cliente Redis conectado
            poll_interval: Intervalo de polling en segundos
        """
        self.api_key = api_key
        self.redis = redis_client
        self.poll_interval = poll_interval
        
        # Cliente de noticias
        self.news_client = BenzingaNewsClient(api_key)
        
        # Control de ejecución
        self._running = False
        self._poll_task: Optional[asyncio.Task] = None
        
        # Estadísticas
        self.stats = {
            "articles_processed": 0,
            "duplicates_skipped": 0,
            "errors": 0,
            "polls_completed": 0,
            "started_at": None,
            "last_article_time": None
        }
        
        logger.info("benzinga_news_stream_manager_initialized")
    
    async def start(self):
        """
        Inicia el manager y comienza el polling
        """
        logger.info("🚀 Starting Benzinga News Stream Manager...")
        
        self.stats["started_at"] = datetime.now().isoformat()
        self._running = True
        
        # Iniciar task de polling
        self._poll_task = asyncio.create_task(self._polling_loop())
        
        logger.info("✅ Benzinga News Stream Manager started")
    
    async def stop(self):
        """
        Detiene el manager
        """
        logger.info("🛑 Stopping Benzinga News Stream Manager...")
        
        self._running = False
        
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        
        await self.news_client.close()
        
        logger.info("✅ Benzinga News Stream Manager stopped")
    
    async def _polling_loop(self):
        """
        Loop principal de polling
        
        Estrategia: Siempre obtener las últimas N noticias ordenadas por fecha.
        La deduplicación en Redis evita procesar duplicados.
        Esto es más robusto que depender de filtros de fecha de la API.
        """
        logger.info(f"📰 Starting polling loop (interval: {self.poll_interval}s)")
        
        while self._running:
            try:
                # Siempre obtener las últimas noticias (la deduplicación filtra duplicados)
                articles = await self.news_client.fetch_latest_news(limit=50)
                
                # Procesar artículos
                new_articles = 0
                for article in articles:
                    processed = await self._process_article(article)
                    if processed:
                        new_articles += 1
                        self.stats["last_article_time"] = article.published
                
                self.stats["polls_completed"] += 1
                
                if new_articles > 0:
                    logger.info(
                        "📰 Poll completed",
                        new_articles=new_articles,
                        total_fetched=len(articles),
                        polls_completed=self.stats["polls_completed"]
                    )
                
            except Exception as e:
                logger.error("polling_error", error=str(e))
                self.stats["errors"] += 1
            
            # Esperar antes del siguiente poll
            await asyncio.sleep(self.poll_interval)
    
    async def _process_article(self, article: BenzingaArticle) -> bool:
        """
        Procesa un artículo de noticias
        
        Args:
            article: Artículo a procesar
            
        Returns:
            True si se procesó (no era duplicado), False si era duplicado
        """
        try:
            article_id = str(article.benzinga_id)
            
            # 1. Deduplicación
            is_duplicate = await self._is_duplicate(article_id)
            if is_duplicate:
                self.stats["duplicates_skipped"] += 1
                return False
            
            # 2. Marcar como procesado
            await self._mark_as_processed(article_id)
            
            # 3. Guardar en cache latest
            await self._cache_in_latest(article)
            
            # 4. Guardar en cache por ticker
            for ticker in article.tickers or []:
                await self._cache_by_ticker(ticker, article)
            
            # 5. Publicar a Redis Stream para broadcast
            await self._publish_to_stream(article)
            
            self.stats["articles_processed"] += 1
            
            logger.debug(
                "✨ Article processed",
                benzinga_id=article.benzinga_id,
                title=article.title[:50],
                tickers=article.tickers
            )
            
            return True
            
        except Exception as e:
            logger.error("article_processing_error", error=str(e))
            self.stats["errors"] += 1
            return False
    
    async def _is_duplicate(self, article_id: str) -> bool:
        """Verifica si un artículo ya fue procesado"""
        result = await self.redis.sismember(self.DEDUP_SET_KEY, article_id)
        return bool(result)
    
    async def _mark_as_processed(self, article_id: str):
        """Marca un artículo como procesado"""
        await self.redis.sadd(self.DEDUP_SET_KEY, article_id)
    
    async def _cache_in_latest(self, article: BenzingaArticle):
        """Guarda artículo en cache de 'latest'"""
        try:
            # Usar published timestamp como score
            published = article.published
            if published:
                try:
                    dt = datetime.fromisoformat(published.replace('Z', '+00:00'))
                    score = dt.timestamp()
                except:
                    score = datetime.now().timestamp()
            else:
                score = datetime.now().timestamp()
            
            # ZADD
            await self.redis.zadd(
                self.CACHE_LATEST_KEY,
                {article.model_dump_json(): score}
            )
            
            # Trim
            await self.redis.zremrangebyrank(
                self.CACHE_LATEST_KEY,
                0,
                -(self.CACHE_LATEST_SIZE + 1)
            )
            
        except Exception as e:
            logger.error("cache_latest_error", error=str(e))
    
    async def _cache_by_ticker(self, ticker: str, article: BenzingaArticle):
        """Guarda artículo en cache por ticker"""
        try:
            key = f"{self.CACHE_BY_TICKER_PREFIX}{ticker.upper()}"
            
            # Score
            published = article.published
            if published:
                try:
                    dt = datetime.fromisoformat(published.replace('Z', '+00:00'))
                    score = dt.timestamp()
                except:
                    score = datetime.now().timestamp()
            else:
                score = datetime.now().timestamp()
            
            # ZADD
            await self.redis.zadd(
                key,
                {article.model_dump_json(): score}
            )
            
            # Trim
            await self.redis.zremrangebyrank(
                key,
                0,
                -(self.CACHE_BY_TICKER_SIZE + 1)
            )
            
            # TTL de 7 días
            await self.redis.expire(key, 604800)
            
        except Exception as e:
            logger.error("cache_by_ticker_error", error=str(e), ticker=ticker)
    
    async def _publish_to_stream(self, article: BenzingaArticle):
        """Publica artículo a Redis Stream para broadcast"""
        try:
            stream_payload = {
                "type": "news",
                "data": article.model_dump_json(),
                "timestamp": datetime.now().isoformat()
            }
            
            await self.redis.xadd(
                self.STREAM_KEY,
                stream_payload,
                maxlen=2000
            )
            
            logger.debug(
                "article_published_to_stream",
                benzinga_id=article.benzinga_id
            )
            
        except Exception as e:
            logger.error("publish_to_stream_error", error=str(e))
    
    async def _get_last_poll_time(self) -> Optional[str]:
        """Obtiene el timestamp del último poll"""
        result = await self.redis.get(self.LAST_POLL_KEY)
        if result:
            return result.decode() if isinstance(result, bytes) else result
        return None
    
    async def _set_last_poll_time(self, timestamp: str):
        """Guarda el timestamp del último poll"""
        await self.redis.set(self.LAST_POLL_KEY, timestamp)
    
    async def get_latest_news(self, count: int = 100) -> List[Dict[str, Any]]:
        """Obtiene las últimas N noticias del cache"""
        try:
            results = await self.redis.zrevrange(
                self.CACHE_LATEST_KEY,
                0,
                count - 1,
                withscores=False
            )
            
            articles = []
            for result in results:
                try:
                    article = json.loads(result)
                    articles.append(article)
                except json.JSONDecodeError:
                    continue
            
            return articles
            
        except Exception as e:
            logger.error("get_latest_news_error", error=str(e))
            return []
    
    async def get_news_by_ticker(self, ticker: str, count: int = 50) -> List[Dict[str, Any]]:
        """Obtiene noticias para un ticker específico"""
        try:
            key = f"{self.CACHE_BY_TICKER_PREFIX}{ticker.upper()}"
            
            results = await self.redis.zrevrange(
                key,
                0,
                count - 1,
                withscores=False
            )
            
            articles = []
            for result in results:
                try:
                    article = json.loads(result)
                    articles.append(article)
                except json.JSONDecodeError:
                    continue
            
            return articles
            
        except Exception as e:
            logger.error("get_news_by_ticker_error", error=str(e), ticker=ticker)
            return []
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estadísticas del manager"""
        return {
            "manager": self.stats,
            "client": self.news_client.get_stats()
        }

