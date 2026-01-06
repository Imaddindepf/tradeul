"""
Polygon Client for AI Agent
Provides historical market data from Polygon.io
"""

import os
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from decimal import Decimal
import httpx
import structlog

logger = structlog.get_logger(__name__)


class PolygonClient:
    """
    Cliente de Polygon.io para datos historicos.
    
    Capacidades:
    - Barras OHLCV (1min a 1day)
    - Aggregates grouped (todo el mercado)
    - Ticker details
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("POLYGON_API_KEY")
        if not self.api_key:
            raise ValueError("POLYGON_API_KEY es requerido")
        
        self.base_url = "https://api.polygon.io"
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client
    
    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
    
    async def get_bars(
        self,
        symbol: str,
        days: int = 5,
        timeframe: str = "1h"
    ) -> List[Dict[str, Any]]:
        """
        Obtiene barras OHLCV para un simbolo.
        
        Args:
            symbol: Ticker symbol (ej: AAPL)
            days: Dias hacia atras (default 5)
            timeframe: Timeframe - 1min, 5min, 15min, 1h, 4h, 1d
        
        Returns:
            Lista de barras con timestamp, open, high, low, close, volume
        """
        # Mapear timeframe a Polygon format
        timeframe_map = {
            "1min": (1, "minute"),
            "5min": (5, "minute"),
            "15min": (15, "minute"),
            "30min": (30, "minute"),
            "1h": (1, "hour"),
            "4h": (4, "hour"),
            "1d": (1, "day"),
        }
        
        if timeframe not in timeframe_map:
            timeframe = "1h"
        
        multiplier, span = timeframe_map[timeframe]
        
        # Calcular fechas
        to_date = datetime.now()
        from_date = to_date - timedelta(days=days)
        
        url = f"{self.base_url}/v2/aggs/ticker/{symbol.upper()}/range/{multiplier}/{span}/{from_date.strftime('%Y-%m-%d')}/{to_date.strftime('%Y-%m-%d')}"
        
        params = {
            "apiKey": self.api_key,
            "adjusted": "true",
            "sort": "asc",
            "limit": 5000
        }
        
        try:
            client = await self._get_client()
            response = await client.get(url, params=params)
            
            if response.status_code != 200:
                logger.warning("polygon_bars_error", status=response.status_code, symbol=symbol)
                return []
            
            data = response.json()
            results = data.get("results", [])
            
            # Formatear resultados
            bars = []
            for bar in results:
                bars.append({
                    "timestamp": datetime.fromtimestamp(bar["t"] / 1000).isoformat(),
                    "open": float(bar.get("o", 0)),
                    "high": float(bar.get("h", 0)),
                    "low": float(bar.get("l", 0)),
                    "close": float(bar.get("c", 0)),
                    "volume": int(bar.get("v", 0)),
                    "vwap": float(bar.get("vw", 0)) if bar.get("vw") else None,
                    "trades": int(bar.get("n", 0)) if bar.get("n") else None,
                    "symbol": symbol.upper()
                })
            
            logger.info("polygon_bars_fetched", symbol=symbol, count=len(bars), days=days, timeframe=timeframe)
            return bars
        
        except Exception as e:
            logger.error("polygon_bars_exception", symbol=symbol, error=str(e))
            return []
    
    async def get_previous_close(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene el cierre del dia anterior.
        """
        url = f"{self.base_url}/v2/aggs/ticker/{symbol.upper()}/prev"
        params = {"apiKey": self.api_key, "adjusted": "true"}
        
        try:
            client = await self._get_client()
            response = await client.get(url, params=params)
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            results = data.get("results", [])
            
            if results:
                bar = results[0]
                return {
                    "symbol": symbol.upper(),
                    "close": float(bar.get("c", 0)),
                    "open": float(bar.get("o", 0)),
                    "high": float(bar.get("h", 0)),
                    "low": float(bar.get("l", 0)),
                    "volume": int(bar.get("v", 0)),
                    "vwap": float(bar.get("vw", 0)) if bar.get("vw") else None,
                }
            return None
        
        except Exception as e:
            logger.error("polygon_prev_close_error", symbol=symbol, error=str(e))
            return None
    
    async def get_grouped_daily(self, date: str = None) -> List[Dict[str, Any]]:
        """
        Obtiene datos diarios de todo el mercado para una fecha.
        Util para comparar rendimiento de multiples tickers.
        
        Args:
            date: Fecha en formato YYYY-MM-DD (default: ayer)
        
        Returns:
            Lista de tickers con OHLCV del dia
        """
        if not date:
            date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        
        url = f"{self.base_url}/v2/aggs/grouped/locale/us/market/stocks/{date}"
        params = {"apiKey": self.api_key, "adjusted": "true"}
        
        try:
            client = await self._get_client()
            response = await client.get(url, params=params)
            
            if response.status_code != 200:
                return []
            
            data = response.json()
            results = data.get("results", [])
            
            # Formatear
            tickers = []
            for bar in results:
                tickers.append({
                    "symbol": bar.get("T"),
                    "open": float(bar.get("o", 0)),
                    "high": float(bar.get("h", 0)),
                    "low": float(bar.get("l", 0)),
                    "close": float(bar.get("c", 0)),
                    "volume": int(bar.get("v", 0)),
                    "vwap": float(bar.get("vw", 0)) if bar.get("vw") else None,
                    "change_percent": round(((bar.get("c", 0) - bar.get("o", 0)) / bar.get("o", 1)) * 100, 2) if bar.get("o") else 0
                })
            
            return tickers
        
        except Exception as e:
            logger.error("polygon_grouped_error", date=date, error=str(e))
            return []
    
    async def get_ticker_details(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene detalles fundamentales de un ticker.
        """
        url = f"{self.base_url}/v3/reference/tickers/{symbol.upper()}"
        params = {"apiKey": self.api_key}
        
        try:
            client = await self._get_client()
            response = await client.get(url, params=params)
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            results = data.get("results", {})
            
            return {
                "symbol": results.get("ticker"),
                "name": results.get("name"),
                "market_cap": results.get("market_cap"),
                "shares_outstanding": results.get("share_class_shares_outstanding"),
                "weighted_shares": results.get("weighted_shares_outstanding"),
                "sector": results.get("sic_description"),
                "exchange": results.get("primary_exchange"),
                "type": results.get("type"),
                "active": results.get("active"),
                "homepage": results.get("homepage_url"),
                "description": results.get("description"),
            }
        
        except Exception as e:
            logger.error("polygon_details_error", symbol=symbol, error=str(e))
            return None

