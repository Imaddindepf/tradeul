"""
Catalyst Alert Engine - Sistema Profesional con WebSocket

Detecta el IMPACTO REAL de noticias en tiempo real usando WebSocket.

FLUJO:
1. Llega noticia → capturar precio actual
2. Subscribir al ticker en WebSocket (via Redis)
3. Escuchar stream en tiempo real
4. Cuando cambio desde noticia >= umbral + RVOL alto → ALERTAR
5. Timeout 3 min → limpiar

MÉTRICAS:
- change_since_news_pct: Cambio REAL desde que llegó la noticia
- seconds_since_news: Tiempo transcurrido
- rvol: Volumen relativo del día
- volume_spike_ratio: Spike de volumen reciente

NO usa el cambio del día (inútil para catalyst).
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, asdict
import structlog
import httpx
from redis.asyncio import Redis

logger = structlog.get_logger(__name__)


@dataclass
class CatalystMetrics:
    """Métricas de impacto de una noticia en un ticker"""
    ticker: str
    news_id: str
    news_title: str
    news_time: str
    
    # Precios
    price_at_news: float
    price_current: float
    
    # Cambio desde noticia (LO MÁS IMPORTANTE)
    change_since_news_pct: float
    seconds_since_news: int
    
    # Volumen
    rvol: float
    current_volume: int
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MonitoredNews:
    """Noticia siendo monitoreada en tiempo real"""
    news_id: str
    ticker: str
    title: str
    news_time: datetime
    price_at_news: float
    rvol_at_news: float
    alerted: bool = False  # Ya se envió alerta?


class CatalystAlertEngine:
    """
    Motor profesional de detección de catalyst con WebSocket.
    
    Detecta noticias que causan impacto real en el precio
    monitoreando en tiempo real via WebSocket/Redis Streams.
    """
    
    # Configuración por defecto
    DEFAULT_CONFIG = {
        # Tiempo máximo de monitoreo (segundos)
        "monitor_timeout": 180,  # 3 minutos
        
        # Umbrales para alertar
        "min_change_pct": 2.0,    # Cambio mínimo desde noticia
        "min_rvol": 2.0,          # RVOL mínimo
    }
    
    ANALYTICS_URL = "http://analytics:8007"
    POLYGON_WS_URL = "http://polygon_ws:8002"
    
    def __init__(self, redis_client: Redis, polygon_api_key: str, config: Dict = None):
        self.redis = redis_client
        self.api_key = polygon_api_key
        self.config = {**self.DEFAULT_CONFIG, **(config or {})}
        self._http_client: Optional[httpx.AsyncClient] = None
        
        # Noticias siendo monitoreadas
        self._monitored: Dict[str, MonitoredNews] = {}
        
        # Tarea de monitoreo del stream
        self._monitor_task: Optional[asyncio.Task] = None
        
        # Callback para enviar alertas
        self._alert_callback: Optional[Callable] = None
        
        # Último ID leído del stream
        self._last_stream_id = "$"
        
        logger.info("catalyst_engine_initialized", config=self.config)
    
    def set_alert_callback(self, callback: Callable):
        """Registra callback para enviar alertas"""
        self._alert_callback = callback
    
    async def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                base_url="https://api.polygon.io",
                timeout=10.0
            )
        return self._http_client
    
    async def start(self):
        """Inicia el motor y el monitoreo del stream"""
        logger.info("catalyst_engine_starting")
        self._monitor_task = asyncio.create_task(self._monitor_stream())
        logger.info("catalyst_engine_started")
    
    async def stop(self):
        """Detiene el motor"""
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
        
        logger.info("catalyst_engine_stopped")
    
    async def process_news(
        self,
        news_id: str,
        ticker: str,
        title: str,
        categories: List[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Procesa una noticia entrante.
        
        1. Captura el precio actual
        2. Empieza a monitorear el ticker
        3. Solicita suscripción al WebSocket
        
        Returns:
            None (las alertas se envían via callback cuando se detecta impacto)
        """
        try:
            now = datetime.now()
            
            # 1. Obtener precio y RVOL actual
            market_data = await self._get_current_price(ticker)
            if not market_data:
                logger.warning("no_market_data", ticker=ticker, news_id=news_id)
                return None
            
            price_at_news = market_data["price"]
            rvol = market_data.get("rvol", 1.0)
            
            if price_at_news <= 0:
                logger.warning("invalid_price", ticker=ticker, price=price_at_news)
                return None
            
            # 2. Registrar para monitoreo
            self._monitored[news_id] = MonitoredNews(
                news_id=news_id,
                ticker=ticker,
                title=title,
                news_time=now,
                price_at_news=price_at_news,
                rvol_at_news=rvol,
            )
            
            # 3. Solicitar suscripción al WebSocket
            await self._request_subscription(ticker)
            
            # 4. Programar limpieza después del timeout
            asyncio.create_task(self._schedule_cleanup(news_id))
            
            logger.info(
                "news_monitoring_started",
                ticker=ticker,
                news_id=news_id,
                price=price_at_news,
                rvol=rvol,
                title=title[:50]
            )
            
            return None  # Alertas se envían via callback
            
        except Exception as e:
            logger.error("process_news_error", error=str(e), ticker=ticker)
            return None
    
    async def _monitor_stream(self):
        """
        Monitorea el stream de aggregates en tiempo real.
        Por cada mensaje, evalúa si hay impacto en alguna noticia monitoreada.
        """
        logger.info("stream_monitor_started")
        
        while True:
            try:
                # Leer del stream de aggregates
                messages = await self.redis.xread(
                    {"stream:realtime:aggregates": self._last_stream_id},
                    count=100,
                    block=1000  # 1 segundo de timeout
                )
                
                if not messages:
                    # Limpiar noticias expiradas
                    await self._cleanup_expired()
                    continue
                
                for stream_name, stream_messages in messages:
                    for msg_id, data in stream_messages:
                        self._last_stream_id = msg_id
                        await self._process_stream_message(data)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("stream_monitor_error", error=str(e))
                await asyncio.sleep(1)
        
        logger.info("stream_monitor_stopped")
    
    async def _process_stream_message(self, data: Dict[str, Any]):
        """Procesa un mensaje del stream de aggregates"""
        try:
            symbol = data.get(b'symbol') or data.get('symbol')
            if isinstance(symbol, bytes):
                symbol = symbol.decode()
            
            if not symbol:
                return
            
            symbol = symbol.upper()
            
            # Buscar noticias monitoreadas para este ticker
            for news_id, monitored in list(self._monitored.items()):
                if monitored.ticker.upper() != symbol:
                    continue
                
                if monitored.alerted:
                    continue
                
                # Obtener precio actual del mensaje
                close_price = data.get(b'close') or data.get('close')
                if isinstance(close_price, bytes):
                    close_price = close_price.decode()
                
                try:
                    price_current = float(close_price)
                except (ValueError, TypeError):
                    continue
                
                # Calcular cambio desde la noticia
                if monitored.price_at_news <= 0:
                    continue
                
                change_pct = ((price_current - monitored.price_at_news) / monitored.price_at_news) * 100
                seconds_elapsed = (datetime.now() - monitored.news_time).total_seconds()
                
                # Obtener RVOL actual
                rvol = await self._get_current_rvol(symbol)
                if rvol is None:
                    rvol = monitored.rvol_at_news
                
                # Obtener volumen del mensaje
                volume = data.get(b'volume_accumulated') or data.get('volume_accumulated') or 0
                if isinstance(volume, bytes):
                    volume = volume.decode()
                try:
                    current_volume = int(float(volume))
                except (ValueError, TypeError):
                    current_volume = 0
                
                # Evaluar si cumple criterios
                if (abs(change_pct) >= self.config["min_change_pct"] and
                    rvol >= self.config["min_rvol"]):
                    
                    # ALERTA!
                    monitored.alerted = True
                    
                    metrics = CatalystMetrics(
                        ticker=symbol,
                        news_id=news_id,
                        news_title=monitored.title[:100],
                        news_time=monitored.news_time.isoformat(),
                        price_at_news=monitored.price_at_news,
                        price_current=price_current,
                        change_since_news_pct=round(change_pct, 2),
                        seconds_since_news=int(seconds_elapsed),
                        rvol=round(rvol, 2),
                        current_volume=current_volume,
                    )
                    
                    logger.info(
                        "catalyst_alert_triggered",
                        ticker=symbol,
                        change_pct=round(change_pct, 2),
                        seconds=int(seconds_elapsed),
                        rvol=round(rvol, 2),
                        title=monitored.title[:50]
                    )
                    
                    # Enviar alerta via callback
                    if self._alert_callback:
                        await self._alert_callback(symbol, metrics.to_dict())
                    
        except Exception as e:
            logger.error("process_message_error", error=str(e))
    
    async def _get_current_price(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Obtiene precio actual y RVOL del ticker"""
        try:
            # 1. Intentar desde snapshot enriched hash (HGET = ~500 bytes vs 7MB)
            import orjson
            ticker_json = await self.redis.hget("snapshot:enriched:latest", ticker.upper())
            if ticker_json:
                try:
                    item = orjson.loads(ticker_json)
                    price = item.get("current_price") or item.get("lastTrade", {}).get("p", 0)
                    rvol = item.get("rvol") or 1.0
                    
                    return {
                        "price": float(price) if price else 0,
                        "rvol": float(rvol),
                        "source": "enriched_snapshot"
                    }
                except Exception:
                    pass
            
            # 2. Fallback: API de Polygon
            client = await self._get_http_client()
            response = await client.get(
                f"/v2/snapshot/locale/us/markets/stocks/tickers/{ticker.upper()}",
                params={"apiKey": self.api_key}
            )
            
            if response.status_code == 200:
                data = response.json()
                ticker_data = data.get("ticker", {})
                
                last_trade = ticker_data.get("lastTrade", {})
                price = float(last_trade.get("p", 0)) if last_trade else 0
                
                # Obtener RVOL de Analytics
                rvol = await self._get_current_rvol(ticker)
                
                return {
                    "price": price,
                    "rvol": rvol or 1.0,
                    "source": "polygon_api"
                }
            
            return None
            
        except Exception as e:
            logger.error("get_price_error", error=str(e), ticker=ticker)
            return None
    
    async def _get_current_rvol(self, ticker: str) -> Optional[float]:
        """Obtiene RVOL actual del servicio de Analytics"""
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(f"{self.ANALYTICS_URL}/rvol/{ticker.upper()}")
                
                if response.status_code == 200:
                    data = response.json()
                    rvol = data.get("rvol")
                    if rvol is not None:
                        return float(rvol)
            
            return None
            
        except Exception:
            return None
    
    # Stream para suscripciones de catalyst (leído por polygon_ws)
    CATALYST_SUBSCRIPTION_STREAM = "polygon_ws:catalyst_subscriptions"
    
    async def _request_subscription(self, ticker: str):
        """
        Solicita al polygon_ws que se suscriba al ticker via Redis Stream.
        
        Usa el stream 'polygon_ws:catalyst_subscriptions' que es leído por
        polygon_ws de forma independiente al scanner y quotes.
        """
        try:
            ticker_upper = ticker.upper()
            
            # Publicar al stream de suscripciones de catalyst
            await self.redis.xadd(
                self.CATALYST_SUBSCRIPTION_STREAM,
                {
                    "symbol": ticker_upper,
                    "action": "subscribe",
                    "source": "catalyst_engine",
                    "timestamp": datetime.now().isoformat()
                },
                maxlen=1000  # Mantener stream limpio
            )
            
            logger.debug("subscription_requested", ticker=ticker_upper)
            
        except Exception as e:
            logger.error("subscription_request_error", error=str(e), ticker=ticker)
    
    async def _request_unsubscription(self, ticker: str):
        """
        Solicita al polygon_ws que se desuscriba del ticker.
        
        Se llama cuando el monitoreo de una noticia expira.
        """
        try:
            ticker_upper = ticker.upper()
            
            # Verificar si hay otras noticias monitoreando el mismo ticker
            other_monitoring = any(
                m.ticker.upper() == ticker_upper 
                for m in self._monitored.values()
            )
            
            if other_monitoring:
                logger.debug(
                    "skipping_unsubscribe_still_monitoring",
                    ticker=ticker_upper
                )
                return
            
            # Publicar al stream de suscripciones de catalyst
            await self.redis.xadd(
                self.CATALYST_SUBSCRIPTION_STREAM,
                {
                    "symbol": ticker_upper,
                    "action": "unsubscribe",
                    "source": "catalyst_engine",
                    "timestamp": datetime.now().isoformat()
                },
                maxlen=1000
            )
            
            logger.debug("unsubscription_requested", ticker=ticker_upper)
            
        except Exception as e:
            logger.error("unsubscription_request_error", error=str(e), ticker=ticker)
    
    async def _schedule_cleanup(self, news_id: str):
        """Programa limpieza de una noticia después del timeout"""
        await asyncio.sleep(self.config["monitor_timeout"])
        
        if news_id in self._monitored:
            monitored = self._monitored[news_id]
            ticker = monitored.ticker
            
            if not monitored.alerted:
                logger.debug(
                    "monitoring_timeout_no_alert",
                    ticker=ticker,
                    news_id=news_id
                )
            
            # Eliminar del monitoreo
            del self._monitored[news_id]
            
            # Solicitar desuscripción (si no hay más noticias para este ticker)
            await self._request_unsubscription(ticker)
    
    async def _cleanup_expired(self):
        """Limpia noticias expiradas"""
        now = datetime.now()
        timeout = timedelta(seconds=self.config["monitor_timeout"])
        
        expired = [
            news_id for news_id, m in self._monitored.items()
            if now - m.news_time > timeout
        ]
        
        for news_id in expired:
            del self._monitored[news_id]
    
    async def get_stats(self) -> Dict[str, Any]:
        """Retorna estadísticas del motor"""
        return {
            "monitored_news": len(self._monitored),
            "config": self.config,
            "tickers_monitoring": list(set(m.ticker for m in self._monitored.values())),
        }
    
    def update_config(self, new_config: Dict[str, Any]):
        """Actualiza la configuración en runtime"""
        self.config.update(new_config)
        logger.info("config_updated", new_config=new_config)
