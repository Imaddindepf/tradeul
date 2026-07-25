"""
Polygon News Stream Manager

Poller de /v2/reference/news hacia el pipeline unificado de noticias:
  1. Dedup en Redis (set dedup:polygon:news, ID estable de Polygon)
  2. Cache en las keys compartidas de noticias (nombre "benzinga" histórico)
  3. Publica en stream:benzinga:news → websocket_server → frontend en vivo

Aporta la capa exclusiva de Polygon: sentimiento por ticker (insights) y
sentimiento agregado por artículo, que viajan dentro del payload.

El primer poll es bootstrap (solo cachea, no publica al stream).
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
import structlog

from models.news import PolygonArticle

logger = structlog.get_logger(__name__)


class PolygonNewsStreamManager:
    # Pipeline unificado de noticias (keys compartidas por todas las fuentes)
    STREAM_KEY = "stream:benzinga:news"
    CACHE_LATEST_KEY = "cache:benzinga:news:latest"
    CACHE_BY_TICKER_PREFIX = "cache:benzinga:news:ticker:"

    DEDUP_SET_KEY = "dedup:polygon:news"

    CACHE_LATEST_SIZE = 2000
    CACHE_BY_TICKER_SIZE = 200
    DEDUP_TTL_SECONDS = 7 * 86400

    def __init__(self, redis_client, api_key: str, base_url: str, settings):
        self.redis = redis_client
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.limit = settings.max_articles_per_poll
        self.interval = settings.poll_interval_seconds
        self._http: Optional[httpx.AsyncClient] = None
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self.stats: Dict[str, Any] = {
            "polls": 0, "new_articles": 0, "with_sentiment": 0,
            "errors": 0, "last_poll": None, "last_article": None,
        }

    async def start(self):
        self._http = httpx.AsyncClient(timeout=15.0)
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("polygon_news_manager_started", interval=self.interval)

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        if self._http:
            await self._http.aclose()
        logger.info("polygon_news_manager_stopped")

    async def _poll_loop(self):
        bootstrap = True
        while self._running:
            try:
                new_count = await self._poll_once(publish=not bootstrap)
                self.stats["polls"] += 1
                self.stats["new_articles"] += new_count
                self.stats["last_poll"] = datetime.now(timezone.utc).isoformat()
                if bootstrap:
                    logger.info("polygon_news_bootstrap_complete", cached=new_count)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.stats["errors"] += 1
                logger.error("polygon_news_poll_error", error=str(e))
            bootstrap = False
            await asyncio.sleep(self.interval)

    async def _poll_once(self, publish: bool) -> int:
        response = await self._http.get(
            f"{self.base_url}/v2/reference/news",
            params={"limit": self.limit, "order": "desc", "apiKey": self.api_key},
        )
        response.raise_for_status()
        items = (response.json() or {}).get("results") or []

        new_count = 0
        # newest-first → procesar en orden cronológico para el stream
        for data in reversed(items):
            article = PolygonArticle.from_polygon(data)
            if article is None:
                continue
            if await self.redis.sismember(self.DEDUP_SET_KEY, article.id):
                continue
            await self.redis.sadd(self.DEDUP_SET_KEY, article.id)
            await self._cache_article(article)
            if publish:
                await self._publish_to_stream(article)
            if article.sentiment:
                self.stats["with_sentiment"] += 1
            self.stats["last_article"] = article.published
            new_count += 1
        await self.redis.expire(self.DEDUP_SET_KEY, self.DEDUP_TTL_SECONDS)
        return new_count

    @staticmethod
    def _score(article: PolygonArticle) -> float:
        try:
            return datetime.fromisoformat(article.published.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return datetime.now(timezone.utc).timestamp()

    async def _cache_article(self, article: PolygonArticle):
        payload = article.model_dump_json()
        score = self._score(article)

        await self.redis.zadd(self.CACHE_LATEST_KEY, {payload: score})
        await self.redis.zremrangebyrank(self.CACHE_LATEST_KEY, 0, -(self.CACHE_LATEST_SIZE + 1))

        for ticker in article.tickers[:8]:
            key = f"{self.CACHE_BY_TICKER_PREFIX}{ticker.upper()}"
            await self.redis.zadd(key, {payload: score})
            await self.redis.zremrangebyrank(key, 0, -(self.CACHE_BY_TICKER_SIZE + 1))
            await self.redis.expire(key, 604800)

    async def _publish_to_stream(self, article: PolygonArticle):
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
            logger.debug("polygon_news_published", title=article.title[:50], sentiment=article.sentiment)
        except Exception as e:
            logger.error("publish_to_stream_error", error=str(e))
