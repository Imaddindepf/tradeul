"""
Benzinga News Client

Cliente para la API de Benzinga News a través de Polygon.io
Endpoint: GET /benzinga/v2/news
"""

import httpx
import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import structlog

from models.news import BenzingaArticle, NewsFilterParams

logger = structlog.get_logger(__name__)


class BenzingaNewsClient:
    """
    Cliente asíncrono para la API de Benzinga News (Polygon.io)
    """
    
    BASE_URL = "https://api.polygon.io"
    ENDPOINT = "/benzinga/v2/news"
    
    def __init__(self, api_key: str):
        """
        Inicializa el cliente
        
        Args:
            api_key: Polygon.io API key
        """
        self.api_key = api_key
        self._client: Optional[httpx.AsyncClient] = None
        
        # Rate limiting
        self._last_request_time = 0
        self._min_request_interval = 0.1  # 100ms entre requests
        
        # Estadísticas
        self.stats = {
            "requests_made": 0,
            "articles_fetched": 0,
            "errors": 0,
            "last_fetch": None
        }
        
        logger.info("benzinga_client_initialized")
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Obtiene o crea el cliente HTTP"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                timeout=30.0,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "Tradeul/1.0"
                }
            )
        return self._client
    
    async def close(self):
        """Cierra el cliente HTTP"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
    
    async def _rate_limit(self):
        """Aplica rate limiting entre requests"""
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_request_time
        if elapsed < self._min_request_interval:
            await asyncio.sleep(self._min_request_interval - elapsed)
        self._last_request_time = asyncio.get_event_loop().time()
    
    async def fetch_news(
        self,
        params: Optional[NewsFilterParams] = None,
        **kwargs
    ) -> List[BenzingaArticle]:
        """
        Obtiene noticias de Benzinga
        
        Args:
            params: Parámetros de filtrado
            **kwargs: Parámetros adicionales
            
        Returns:
            Lista de artículos
        """
        await self._rate_limit()
        
        try:
            client = await self._get_client()
            
            # Construir query params
            query_params = {
                "apiKey": self.api_key,
                "limit": kwargs.get("limit", 50),
                "sort": kwargs.get("sort", "published.desc")
            }
            
            # Agregar filtros opcionales
            if params:
                if params.tickers:
                    query_params["tickers"] = params.tickers
                if params.channels:
                    query_params["channels"] = params.channels
                if params.tags:
                    query_params["tags"] = params.tags
                if params.author:
                    query_params["author"] = params.author
                if params.published_after:
                    query_params["published.gte"] = params.published_after
                if params.published_before:
                    query_params["published.lte"] = params.published_before
                if params.limit:
                    query_params["limit"] = params.limit
                if params.sort:
                    query_params["sort"] = params.sort
            
            # Parámetros adicionales de kwargs
            for key, value in kwargs.items():
                if key not in ["limit", "sort"] and value is not None:
                    query_params[key] = value
            
            # Hacer request
            response = await client.get(self.ENDPOINT, params=query_params)
            response.raise_for_status()
            
            data = response.json()
            
            self.stats["requests_made"] += 1
            self.stats["last_fetch"] = datetime.now().isoformat()
            
            # Parsear resultados
            articles = []
            results = data.get("results", [])
            
            for article_data in results:
                try:
                    article = BenzingaArticle.from_polygon_response(article_data)
                    articles.append(article)
                except Exception as e:
                    logger.warning("article_parse_error", error=str(e), data=article_data)
            
            self.stats["articles_fetched"] += len(articles)
            
            logger.info(
                "news_fetched",
                count=len(articles),
                params=str(query_params.keys())
            )
            
            return articles
            
        except httpx.HTTPStatusError as e:
            logger.error("http_error", status=e.response.status_code, detail=str(e))
            self.stats["errors"] += 1
            return []
        except Exception as e:
            logger.error("fetch_error", error=str(e))
            self.stats["errors"] += 1
            return []
    
    async def fetch_latest_news(self, limit: int = 50) -> List[BenzingaArticle]:
        """
        Obtiene las últimas noticias
        
        Args:
            limit: Número de artículos
            
        Returns:
            Lista de artículos
        """
        return await self.fetch_news(limit=limit, sort="published.desc")
    
    async def fetch_news_for_ticker(
        self,
        ticker: str,
        limit: int = 50,
        since: Optional[str] = None
    ) -> List[BenzingaArticle]:
        """
        Obtiene noticias para un ticker específico
        
        Args:
            ticker: Símbolo del ticker
            limit: Número de artículos
            since: Desde cuándo (ISO 8601)
            
        Returns:
            Lista de artículos
        """
        params = NewsFilterParams(
            tickers=ticker.upper(),
            limit=limit,
            published_after=since
        )
        return await self.fetch_news(params=params)
    
    async def fetch_news_since(
        self,
        since_timestamp: str,
        limit: int = 100
    ) -> List[BenzingaArticle]:
        """
        Obtiene noticias desde un timestamp específico
        Útil para polling incremental
        
        Args:
            since_timestamp: Timestamp ISO 8601
            limit: Número máximo de artículos
            
        Returns:
            Lista de artículos nuevos
        """
        params = NewsFilterParams(
            published_after=since_timestamp,
            limit=limit,
            sort="published.asc"  # Más antiguos primero para procesar en orden
        )
        return await self.fetch_news(params=params)
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estadísticas del cliente"""
        return self.stats.copy()

