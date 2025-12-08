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
        logger.info("🚀 Starting Benzinga News Stream Manager...")
        
        self.stats["started_at"] = datetime.now().isoformat()
        self._running = True
        
        # Iniciar motor de alertas de catalyst
        if self.catalyst_engine:
            await self.catalyst_engine.start()
            logger.info("✅ Catalyst Alert Engine started")
        
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
        
        # Detener motor de alertas
        if self.catalyst_engine:
            await self.catalyst_engine.stop()
        
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
    
    async def _get_catalyst_metrics(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene métricas de catalyst para un ticker.
        
        ESTRATEGIA: Primero obtener datos base del snapshot general (todos los tickers),
        luego enriquecer con datos de minuto si hay snapshots de catalyst disponibles.
        
        Esto funciona para TODOS los tickers, no solo los del scanner.
        
        Returns:
            Dict con métricas incluyendo:
            - change_1m_pct: Cambio en último minuto (si hay catalyst snapshots)
            - change_5m_pct: Cambio en últimos 5 minutos (si hay catalyst snapshots)
            - change_day_pct: Cambio desde cierre anterior (siempre disponible)
        """
        try:
            # PASO 1: Obtener datos base del snapshot general (funciona para TODOS los tickers)
            base_metrics = await self._get_from_enriched_snapshot(ticker)
            
            if not base_metrics:
                return None
            
            # PASO 2: Intentar enriquecer con datos de catalyst snapshots (más precisos)
            # Solo disponible para tickers en el scanner
            key = f"catalyst:snapshot:{ticker}"
            entries = await self.redis.lrange(key, 0, -1)
            
            if entries:
            snapshots = []
            for entry in entries:
                try:
                    data = json.loads(entry if isinstance(entry, str) else entry.decode())
                    snapshots.append(data)
                except:
                    continue
            
                if snapshots:
            now = datetime.now().timestamp() * 1000
            current = snapshots[0]  # Más reciente
            
            # Buscar snapshot de hace ~1 minuto y ~5 minutos
            price_1m_ago = None
            price_5m_ago = None
            
            for snap in snapshots:
                age_ms = now - snap.get("t", 0)
                age_min = age_ms / 60000
                
                if age_min >= 0.8 and age_min <= 1.5 and price_1m_ago is None:
                    price_1m_ago = snap.get("p")
                elif age_min >= 4.5 and age_min <= 6 and price_5m_ago is None:
                    price_5m_ago = snap.get("p")
            
            current_price = current.get("p", 0)
            
                    # Calcular cambios por minuto si tenemos los datos
            if price_1m_ago and price_1m_ago > 0:
                        base_metrics["change_1m_pct"] = round(((current_price - price_1m_ago) / price_1m_ago) * 100, 2)
                        base_metrics["price_1m_ago"] = price_1m_ago
            
            if price_5m_ago and price_5m_ago > 0:
                        base_metrics["change_5m_pct"] = round(((current_price - price_5m_ago) / price_5m_ago) * 100, 2)
                        base_metrics["price_5m_ago"] = price_5m_ago
                    
                    # Actualizar precio y volumen con datos más recientes del catalyst
                    base_metrics["price_at_news"] = current_price
                    base_metrics["volume"] = current.get("v", base_metrics.get("volume", 0))
                    base_metrics["source"] = "enriched+catalyst"  # Indica que tiene ambos
            
            return base_metrics
            
        except Exception as e:
            logger.error("get_catalyst_metrics_error", error=str(e), ticker=ticker)
            return None
    
    async def _get_from_enriched_snapshot(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Fallback: obtener datos del snapshot:enriched:latest cuando no hay catalyst snapshots.
        Este snapshot contiene datos de todos los tickers del mercado.
        
        Devuelve métricas con:
        - change_day_pct: Cambio desde el cierre anterior (siempre disponible)
        - change_1m_pct / change_5m_pct: NULL (no tenemos datos por minuto)
        
        El frontend debe usar change_day_pct como fallback cuando los otros son null.
        """
        try:
            # Obtener el snapshot enriched más reciente
            snapshot_data = await self.redis.get("snapshot:enriched:latest")
            if not snapshot_data:
                return None
            
            snapshot = json.loads(snapshot_data if isinstance(snapshot_data, str) else snapshot_data.decode())
            tickers_list = snapshot.get("tickers", [])
            
            # Buscar el ticker en el snapshot
            ticker_upper = ticker.upper()
            for item in tickers_list:
                if item.get("ticker", "").upper() == ticker_upper:
                    # Extraer datos del snapshot
                    price = item.get("current_price") or item.get("lastTrade", {}).get("p", 0)
                    prev_day = item.get("prevDay", {})
                    prev_close = prev_day.get("c", 0)
                    volume = item.get("current_volume") or item.get("day", {}).get("v", 0)
                    rvol = item.get("rvol", 0)
                    
                    # Usar todaysChangePerc directamente si existe (más preciso)
                    change_day_pct = item.get("todaysChangePerc")
                    if change_day_pct is not None:
                        change_day_pct = round(change_day_pct, 2)
                    elif prev_close and prev_close > 0 and price:
                        # Fallback: calcular manualmente
                        change_day_pct = round(((price - prev_close) / prev_close) * 100, 2)
                    
                    logger.info(
                        "catalyst_metrics_from_enriched",
                        ticker=ticker,
                        price=price,
                        change_day_pct=change_day_pct,
                        rvol=rvol,
                        source="enriched_snapshot"
                    )
                    
                    return {
                        "ticker": ticker,
                        "price_at_news": price,
                        "price_1m_ago": None,
                        "price_5m_ago": prev_close,
                        "change_1m_pct": None,  # No disponible sin snapshots por minuto
                        "change_5m_pct": None,  # No disponible sin snapshots por minuto
                        "change_day_pct": change_day_pct,  # NUEVO: Cambio desde cierre anterior
                        "volume": volume,
                        "rvol": rvol,
                        "snapshot_time": int(datetime.now().timestamp() * 1000),
                        "source": "enriched_snapshot"
                    }
            
            return None
            
        except Exception as e:
            logger.error("get_from_enriched_snapshot_error", error=str(e), ticker=ticker)
            return None

    async def _publish_to_stream(self, article: BenzingaArticle):
        """
        Publica artículo a Redis Stream para broadcast.
        Incluye métricas de catalyst (el frontend filtra según criterios del usuario).
        """
        try:
            catalyst_metrics = None
            primary_ticker = None
            
            # Obtener métricas de catalyst para el primer ticker
            if self.catalyst_engine and article.tickers and len(article.tickers) > 0:
                primary_ticker = article.tickers[0]
                
                # Capturar estado del mercado en este momento
                catalyst_metrics = await self.catalyst_engine.process_news(
                    news_id=str(article.benzinga_id),
                    ticker=primary_ticker,
                    title=article.title,
                    categories=article.channels or []
                )
                
                # Si el primer ticker no tiene datos, intentar con otros
                if catalyst_metrics is None:
                    for ticker in article.tickers[1:3]:
                        catalyst_metrics = await self.catalyst_engine.process_news(
                            news_id=f"{article.benzinga_id}_{ticker}",
                            ticker=ticker,
                            title=article.title,
                            categories=article.channels or []
                        )
                        if catalyst_metrics:
                            primary_ticker = ticker
                            break
            
            # Publicar noticia al stream
            stream_payload = {
                "type": "news",
                "data": article.model_dump_json(),
                "timestamp": datetime.now().isoformat()
            }
            
            # Incluir métricas de catalyst (el frontend decide si alertar)
            if catalyst_metrics:
                stream_payload["catalyst_metrics"] = json.dumps(catalyst_metrics)
                self.stats["catalyst_alerts"] += 1
            
            await self.redis.xadd(
                self.STREAM_KEY,
                stream_payload,
                maxlen=2000
            )
            
            # Log
            if catalyst_metrics:
                log_msg = (
                    f"📰 NEWS | {primary_ticker} | "
                    f"recent={catalyst_metrics.get('change_recent_pct')}% | "
                    f"day={catalyst_metrics.get('change_day_pct')}% | "
                    f"rvol={catalyst_metrics.get('rvol', 0):.1f}x | "
                    f"{article.title[:35]}..."
                )
            else:
                log_msg = f"📰 NEWS | {article.tickers[:2] if article.tickers else []} | no_metrics | {article.title[:35]}..."
            print(log_msg, flush=True)
            
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

