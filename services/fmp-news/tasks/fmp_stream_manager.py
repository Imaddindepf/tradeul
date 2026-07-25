"""
FMP News Stream Manager

Un poller por feed de FMP. Cada artículo nuevo se:
  1. Deduplica en Redis (set dedup:fmp:news, ID = hash de URL)
  2. Cachea en la cache unificada de noticias (las mismas keys que sirve
     GET /api/v1/news del servicio de news, nombre "benzinga" por herencia)
  3. Cachea en cache:fmp:news:reuters si el publisher es Reuters (Top News)
  4. Publica en el stream unificado stream:benzinga:news -> websocket_server
     -> frontend en tiempo real

El primer poll de cada feed es bootstrap: solo cachea (no publica al stream)
para no inundar el feed live al arrancar el servicio.
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

import httpx
import structlog

from models.news import FMPArticle

logger = structlog.get_logger(__name__)


@dataclass
class FeedConfig:
    name: str            # nombre interno (stats/logs)
    path: str            # path relativo al base URL de FMP
    channel: str         # tag que viaja en article.channels (filtro de la UI)
    interval: int        # segundos entre polls
    is_fmp_articles: bool = False  # formato distinto (/fmp-articles)
    stats: Dict[str, Any] = field(default_factory=lambda: {
        "polls": 0, "new_articles": 0, "errors": 0, "last_poll": None, "last_article": None
    })


class FMPNewsStreamManager:
    # Pipeline unificado de noticias (keys con nombre "benzinga" por herencia:
    # las comparten todas las fuentes y las sirve el endpoint GET /news del gateway)
    STREAM_KEY = "stream:benzinga:news"
    CACHE_LATEST_KEY = "cache:benzinga:news:latest"
    CACHE_BY_TICKER_PREFIX = "cache:benzinga:news:ticker:"

    # Keys propias de esta fuente
    CACHE_REUTERS_KEY = "cache:fmp:news:reuters"
    DEDUP_SET_KEY = "dedup:fmp:news"

    CACHE_LATEST_SIZE = 2000
    CACHE_BY_TICKER_SIZE = 200
    CACHE_REUTERS_SIZE = 300
    DEDUP_TTL_SECONDS = 7 * 86400

    def __init__(self, redis_client, api_key: str, base_url: str, settings):
        self.redis = redis_client
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.limit = settings.max_articles_per_poll
        self._http: Optional[httpx.AsyncClient] = None
        self._tasks: List[asyncio.Task] = []
        self._running = False

        self.feeds: List[FeedConfig] = [
            FeedConfig("stock", "/news/stock-latest", "Stock", settings.poll_interval_stock),
            FeedConfig("press", "/news/press-releases-latest", "Press Releases", settings.poll_interval_press),
            FeedConfig("general", "/news/general-latest", "General", settings.poll_interval_general),
            FeedConfig("forex", "/news/forex-latest", "Forex", settings.poll_interval_forex),
            FeedConfig("articles", "/fmp-articles", "FMP", settings.poll_interval_articles, is_fmp_articles=True),
        ]

    # ────────────────────────────────────────────────────────────────────
    # Lifecycle
    # ────────────────────────────────────────────────────────────────────

    async def start(self):
        self._http = httpx.AsyncClient(timeout=15.0)
        self._running = True
        for feed in self.feeds:
            self._tasks.append(asyncio.create_task(self._feed_loop(feed)))
        logger.info("fmp_news_manager_started", feeds=[f.name for f in self.feeds])

    async def stop(self):
        self._running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        if self._http:
            await self._http.aclose()
        logger.info("fmp_news_manager_stopped")

    # ────────────────────────────────────────────────────────────────────
    # Polling
    # ────────────────────────────────────────────────────────────────────

    async def _feed_loop(self, feed: FeedConfig):
        bootstrap = True
        while self._running:
            try:
                new_count = await self._poll_feed(feed, publish=not bootstrap)
                feed.stats["polls"] += 1
                feed.stats["new_articles"] += new_count
                feed.stats["last_poll"] = datetime.now(timezone.utc).isoformat()
                if bootstrap:
                    logger.info("feed_bootstrap_complete", feed=feed.name, cached=new_count)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                feed.stats["errors"] += 1
                logger.error("feed_poll_error", feed=feed.name, error=str(e))
            bootstrap = False
            await asyncio.sleep(feed.interval)

    async def _poll_feed(self, feed: FeedConfig, publish: bool) -> int:
        items = await self._fetch(feed)
        new_count = 0
        # Los feeds vienen newest-first; procesamos en orden cronológico
        # para que el stream conserve el orden de publicación.
        for data in reversed(items):
            if feed.is_fmp_articles:
                article = FMPArticle.from_fmp_article(data, feed.channel)
            else:
                article = FMPArticle.from_feed_item(data, feed.channel)
            if article is None:
                continue
            if await self.redis.sismember(self.DEDUP_SET_KEY, article.id):
                continue
            await self.redis.sadd(self.DEDUP_SET_KEY, article.id)
            await self._cache_article(article)
            if publish:
                await self._publish_to_stream(article)
            feed.stats["last_article"] = article.published
            new_count += 1
        # El TTL se renueva en cada poll: solo expira tras parada prolongada
        await self.redis.expire(self.DEDUP_SET_KEY, self.DEDUP_TTL_SECONDS)
        return new_count

    async def _fetch(self, feed: FeedConfig) -> List[dict]:
        url = f"{self.base_url}{feed.path}"
        params = {"page": 0, "limit": self.limit, "apikey": self.api_key}
        response = await self._http.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            raise ValueError(f"unexpected FMP response: {str(data)[:200]}")
        return data

    # ────────────────────────────────────────────────────────────────────
    # Cache + stream
    # ────────────────────────────────────────────────────────────────────

    @staticmethod
    def _score(article: FMPArticle) -> float:
        try:
            return datetime.fromisoformat(article.published).timestamp()
        except ValueError:
            return datetime.now(timezone.utc).timestamp()

    async def _cache_article(self, article: FMPArticle):
        payload = article.model_dump_json()
        score = self._score(article)

        await self.redis.zadd(self.CACHE_LATEST_KEY, {payload: score})
        await self.redis.zremrangebyrank(self.CACHE_LATEST_KEY, 0, -(self.CACHE_LATEST_SIZE + 1))

        for ticker in article.tickers[:5]:
            key = f"{self.CACHE_BY_TICKER_PREFIX}{ticker.upper()}"
            await self.redis.zadd(key, {payload: score})
            await self.redis.zremrangebyrank(key, 0, -(self.CACHE_BY_TICKER_SIZE + 1))
            await self.redis.expire(key, 604800)

        if article.is_reuters:
            await self.redis.zadd(self.CACHE_REUTERS_KEY, {payload: score})
            await self.redis.zremrangebyrank(self.CACHE_REUTERS_KEY, 0, -(self.CACHE_REUTERS_SIZE + 1))

    async def _publish_to_stream(self, article: FMPArticle):
        try:
            await self.redis.xadd(
                self.STREAM_KEY,
                {
                    "type": "news",
                    "data": article.model_dump_json(),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                maxlen=2000,
            )
            logger.debug("fmp_news_published", title=article.title[:50], channel=article.channels[0])
        except Exception as e:
            logger.error("publish_to_stream_error", error=str(e))

    # ────────────────────────────────────────────────────────────────────
    # Queries (REST)
    # ────────────────────────────────────────────────────────────────────

    async def get_top_news(self, count: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Últimas noticias de Reuters (feed Top News), más recientes primero"""
        try:
            results = await self.redis.zrevrange(self.CACHE_REUTERS_KEY, offset, offset + count - 1)
            articles = []
            for result in results:
                try:
                    articles.append(json.loads(result))
                except json.JSONDecodeError:
                    continue
            return articles
        except Exception as e:
            logger.error("get_top_news_error", error=str(e))
            return []

    def get_stats(self) -> Dict[str, Any]:
        return {feed.name: feed.stats for feed in self.feeds}
