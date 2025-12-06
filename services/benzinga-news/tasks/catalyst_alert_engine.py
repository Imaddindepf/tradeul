"""
Catalyst Alert Engine - Sistema Profesional de Detección de Movimientos

Cuando llega una noticia, captura el estado del mercado en ese momento:
- change_recent: Movimiento en los últimos 2-3 minutos (backward)
- change_day: Movimiento del día (incluye el momento actual)

El frontend recibe ambos y filtra según los criterios del usuario.
Sin workers, sin pendientes, sin complejidad innecesaria.
"""

import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import structlog
import httpx
from redis.asyncio import Redis

logger = structlog.get_logger(__name__)


class CatalystAlertEngine:
    """
    Motor simple de detección de catalyst.
    Captura el estado del mercado cuando llega una noticia.
    """
    
    LOOKBACK_MINUTES = 3  # Minutos hacia atrás para detectar movimiento reciente
    ANALYTICS_URL = "http://analytics:8007"  # Servicio de analytics para RVOL on-demand
    
    def __init__(self, redis_client: Redis, polygon_api_key: str):
        self.redis = redis_client
        self.api_key = polygon_api_key
        self._http_client: Optional[httpx.AsyncClient] = None
        self._analytics_client: Optional[httpx.AsyncClient] = None
        
        logger.info("catalyst_alert_engine_initialized")
    
    async def _get_http_client(self) -> httpx.AsyncClient:
        """Obtiene o crea el cliente HTTP para Polygon"""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                base_url="https://api.polygon.io",
                timeout=10.0
            )
        return self._http_client
    
    async def _get_analytics_client(self) -> httpx.AsyncClient:
        """Obtiene o crea el cliente HTTP para Analytics"""
        if self._analytics_client is None or self._analytics_client.is_closed:
            self._analytics_client = httpx.AsyncClient(
                base_url=self.ANALYTICS_URL,
                timeout=5.0  # Timeout corto para no bloquear
            )
        return self._analytics_client
    
    async def start(self):
        """Inicializa el motor (no hay workers)"""
        logger.info("catalyst_alert_engine_started")
    
    async def stop(self):
        """Cierra conexiones"""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
        if self._analytics_client and not self._analytics_client.is_closed:
            await self._analytics_client.aclose()
        logger.info("catalyst_alert_engine_stopped")
    
    async def _get_rvol_from_analytics(self, ticker: str) -> Optional[float]:
        """
        Obtiene RVOL on-demand del servicio de Analytics.
        Esto funciona para CUALQUIER ticker, no solo los del scanner.
        """
        try:
            client = await self._get_analytics_client()
            response = await client.get(f"/rvol/{ticker.upper()}")
            
            if response.status_code == 200:
                data = response.json()
                rvol = data.get("rvol")
                if rvol is not None:
                    logger.debug("rvol_from_analytics", ticker=ticker, rvol=rvol)
                    return float(rvol)
            
            return None
            
        except httpx.TimeoutException:
            logger.debug("rvol_analytics_timeout", ticker=ticker)
            return None
        except Exception as e:
            logger.debug("rvol_analytics_error", ticker=ticker, error=str(e))
            return None
    
    async def process_news(
        self,
        news_id: str,
        ticker: str,
        title: str,
        categories: List[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Procesa una noticia y captura el estado del mercado.
        
        Returns:
            Dict con métricas del momento (el frontend filtra según criterios del usuario)
        """
        try:
            now = datetime.now()
            
            # 1. Obtener precio actual y cambio del día desde snapshot
            current_data = await self._get_current_snapshot(ticker)
            if not current_data:
                logger.warning("no_current_data", ticker=ticker, news_id=news_id)
                return None
            
            current_price = current_data.get("price", 0)
            change_day = current_data.get("change_day_pct")  # Incluye movimiento AHORA
            rvol = current_data.get("rvol", 0)
            volume = current_data.get("volume", 0)
            
            # 2. Si no hay RVOL en snapshot, obtenerlo de Analytics on-demand
            if not rvol or rvol == 0:
                rvol_from_analytics = await self._get_rvol_from_analytics(ticker)
                if rvol_from_analytics:
                    rvol = rvol_from_analytics
            
            # 3. Obtener precio histórico (hace 3 minutos) para change_recent
            price_before = await self._get_historical_price(ticker, minutes_ago=self.LOOKBACK_MINUTES)
            
            change_recent = None
            if price_before and price_before > 0 and current_price > 0:
                change_recent = round(((current_price - price_before) / price_before) * 100, 2)
            
            # 4. Construir resultado con TODAS las métricas
            result = {
                "type": "catalyst_alert",
                "news_id": news_id,
                "ticker": ticker,
                "title": title,
                "categories": categories or [],
                "price": current_price,
                "change_recent_pct": change_recent,  # Movimiento últimos 3 min
                "change_day_pct": change_day,        # Movimiento del día (incluye ahora)
                "rvol": rvol,
                "volume": volume,
                "lookback_minutes": self.LOOKBACK_MINUTES,
                "timestamp": now.isoformat()
            }
            
            # Log para debugging
            log_msg = (
                f"🔍 CATALYST | {ticker} | "
                f"price=${current_price:.2f} | "
                f"recent={change_recent}% ({self.LOOKBACK_MINUTES}min) | "
                f"day={change_day}% | "
                f"rvol={rvol:.1f}x | "
                f"{title[:35]}..."
            )
            print(log_msg, flush=True)
            
            return result
            
        except Exception as e:
            logger.error("process_news_error", error=str(e), ticker=ticker)
            return None
    
    async def _get_current_snapshot(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene datos actuales del ticker desde snapshot enriched o API.
        Incluye precio actual y cambio del día.
        """
        try:
            # 1. Intentar desde snapshot enriched (más rápido)
            snapshot_data = await self.redis.get("snapshot:enriched:latest")
            if snapshot_data:
                snapshot = json.loads(snapshot_data if isinstance(snapshot_data, str) else snapshot_data.decode())
                tickers_list = snapshot.get("tickers", [])
                
                ticker_upper = ticker.upper()
                for item in tickers_list:
                    if item.get("ticker", "").upper() == ticker_upper:
                        price = item.get("current_price") or item.get("lastTrade", {}).get("p", 0)
                        change_day = item.get("todaysChangePerc")
                        if change_day is not None:
                            change_day = round(change_day, 2)
                        
                        return {
                            "price": float(price) if price else 0,
                            "change_day_pct": change_day,
                            "rvol": item.get("rvol", 0),
                            "volume": item.get("current_volume") or item.get("day", {}).get("v", 0),
                            "source": "enriched_snapshot"
                        }
            
            # 2. Fallback: API de Polygon
            client = await self._get_http_client()
            response = await client.get(
                f"/v2/snapshot/locale/us/markets/stocks/tickers/{ticker.upper()}",
                params={"apiKey": self.api_key}
            )
            
            if response.status_code == 200:
                data = response.json()
                ticker_data = data.get("ticker", {})
                
                price = 0
                last_trade = ticker_data.get("lastTrade", {})
                if last_trade:
                    price = float(last_trade.get("p", 0))
                
                change_day = ticker_data.get("todaysChangePerc")
                if change_day is not None:
                    change_day = round(change_day, 2)
                
                day_data = ticker_data.get("day", {})
                
                return {
                    "price": price,
                    "change_day_pct": change_day,
                    "rvol": 0,  # No disponible en este endpoint
                    "volume": day_data.get("v", 0),
                    "source": "polygon_api"
                }
            
            return None
            
        except Exception as e:
            logger.error("get_current_snapshot_error", error=str(e), ticker=ticker)
            return None
    
    async def _get_historical_price(self, ticker: str, minutes_ago: int = 3) -> Optional[float]:
        """
        Obtiene el precio de hace X minutos usando barras de 1 minuto.
        """
        try:
            now = datetime.now()
            from_time = now - timedelta(minutes=minutes_ago + 2)  # Buffer extra
            to_time = now
            
            # Formato para Polygon: milliseconds
            from_ts = int(from_time.timestamp() * 1000)
            to_ts = int(to_time.timestamp() * 1000)
            
            client = await self._get_http_client()
            
            response = await client.get(
                f"/v2/aggs/ticker/{ticker.upper()}/range/1/minute/{from_ts}/{to_ts}",
                params={
                    "apiKey": self.api_key,
                    "adjusted": "true",
                    "sort": "desc",
                    "limit": 10
                }
            )
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            results = data.get("results", [])
            
            if not results:
                # Fuera de horario, usar prev day close
                return await self._get_prev_close(ticker)
            
            # Buscar la barra más cercana a "minutes_ago"
            target_time = (now - timedelta(minutes=minutes_ago)).timestamp() * 1000
            
            closest_bar = None
            min_diff = float('inf')
            
            for bar in results:
                bar_time = bar.get("t", 0)
                diff = abs(bar_time - target_time)
                if diff < min_diff:
                    min_diff = diff
                    closest_bar = bar
            
            if closest_bar:
                return float(closest_bar.get("c", 0))
            
            return None
            
        except Exception as e:
            logger.error("get_historical_price_error", error=str(e), ticker=ticker)
            return None
    
    async def _get_prev_close(self, ticker: str) -> Optional[float]:
        """Obtiene el precio de cierre del día anterior (fuera de horario)"""
        try:
            client = await self._get_http_client()
            response = await client.get(
                f"/v2/aggs/ticker/{ticker.upper()}/prev",
                params={"apiKey": self.api_key}
            )
            
            if response.status_code == 200:
                data = response.json()
                results = data.get("results", [])
                if results:
                    return float(results[0].get("c", 0))
            
            return None
            
        except Exception as e:
            logger.error("get_prev_close_error", error=str(e), ticker=ticker)
            return None
    
    async def get_stats(self) -> Dict[str, Any]:
        """Retorna estadísticas del motor"""
        return {
            "lookback_minutes": self.LOOKBACK_MINUTES
        }
