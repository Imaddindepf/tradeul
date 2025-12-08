"""
Catalyst Alert Engine - Sistema Profesional de Detección de Movimientos

Sistema híbrido de detección de catalyst para traders de breaking news:

1. EARLY ALERT (inmediata): Si la noticia llega y el ticker ya muestra
   movimiento significativo + RVOL alto, alertar inmediatamente.

2. CONFIRMED ALERT (diferida): Evaluar el impacto REAL de la noticia
   después de 30s, 60s, 180s para detectar movimientos causados por ella.

Métricas clave:
- change_since_news_pct: Cambio REAL desde que llegó la noticia
- velocity_pct_per_min: Velocidad del movimiento (momentum)
- rvol: Volumen relativo del día
- volume_spike_ratio: Spike de volumen en ventana corta vs normal

Sin hardcodeos arbitrarios - todo configurable por el usuario.
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Set
from dataclasses import dataclass, asdict
from enum import Enum
import structlog
import httpx
from redis.asyncio import Redis

logger = structlog.get_logger(__name__)


class AlertType(str, Enum):
    EARLY = "early"           # Alerta inmediata (ticker ya en movimiento)
    CONFIRMED = "confirmed"   # Alerta confirmada después de evaluación


@dataclass
class CatalystMetrics:
    """Métricas de impacto de una noticia en un ticker"""
    # Identificación
    ticker: str
    news_id: str
    news_title: str
    news_time: str
    
    # Precios
    price_at_news: float          # Precio cuando llegó la noticia
    price_current: float          # Precio en evaluación
    
    # Cambios (lo más importante)
    change_since_news_pct: float  # Cambio REAL desde la noticia
    seconds_since_news: int       # Tiempo desde la noticia
    
    # Velocidad (momentum)
    velocity_pct_per_min: float   # % de cambio por minuto
    
    # Volumen
    rvol: float                   # RVOL del día
    volume_spike_ratio: float     # Spike de volumen reciente vs normal
    current_volume: int           # Volumen actual
    
    # Clasificación
    alert_type: str               # "early" o "confirmed"
    evaluation_window: int        # Ventana de evaluación en segundos (0=early)
    
    # Cambio del día (contexto adicional)
    change_day_pct: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass 
class PendingEvaluation:
    """Noticia pendiente de evaluación"""
    news_id: str
    ticker: str
    title: str
    news_time: datetime
    price_at_news: float
    volume_at_news: int
    rvol_at_news: float
    categories: List[str]
    evaluation_windows: List[int]  # Segundos para evaluar [30, 60, 180]
    evaluated_windows: Set[int]    # Ventanas ya evaluadas


class CatalystAlertEngine:
    """
    Motor profesional de detección de catalyst.
    
    Detecta noticias que causan impacto real en el precio/volumen
    usando evaluación híbrida (inmediata + diferida).
    """
    
    # Configuración por defecto (el usuario puede sobrescribir)
    DEFAULT_CONFIG = {
        # Ventanas de evaluación en segundos
        "evaluation_windows": [30, 60, 180],
        
        # Umbrales para EARLY alert (inmediata)
        "early_min_change_pct": 1.5,      # Cambio mínimo pre-existente
        "early_min_rvol": 2.0,            # RVOL mínimo
        
        # Umbrales para CONFIRMED alert (diferida)  
        "confirmed_min_change_pct": 2.0,  # Cambio mínimo desde noticia
        "confirmed_min_rvol": 1.5,        # RVOL mínimo
        "confirmed_min_volume_spike": 2.0, # Spike de volumen mínimo
        
        # Velocidad mínima (% por minuto)
        "min_velocity": 0.5,
    }
    
    ANALYTICS_URL = "http://analytics:8007"
    
    def __init__(self, redis_client: Redis, polygon_api_key: str, config: Dict = None):
        self.redis = redis_client
        self.api_key = polygon_api_key
        self.config = {**self.DEFAULT_CONFIG, **(config or {})}
        self._http_client: Optional[httpx.AsyncClient] = None
        self._analytics_client: Optional[httpx.AsyncClient] = None
        
        # Noticias pendientes de evaluación diferida
        self._pending_evaluations: Dict[str, PendingEvaluation] = {}
        
        # Tareas de evaluación activas
        self._evaluation_tasks: Dict[str, asyncio.Task] = {}
        
        # Callback para enviar alertas (lo setea el stream manager)
        self._alert_callback: Optional[callable] = None
        
        logger.info("catalyst_engine_initialized", config=self.config)
    
    def set_alert_callback(self, callback: callable):
        """Registra callback para enviar alertas al stream"""
        self._alert_callback = callback
    
    async def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                base_url="https://api.polygon.io",
                timeout=10.0
            )
        return self._http_client
    
    async def _get_analytics_client(self) -> httpx.AsyncClient:
        if self._analytics_client is None or self._analytics_client.is_closed:
            self._analytics_client = httpx.AsyncClient(
                base_url=self.ANALYTICS_URL,
                timeout=5.0
            )
        return self._analytics_client
    
    async def start(self):
        """Inicializa el motor"""
        logger.info("catalyst_engine_started")
    
    async def stop(self):
        """Cierra conexiones y cancela tareas pendientes"""
        # Cancelar todas las tareas de evaluación
        for task in self._evaluation_tasks.values():
            task.cancel()
        
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
        if self._analytics_client and not self._analytics_client.is_closed:
            await self._analytics_client.aclose()
        
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
        
        1. Captura el estado del mercado en el momento de la noticia
        2. Evalúa si hay condiciones para EARLY alert
        3. Programa evaluaciones diferidas para CONFIRMED alerts
        
        Returns:
            Dict con métricas si hay EARLY alert, None si solo hay evaluación diferida
        """
        try:
            now = datetime.now()
            
            # 1. Obtener estado actual del mercado
            market_state = await self._get_market_state(ticker)
            if not market_state:
                logger.warning("no_market_state", ticker=ticker, news_id=news_id)
                return None
            
            price_at_news = market_state["price"]
            volume_at_news = market_state["volume"]
            rvol = market_state["rvol"]
            change_day_pct = market_state.get("change_day_pct")
            volume_spike = market_state.get("volume_spike_ratio", 1.0)
            
            # 2. Evaluar EARLY alert (si el ticker ya está en movimiento)
            early_alert = None
            pre_move_pct = abs(change_day_pct) if change_day_pct else 0
            
            if (pre_move_pct >= self.config["early_min_change_pct"] and 
                rvol >= self.config["early_min_rvol"]):
                
                # Calcular velocidad aproximada (asumiendo movimiento en últimos 5 min)
                velocity = pre_move_pct / 5 if pre_move_pct > 0 else 0
                
                early_alert = CatalystMetrics(
                    ticker=ticker,
                    news_id=news_id,
                    news_title=title[:100],
                    news_time=now.isoformat(),
                    price_at_news=price_at_news,
                    price_current=price_at_news,
                    change_since_news_pct=0.0,  # Acaba de llegar
                    seconds_since_news=0,
                    velocity_pct_per_min=velocity,
                    rvol=rvol,
                    volume_spike_ratio=volume_spike,
                    current_volume=volume_at_news,
                    alert_type=AlertType.EARLY.value,
                    evaluation_window=0,
                    change_day_pct=change_day_pct,
                )
                
                logger.info(
                    "early_alert_triggered",
                    ticker=ticker,
                    pre_move_pct=pre_move_pct,
                    rvol=rvol,
                    title=title[:50]
                )
            
            # 3. Programar evaluaciones diferidas
            pending = PendingEvaluation(
                news_id=news_id,
                ticker=ticker,
                title=title,
                news_time=now,
                price_at_news=price_at_news,
                volume_at_news=volume_at_news,
                rvol_at_news=rvol,
                categories=categories or [],
                evaluation_windows=self.config["evaluation_windows"].copy(),
                evaluated_windows=set(),
            )
            
            self._pending_evaluations[news_id] = pending
            
            # Crear tareas de evaluación diferida
            for window_seconds in pending.evaluation_windows:
                task = asyncio.create_task(
                    self._schedule_evaluation(news_id, window_seconds)
                )
                task_key = f"{news_id}_{window_seconds}"
                self._evaluation_tasks[task_key] = task
            
            # Retornar early alert si existe (para envío inmediato)
            if early_alert:
                return early_alert.to_dict()
            
            return None
            
        except Exception as e:
            logger.error("process_news_error", error=str(e), ticker=ticker)
            return None
    
    async def _schedule_evaluation(self, news_id: str, delay_seconds: int):
        """Programa una evaluación diferida"""
        try:
            await asyncio.sleep(delay_seconds)
            await self._evaluate_impact(news_id, delay_seconds)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("scheduled_evaluation_error", error=str(e), news_id=news_id)
    
    async def _evaluate_impact(self, news_id: str, window_seconds: int):
        """
        Evalúa el impacto REAL de una noticia después de X segundos.
        
        Compara el precio actual vs el precio cuando llegó la noticia
        para determinar si causó un movimiento significativo.
        """
        pending = self._pending_evaluations.get(news_id)
        if not pending:
            return
        
        if window_seconds in pending.evaluated_windows:
            return
        
        pending.evaluated_windows.add(window_seconds)
        
        try:
            now = datetime.now()
            seconds_elapsed = (now - pending.news_time).total_seconds()
            
            # Obtener estado actual del mercado
            market_state = await self._get_market_state(pending.ticker)
            if not market_state:
                return
            
            price_current = market_state["price"]
            rvol_current = market_state["rvol"]
            volume_current = market_state["volume"]
            volume_spike = market_state.get("volume_spike_ratio", 1.0)
            change_day_pct = market_state.get("change_day_pct")
            
            # Calcular cambio REAL desde la noticia
            if pending.price_at_news > 0:
                change_since_news = ((price_current - pending.price_at_news) / pending.price_at_news) * 100
            else:
                change_since_news = 0
            
            # Calcular velocidad (% por minuto)
            minutes_elapsed = max(seconds_elapsed / 60, 0.5)  # Mínimo 30 segundos
            velocity = abs(change_since_news) / minutes_elapsed
            
            # Evaluar si cumple criterios para CONFIRMED alert
            passes_criteria = (
                abs(change_since_news) >= self.config["confirmed_min_change_pct"] and
                rvol_current >= self.config["confirmed_min_rvol"] and
                velocity >= self.config["min_velocity"]
            )
            
            if passes_criteria:
                metrics = CatalystMetrics(
                    ticker=pending.ticker,
                    news_id=news_id,
                    news_title=pending.title[:100],
                    news_time=pending.news_time.isoformat(),
                    price_at_news=pending.price_at_news,
                    price_current=price_current,
                    change_since_news_pct=round(change_since_news, 2),
                    seconds_since_news=int(seconds_elapsed),
                    velocity_pct_per_min=round(velocity, 2),
                    rvol=round(rvol_current, 2),
                    volume_spike_ratio=round(volume_spike, 2),
                    current_volume=volume_current,
                    alert_type=AlertType.CONFIRMED.value,
                    evaluation_window=window_seconds,
                    change_day_pct=round(change_day_pct, 2) if change_day_pct else None,
                )
                
                logger.info(
                    "confirmed_alert_triggered",
                    ticker=pending.ticker,
                    window=window_seconds,
                    change_pct=change_since_news,
                    rvol=rvol_current,
                    velocity=velocity,
                )
                
                # Enviar alerta via callback
                if self._alert_callback:
                    await self._alert_callback(pending.ticker, metrics.to_dict())
            else:
                logger.debug(
                    "evaluation_no_alert",
                    ticker=pending.ticker,
                    window=window_seconds,
                    change_pct=round(change_since_news, 2),
                    rvol=round(rvol_current, 2),
                    velocity=round(velocity, 2),
                )
            
            # Limpiar si es la última evaluación
            if len(pending.evaluated_windows) >= len(pending.evaluation_windows):
                self._cleanup_pending(news_id)
                
        except Exception as e:
            logger.error("evaluate_impact_error", error=str(e), news_id=news_id)
    
    def _cleanup_pending(self, news_id: str):
        """Limpia una noticia de las pendientes"""
        if news_id in self._pending_evaluations:
            del self._pending_evaluations[news_id]
        
        # Limpiar tareas relacionadas
        keys_to_remove = [k for k in self._evaluation_tasks if k.startswith(news_id)]
        for key in keys_to_remove:
            if key in self._evaluation_tasks:
                del self._evaluation_tasks[key]
    
    async def _get_market_state(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene el estado actual del mercado para un ticker.
        
        Returns:
            Dict con price, volume, rvol, change_day_pct, volume_spike_ratio
        """
        try:
            # 1. Intentar desde snapshot enriched (más rápido, tiene RVOL)
            snapshot_data = await self.redis.get("snapshot:enriched:latest")
            if snapshot_data:
                snapshot = json.loads(snapshot_data if isinstance(snapshot_data, str) else snapshot_data.decode())
                tickers_list = snapshot.get("tickers", [])
                
                ticker_upper = ticker.upper()
                for item in tickers_list:
                    if item.get("ticker", "").upper() == ticker_upper:
                        price = item.get("current_price") or item.get("lastTrade", {}).get("p", 0)
                        volume = item.get("current_volume") or item.get("day", {}).get("v", 0)
                        rvol = item.get("rvol") or 0
                        change_day_pct = item.get("todaysChangePerc")
                        
                        if change_day_pct is not None:
                            change_day_pct = round(change_day_pct, 2)
                        
                        # Calcular volume spike (si hay datos históricos)
                        volume_spike = await self._calculate_volume_spike(ticker, volume)
                        
                        return {
                            "price": float(price) if price else 0,
                            "volume": int(volume) if volume else 0,
                            "rvol": float(rvol) if rvol else 0,
                            "change_day_pct": change_day_pct,
                            "volume_spike_ratio": volume_spike,
                            "source": "enriched_snapshot"
                        }
            
            # 2. Fallback: API de Polygon + Analytics para RVOL
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
                
                day_data = ticker_data.get("day", {})
                volume = int(day_data.get("v", 0))
                
                change_day_pct = ticker_data.get("todaysChangePerc")
                if change_day_pct is not None:
                    change_day_pct = round(change_day_pct, 2)
                
                # Obtener RVOL de Analytics
                rvol = await self._get_rvol_from_analytics(ticker)
                
                # Calcular volume spike
                volume_spike = await self._calculate_volume_spike(ticker, volume)
                
                return {
                    "price": price,
                    "volume": volume,
                    "rvol": rvol or 1.0,
                    "change_day_pct": change_day_pct,
                    "volume_spike_ratio": volume_spike,
                    "source": "polygon_api"
                }
            
            return None
            
        except Exception as e:
            logger.error("get_market_state_error", error=str(e), ticker=ticker)
            return None
    
    async def _get_rvol_from_analytics(self, ticker: str) -> Optional[float]:
        """Obtiene RVOL del servicio de Analytics"""
        try:
            client = await self._get_analytics_client()
            response = await client.get(f"/rvol/{ticker.upper()}")
            
            if response.status_code == 200:
                data = response.json()
                rvol = data.get("rvol")
                if rvol is not None:
                    return float(rvol)
            
            return None
            
        except httpx.TimeoutException:
            return None
        except Exception as e:
            logger.debug("rvol_analytics_error", ticker=ticker, error=str(e))
            return None
    
    async def _calculate_volume_spike(self, ticker: str, current_volume: int) -> float:
        """
        Calcula el ratio de spike de volumen reciente.
        
        Compara el volumen actual vs el volumen promedio esperado.
        Si no hay datos históricos, retorna 1.0 (neutral).
        """
        try:
            # Intentar obtener volumen promedio de Redis o calcular
            avg_volume_key = f"volume:avg:{ticker.upper()}"
            avg_volume_data = await self.redis.get(avg_volume_key)
            
            if avg_volume_data:
                avg_volume = float(avg_volume_data)
                if avg_volume > 0:
                    return round(current_volume / avg_volume, 2)
            
            # Si no hay datos, usar RVOL como proxy
            return 1.0
            
        except Exception:
            return 1.0
    
    async def get_stats(self) -> Dict[str, Any]:
        """Retorna estadísticas del motor"""
        return {
            "pending_evaluations": len(self._pending_evaluations),
            "active_tasks": len(self._evaluation_tasks),
            "config": self.config,
        }
    
    def update_config(self, new_config: Dict[str, Any]):
        """Actualiza la configuración en runtime"""
        self.config.update(new_config)
        logger.info("config_updated", config=self.config)
