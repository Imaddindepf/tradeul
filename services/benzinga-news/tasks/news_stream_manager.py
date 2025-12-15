"""
Benzinga News Stream Manager

Gestiona el polling de Benzinga News y la integración con Redis:
- Polling periódico a la API
- Deduplicación de noticias
- Caché en Redis (noticias recientes + por ticker)
- Publicación a Redis streams para broadcast al frontend
- Detección de alertas de catalyst (movimientos + noticias)
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import structlog
import redis.asyncio as aioredis
from redis.asyncio import Redis

from .benzinga_client import BenzingaNewsClient
from .catalyst_alert_engine import CatalystAlertEngine
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
        poll_interval: int = 5,  # Segundos entre polls
        enable_catalyst_alerts: bool = True  # Habilitar sistema de alertas
    ):
        """
        Inicializa el manager
        
        Args:
            api_key: Polygon.io API key
            redis_client: Cliente Redis conectado
            poll_interval: Intervalo de polling en segundos
            enable_catalyst_alerts: Si debe detectar alertas de catalyst
        """
        self.api_key = api_key
        self.redis = redis_client
        self.poll_interval = poll_interval
        
        # Cliente de noticias
        self.news_client = BenzingaNewsClient(api_key)
        
        # Motor de alertas de catalyst (detecta movimientos, el frontend filtra)
        self.enable_catalyst_alerts = enable_catalyst_alerts
        self.catalyst_engine: Optional[CatalystAlertEngine] = None
        if enable_catalyst_alerts:
            self.catalyst_engine = CatalystAlertEngine(
                redis_client=redis_client,
                polygon_api_key=api_key
            )
        
        # Control de ejecución
        self._running = False
        self._poll_task: Optional[asyncio.Task] = None
        
        # Estadísticas
        self.stats = {
            "articles_processed": 0,
            "duplicates_skipped": 0,
            "catalyst_alerts": 0,
            "errors": 0,
            "polls_completed": 0,
            "started_at": None,
            "last_article_time": None
        }
        
        logger.info(
            "benzinga_news_stream_manager_initialized",
            catalyst_alerts=enable_catalyst_alerts
        )
    
    async def start(self):
        """
        Inicia el manager y comienza el polling
        """
        logger.info("Starting Benzinga News Stream Manager...")
        
        self.stats["started_at"] = datetime.now().isoformat()
        self._running = True
        
        # Iniciar motor de alertas de catalyst
        if self.catalyst_engine:
            # Registrar callback para alertas
            self.catalyst_engine.set_alert_callback(self._send_catalyst_alert)
            await self.catalyst_engine.start()
            logger.info("Catalyst Alert Engine started (WebSocket realtime mode)")
        
        # Iniciar task de polling
        self._poll_task = asyncio.create_task(self._polling_loop())
        
        logger.info("Benzinga News Stream Manager started")
    
    async def stop(self):
        """
        Detiene el manager
        """
        logger.info("Stopping Benzinga News Stream Manager...")
        
        self._running = False
        
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        
        # Detener motor de alertas
        if self.catalyst_engine:
            await self.catalyst_engine.stop()
        
        await self.news_client.close()
        
        logger.info("Benzinga News Stream Manager stopped")
    
    async def _polling_loop(self):
        """
        Loop principal de polling
        
        Estrategia: Siempre obtener las últimas N noticias ordenadas por fecha.
        La deduplicación en Redis evita procesar duplicados.
        Esto es más robusto que depender de filtros de fecha de la API.
        """
        logger.info(f"Starting polling loop (interval: {self.poll_interval}s)")
        
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
                        "Poll completed",
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
    
    async def _send_catalyst_alert(self, ticker: str, metrics: Dict[str, Any]):
        """
        Callback para enviar alertas de catalyst al stream.
        Llamado por el CatalystAlertEngine cuando detecta impacto real.
        """
        try:
            alert_payload = {
                "type": "catalyst_alert",
                "ticker": ticker,
                "metrics": json.dumps(metrics),
                "timestamp": datetime.now().isoformat()
            }
            
            await self.redis.xadd(
                self.STREAM_KEY,
                alert_payload,
                maxlen=2000
            )
            
            self.stats["catalyst_alerts"] += 1
            
            change = metrics.get('change_since_news_pct', 0)
            sign = "+" if change >= 0 else ""
            log_msg = (
                f"CATALYST ALERT | {ticker} | "
                f"{sign}{change:.1f}% in {metrics.get('seconds_since_news', 0)}s | "
                f"RVOL {metrics.get('rvol', 0):.1f}x"
            )
            print(log_msg, flush=True)
            
        except Exception as e:
            logger.error("send_catalyst_alert_error", error=str(e), ticker=ticker)
    
    async def _get_ticker_prices_fast(self, tickers: List[str]) -> Dict[str, float]:
        """
        Obtiene precios de tickers del snapshot en Redis.
        Operación rápida, no bloqueante (solo lectura de memoria).
        """
        prices = {}
        try:
            snapshot_data = await self.redis.get("snapshot:enriched:latest")
            if snapshot_data:
                snapshot = json.loads(snapshot_data if isinstance(snapshot_data, str) else snapshot_data.decode())
                tickers_list = snapshot.get("tickers", [])
                
                # Build lookup set for O(1) matching
                ticker_set = {t.upper() for t in tickers}
                
                for item in tickers_list:
                    ticker = item.get("ticker", "").upper()
                    if ticker in ticker_set:
                        price = item.get("current_price") or item.get("lastTrade", {}).get("p", 0)
                        if price:
                            prices[ticker] = float(price)
        except Exception as e:
            # Non-blocking: if we can't get prices, just continue without them
            logger.debug("get_prices_fast_error", error=str(e))
        
        return prices

    async def _publish_to_stream(self, article: BenzingaArticle):
        """
        Publica artículo a Redis Stream para broadcast.
        
        El motor de catalyst monitorea en tiempo real via WebSocket.
        Las alertas se envían via callback cuando detecta impacto real.
        """
        try:
            # Capturar precios actuales (no bloqueante, solo Redis)
            ticker_prices = {}
            if article.tickers:
                ticker_prices = await self._get_ticker_prices_fast(article.tickers[:5])
                
            # Iniciar monitoreo de catalyst para cada ticker
            if self.catalyst_engine and article.tickers:
                for ticker in article.tickers[:3]:  # Máximo 3 tickers por noticia
                    await self.catalyst_engine.process_news(
                            news_id=f"{article.benzinga_id}_{ticker}",
                            ticker=ticker,
                            title=article.title,
                            categories=article.channels or []
                        )
            
            # Publicar noticia al stream con precios
            stream_payload = {
                "type": "news",
                "data": article.model_dump_json(),
                "timestamp": datetime.now().isoformat()
            }
            
            # Añadir precios si los tenemos
            if ticker_prices:
                stream_payload["ticker_prices"] = json.dumps(ticker_prices)
            
            await self.redis.xadd(
                self.STREAM_KEY,
                stream_payload,
                maxlen=2000
            )
            
            # Log
            tickers_str = ','.join(article.tickers[:3]) if article.tickers else 'N/A'
            logger.debug(
                "news_published",
                tickers=tickers_str,
                title=article.title[:50],
                prices_captured=len(ticker_prices)
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
    
    async def get_stats(self) -> Dict[str, Any]:
        """Retorna estadísticas del manager"""
        stats = {
            "manager": self.stats,
            "client": self.news_client.get_stats()
        }
        
        # Añadir stats del motor de alertas
        if self.catalyst_engine:
            stats["catalyst_engine"] = await self.catalyst_engine.get_stats()
        
        return stats
    
    async def fill_cache(self, limit: int = 2000) -> Dict[str, Any]:
        """
        Llena el cache con las últimas N noticias de Polygon.
        
        Método simple y directo: un solo request con limit alto.
        
        Args:
            limit: Número de noticias a obtener (max 5000)
            
        Returns:
            Stats del fill
        """
        logger.info("fill_cache_starting", limit=limit)
        
        stats = {
            "total_fetched": 0,
            "new_articles": 0,
            "duplicates_skipped": 0,
            "errors": 0,
            "date_range": {}
        }
        
        try:
            # Un solo fetch con limit alto
            articles = await self.news_client.fetch_latest_news(limit=limit)
            stats["total_fetched"] = len(articles)
            
            if articles:
                stats["date_range"] = {
                    "newest": articles[0].published if articles else None,
                    "oldest": articles[-1].published if articles else None
                }
            
            logger.info(
                "fill_cache_fetched",
                count=len(articles),
                newest=stats["date_range"].get("newest"),
                oldest=stats["date_range"].get("oldest")
            )
            
            # Procesar todos (sin publicar al stream)
            for i, article in enumerate(articles):
                try:
                    processed = await self._process_article_silent(article)
                    if processed:
                        stats["new_articles"] += 1
                    else:
                        stats["duplicates_skipped"] += 1
                    
                    # Log progreso cada 500
                    if (i + 1) % 500 == 0:
                        logger.info(
                            "fill_cache_progress",
                            processed=i + 1,
                            total=len(articles),
                            new=stats["new_articles"]
                        )
                except Exception as e:
                    stats["errors"] += 1
                    logger.error("fill_cache_article_error", error=str(e))
            
            logger.info("fill_cache_completed", **stats)
            return {"success": True, **stats}
            
        except Exception as e:
            logger.error("fill_cache_error", error=str(e))
            stats["errors"] += 1
            return {"success": False, "error": str(e), **stats}
    
    async def _process_article_silent(self, article: BenzingaArticle) -> bool:
        """
        Procesa artículo sin publicar al stream (para fill/backfill).
        """
        try:
            article_id = str(article.benzinga_id)
            
            # 1. Deduplicación
            is_duplicate = await self._is_duplicate(article_id)
            if is_duplicate:
                return False
            
            # 2. Marcar como procesado
            await self._mark_as_processed(article_id)
            
            # 3. Guardar en cache latest
            await self._cache_in_latest(article)
            
            # 4. Guardar en cache por ticker
            for ticker in article.tickers or []:
                await self._cache_by_ticker(ticker, article)
            
            # NO publicar al stream
            return True
            
        except Exception as e:
            logger.error("process_article_silent_error", error=str(e))
            return False

