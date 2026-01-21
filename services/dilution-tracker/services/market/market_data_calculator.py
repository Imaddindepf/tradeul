"""
Market Data Calculator Service
Obtiene datos de mercado desde Polygon y calcula Baby Shelf, IB6 Float Value, etc.

FORMULAS (de DilutionTracker.com):
- IB6 Float Value = Float × Highest_60_Day_Close × (1/3)
- Current Raisable Amount = min(IB6_Float_Value - Raised_Last_12Mo, Total_Capacity - Total_Raised)
- Price To Exceed Baby Shelf = (Total_Capacity × 3) / Float
- Baby Shelf Restriction = Float_Value < $75,000,000
- ATM Limited By Baby Shelf = is_baby_shelf AND remaining_capacity > current_raisable_amount
"""

import asyncio
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Optional, Dict, Any, List
import structlog
import httpx

logger = structlog.get_logger(__name__)


class MarketDataCalculator:
    """
    Servicio para obtener datos de mercado y calcular restricciones de Baby Shelf
    
    Usa Polygon API para:
    - Highest 60-Day Close
    - Current Price
    - Shares Outstanding
    - Float
    """
    
    BABY_SHELF_THRESHOLD = 75_000_000  # $75M float value threshold
    
    def __init__(self, polygon_api_key: str):
        self.polygon_api_key = polygon_api_key
        self.base_url = "https://api.polygon.io"
        self._client: Optional[httpx.AsyncClient] = None
        
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                http2=True
            )
        return self._client
    
    async def close(self):
        """Close HTTP client"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
    
    async def get_highest_60_day_close(self, ticker: str) -> Optional[Decimal]:
        """
        Obtiene el precio de cierre más alto en los últimos 60 días
        
        Args:
            ticker: Stock ticker
            
        Returns:
            Highest closing price in last 60 days, or None if not found
        """
        try:
            client = await self._get_client()
            
            # Calculate date range (60 calendar days)
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=60)
            
            url = f"{self.base_url}/v2/aggs/ticker/{ticker}/range/1/day/{start_date}/{end_date}"
            params = {
                "apiKey": self.polygon_api_key,
                "adjusted": "true",
                "sort": "desc",
                "limit": 60
            }
            
            response = await client.get(url, params=params)
            
            if response.status_code != 200:
                logger.warning("polygon_aggs_error", ticker=ticker, status=response.status_code)
                return None
            
            data = response.json()
            results = data.get("results", [])
            
            if not results:
                logger.warning("polygon_no_data", ticker=ticker)
                return None
            
            # Find highest close
            highest_close = max(r.get("c", 0) for r in results)
            
            logger.info("highest_60_day_close_found", ticker=ticker, highest=highest_close, days=len(results))
            return Decimal(str(highest_close))
            
        except Exception as e:
            logger.error("get_highest_60_day_close_error", ticker=ticker, error=str(e))
            return None
    
    async def get_ticker_details(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene detalles del ticker desde Polygon
        
        Returns:
            Dict with: share_class_shares_outstanding, weighted_shares_outstanding, market_cap
        """
        try:
            client = await self._get_client()
            
            url = f"{self.base_url}/v3/reference/tickers/{ticker}"
            params = {"apiKey": self.polygon_api_key}
            
            response = await client.get(url, params=params)
            
            if response.status_code != 200:
                logger.warning("polygon_ticker_details_error", ticker=ticker, status=response.status_code)
                return None
            
            data = response.json()
            results = data.get("results", {})
            
            return {
                "shares_outstanding": results.get("share_class_shares_outstanding"),
                "weighted_shares_outstanding": results.get("weighted_shares_outstanding"),
                "market_cap": results.get("market_cap"),
                "name": results.get("name"),
                "sic_code": results.get("sic_code"),
            }
            
        except Exception as e:
            logger.error("get_ticker_details_error", ticker=ticker, error=str(e))
            return None
    
    async def get_free_float(self, ticker: str) -> Optional[int]:
        """
        Obtiene el free float REAL desde Polygon /stocks/vX/float endpoint.
        
        IMPORTANTE: Este es el float correcto para cálculos de Baby Shelf.
        weighted_shares_outstanding NO es el float real.
        
        Returns:
            Free float (shares publicly tradeable) or None
        """
        try:
            client = await self._get_client()
            
            url = f"{self.base_url}/vX/float"
            params = {
                "ticker": ticker,
                "apiKey": self.polygon_api_key
            }
            
            response = await client.get(url, params=params)
            
            if response.status_code != 200:
                logger.debug("polygon_free_float_not_available", ticker=ticker, status=response.status_code)
                return None
            
            data = response.json()
            
            if data.get("status") == "OK" and data.get("results"):
                free_float = data["results"][0].get("free_float")
                if free_float:
                    logger.info("free_float_fetched", ticker=ticker, free_float=free_float)
                    return int(free_float)
            
            return None
            
        except Exception as e:
            logger.error("get_free_float_error", ticker=ticker, error=str(e))
            return None
    
    async def get_current_price(self, ticker: str) -> Optional[Decimal]:
        """
        Obtiene el precio actual desde Polygon snapshot
        
        Returns:
            Current price or None
        """
        try:
            client = await self._get_client()
            
            url = f"{self.base_url}/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}"
            params = {"apiKey": self.polygon_api_key}
            
            response = await client.get(url, params=params)
            
            if response.status_code != 200:
                logger.warning("polygon_snapshot_error", ticker=ticker, status=response.status_code)
                return None
            
            data = response.json()
            ticker_data = data.get("ticker", {})
            
            # Try different price sources
            price = (
                ticker_data.get("lastTrade", {}).get("p") or  # Last trade price
                ticker_data.get("day", {}).get("c") or  # Today's close
                ticker_data.get("prevDay", {}).get("c")  # Previous day close
            )
            
            if price:
                return Decimal(str(price))
            
            return None
            
        except Exception as e:
            logger.error("get_current_price_error", ticker=ticker, error=str(e))
            return None
    
    def calculate_ib6_float_value(
        self, 
        free_float: int, 
        highest_60_day_close: Decimal
    ) -> Decimal:
        """
        Calcula el IB6 Float Value
        
        Formula: Float × Highest_60_Day_Close
        
        This is the total market value of the company's public float.
        The baby shelf limit (what can be raised in 12 months) is IB6 / 3.
        """
        return Decimal(str(free_float)) * highest_60_day_close
    
    def calculate_current_raisable_amount(
        self,
        ib6_float_value: Decimal,
        total_capacity: Decimal,
        total_amount_raised: Decimal = Decimal("0"),
        raised_last_12mo: Decimal = Decimal("0")
    ) -> Decimal:
        """
        Calcula el monto que se puede levantar actualmente (Baby Shelf Rule)
        
        Formula: min(IB6_Float_Value/3 - Raised_Last_12Mo, Total_Capacity - Total_Raised)
        
        Baby Shelf Rule (I.B.6): Company can raise up to 1/3 of IB6 Float Value
        in any 12-month period.
        
        Args:
            ib6_float_value: IB6 float value (Float × Highest60DayClose)
            total_capacity: Total shelf capacity
            total_amount_raised: Total amount raised from this shelf
            raised_last_12mo: Amount raised in last 12 months under this shelf
            
        Returns:
            Current raisable amount
        """
        # Baby shelf limit is 1/3 of IB6 Float Value
        baby_shelf_limit = ib6_float_value / Decimal("3")
        ib6_available = baby_shelf_limit - raised_last_12mo
        capacity_available = total_capacity - total_amount_raised
        
        return max(Decimal("0"), min(ib6_available, capacity_available))
    
    def calculate_price_to_exceed_baby_shelf(
        self,
        total_capacity: Decimal,
        free_float: int
    ) -> Decimal:
        """
        Calcula el precio necesario para que la empresa deje de ser baby shelf
        
        Una empresa es "baby shelf" si su float value < $75M.
        
        Formula CORRECTA: $75,000,000 / Float
        
        Este es el precio al que el stock price debe llegar para que el 
        float market value supere el umbral de $75M y la empresa pueda
        usar más del 1/3 del IB6 float value bajo Instruction I.B.6.
        
        Ejemplo: Si float = 3.2M shares
        Price to exceed = $75M / 3.2M = $23.44
        """
        if free_float <= 0:
            return Decimal("0")
        
        # El precio al que float_value = $75M (umbral de baby shelf)
        return Decimal(str(self.BABY_SHELF_THRESHOLD)) / Decimal(str(free_float))
    
    def is_baby_shelf_company(
        self,
        free_float: int,
        highest_60_day_close: Decimal
    ) -> bool:
        """
        Determina si la empresa está sujeta a Baby Shelf restrictions
        
        Una empresa es "baby shelf" si su float value < $75M
        Float value = Float × Highest_60_Day_Close
        """
        float_value = Decimal(str(free_float)) * highest_60_day_close
        return float_value < Decimal(str(self.BABY_SHELF_THRESHOLD))
    
    async def calculate_all_shelf_metrics(
        self,
        ticker: str,
        free_float: Optional[int] = None,
        total_shelf_capacity: Optional[Decimal] = None,
        total_amount_raised: Decimal = Decimal("0"),
        raised_last_12mo: Decimal = Decimal("0")
    ) -> Dict[str, Any]:
        """
        Calcula todas las métricas de shelf en una sola llamada
        
        Returns:
            Dict with all calculated metrics
        """
        result = {
            "ticker": ticker,
            "highest_60_day_close": None,
            "free_float": free_float,
            "ib6_float_value": None,
            "is_baby_shelf": None,
            "baby_shelf_restriction": None,
            "current_raisable_amount": None,
            "price_to_exceed_baby_shelf": None,
            "calculation_date": datetime.now().isoformat(),
        }
        
        # Get highest 60-day close
        highest_close = await self.get_highest_60_day_close(ticker)
        if not highest_close:
            logger.warning("cannot_calculate_shelf_metrics_no_price", ticker=ticker)
            return result
        
        result["highest_60_day_close"] = float(highest_close)
        
        # Get float if not provided
        # IMPORTANTE: Usar free_float real de Polygon /stocks/vX/float
        # weighted_shares_outstanding NO es el float real para Baby Shelf
        if not free_float:
            # Primero intentar obtener free_float real
            free_float = await self.get_free_float(ticker)
            if free_float:
                free_float = free_float
                logger.info("using_free_float_for_baby_shelf", ticker=ticker, free_float=free_float)
            else:
                # Fallback a weighted_shares_outstanding solo si no hay free_float
                details = await self.get_ticker_details(ticker)
                if details:
                    free_float = details.get("weighted_shares_outstanding") or details.get("shares_outstanding")
                    logger.warning("using_weighted_shares_as_fallback", ticker=ticker, shares=free_float)
        
        if not free_float:
            logger.warning("cannot_calculate_shelf_metrics_no_float", ticker=ticker)
            return result
        
        result["free_float"] = free_float
        
        # Calculate IB6 Float Value
        ib6_value = self.calculate_ib6_float_value(free_float, highest_close)
        result["ib6_float_value"] = float(ib6_value)
        
        # Check if baby shelf
        is_baby = self.is_baby_shelf_company(free_float, highest_close)
        result["is_baby_shelf"] = is_baby
        result["baby_shelf_restriction"] = is_baby
        
        # Calculate current raisable amount if shelf capacity provided
        if total_shelf_capacity:
            current_raisable = self.calculate_current_raisable_amount(
                ib6_value,
                total_shelf_capacity,
                total_amount_raised,
                raised_last_12mo
            )
            result["current_raisable_amount"] = float(current_raisable)
            
            # Calculate price to exceed
            price_to_exceed = self.calculate_price_to_exceed_baby_shelf(
                total_shelf_capacity,
                free_float
            )
            result["price_to_exceed_baby_shelf"] = float(price_to_exceed)
        
        logger.info("shelf_metrics_calculated", ticker=ticker, 
                   is_baby_shelf=is_baby, ib6_value=float(ib6_value))
        
        return result
    
    async def calculate_atm_limitations(
        self,
        ticker: str,
        total_atm_capacity: Decimal,
        remaining_atm_capacity: Decimal,
        free_float: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Calcula las limitaciones del ATM por Baby Shelf
        
        Returns:
            Dict with ATM limitation info
        """
        result = {
            "ticker": ticker,
            "atm_limited_by_baby_shelf": False,
            "effective_remaining_capacity": float(remaining_atm_capacity),
            "remaining_capacity_without_restriction": float(remaining_atm_capacity),
        }
        
        # Get shelf metrics
        shelf_metrics = await self.calculate_all_shelf_metrics(
            ticker,
            free_float=free_float,
            total_shelf_capacity=total_atm_capacity
        )
        
        if not shelf_metrics.get("is_baby_shelf"):
            return result
        
        # ATM is limited by baby shelf
        current_raisable = shelf_metrics.get("current_raisable_amount", 0)
        
        if current_raisable and current_raisable < float(remaining_atm_capacity):
            result["atm_limited_by_baby_shelf"] = True
            result["effective_remaining_capacity"] = current_raisable
            result["remaining_capacity_without_restriction"] = float(remaining_atm_capacity)
            result["ib6_float_value"] = shelf_metrics.get("ib6_float_value")
            result["highest_60_day_close"] = shelf_metrics.get("highest_60_day_close")
        
        return result


# Singleton factory
_calculator_instance: Optional[MarketDataCalculator] = None


def get_market_data_calculator(polygon_api_key: str) -> MarketDataCalculator:
    """Get or create MarketDataCalculator singleton"""
    global _calculator_instance
    if _calculator_instance is None:
        _calculator_instance = MarketDataCalculator(polygon_api_key)
    return _calculator_instance

