"""
Benzinga Earnings Client

Async client for Polygon.io's Benzinga Earnings API.
Endpoint: GET /benzinga/v1/earnings
"""

import httpx
import asyncio
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import structlog

from models.earnings import BenzingaEarning, EarningsFilterParams

logger = structlog.get_logger(__name__)


class BenzingaEarningsClient:
    """
    Async client for Benzinga Earnings API via Polygon.io
    
    Features:
    - Rate limiting to respect API limits
    - Automatic pagination for large result sets
    - Error handling and retries
    - Statistics tracking
    """
    
    BASE_URL = "https://api.polygon.io"
    ENDPOINT = "/benzinga/v1/earnings"
    
    def __init__(self, api_key: str, max_retries: int = 3):
        """
        Initialize the client.
        
        Args:
            api_key: Polygon.io API key
            max_retries: Max retry attempts for failed requests
        """
        self.api_key = api_key
        self.max_retries = max_retries
        self._client: Optional[httpx.AsyncClient] = None
        
        # Rate limiting (Polygon allows ~5 req/sec for paid plans)
        self._last_request_time = 0.0
        self._min_request_interval = 0.2  # 200ms between requests
        
        # Statistics
        self.stats = {
            "requests_made": 0,
            "earnings_fetched": 0,
            "errors": 0,
            "retries": 0,
            "last_fetch": None,
            "started_at": datetime.now().isoformat()
        }
        
        logger.info("benzinga_earnings_client_initialized")
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client with connection pooling."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                timeout=30.0,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "Tradeul/1.0"
                },
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)
            )
        return self._client
    
    async def close(self):
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            logger.info("benzinga_earnings_client_closed")
    
    async def _rate_limit(self):
        """Apply rate limiting between requests."""
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_request_time
        if elapsed < self._min_request_interval:
            await asyncio.sleep(self._min_request_interval - elapsed)
        self._last_request_time = asyncio.get_event_loop().time()
    
    async def _request_with_retry(
        self, 
        params: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Make request with automatic retry on failure.
        
        Args:
            params: Query parameters
            
        Returns:
            JSON response or None on failure
        """
        client = await self._get_client()
        
        for attempt in range(self.max_retries):
            try:
                await self._rate_limit()
                
                response = await client.get(self.ENDPOINT, params=params)
                response.raise_for_status()
                
                self.stats["requests_made"] += 1
                self.stats["last_fetch"] = datetime.now().isoformat()
                
                return response.json()
                
            except httpx.HTTPStatusError as e:
                logger.warning(
                    "http_error",
                    status=e.response.status_code,
                    attempt=attempt + 1,
                    max_retries=self.max_retries
                )
                if e.response.status_code == 429:  # Rate limited
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    self.stats["retries"] += 1
                elif e.response.status_code >= 500:  # Server error
                    await asyncio.sleep(1)
                    self.stats["retries"] += 1
                else:
                    self.stats["errors"] += 1
                    return None
                    
            except Exception as e:
                logger.error("request_error", error=str(e), attempt=attempt + 1)
                self.stats["errors"] += 1
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(1)
                    self.stats["retries"] += 1
        
        return None
    
    async def fetch_earnings(
        self,
        params: Optional[EarningsFilterParams] = None,
        **kwargs
    ) -> List[BenzingaEarning]:
        """
        Fetch earnings from Benzinga API.
        
        Args:
            params: Filter parameters
            **kwargs: Additional query parameters
            
        Returns:
            List of BenzingaEarning objects
        """
        query_params: Dict[str, Any] = {
            "apiKey": self.api_key,
            "limit": kwargs.get("limit", 100),
            "sort": kwargs.get("sort", "date.desc")
        }
        
        # Apply filter params
        if params:
            if params.ticker:
                query_params["ticker"] = params.ticker.upper()
            if params.date:
                query_params["date"] = params.date
            if params.date_gte:
                query_params["date.gte"] = params.date_gte
            if params.date_lte:
                query_params["date.lte"] = params.date_lte
            if params.importance_gte is not None:
                query_params["importance.gte"] = params.importance_gte
            if params.date_status:
                query_params["date_status"] = params.date_status
            if params.fiscal_period:
                query_params["fiscal_period"] = params.fiscal_period
            if params.limit:
                query_params["limit"] = params.limit
            if params.sort:
                query_params["sort"] = params.sort
        
        # Apply kwargs overrides
        for key, value in kwargs.items():
            if value is not None:
                query_params[key] = value
        
        data = await self._request_with_retry(query_params)
        
        if not data:
            return []
        
        # Parse results
        earnings = []
        for item in data.get("results", []):
            try:
                earning = BenzingaEarning.from_polygon_response(item)
                earnings.append(earning)
            except Exception as e:
                logger.warning("parse_error", error=str(e), ticker=item.get("ticker"))
        
        self.stats["earnings_fetched"] += len(earnings)
        
        logger.debug(
            "earnings_fetched",
            count=len(earnings),
            params=list(query_params.keys())
        )
        
        return earnings
    
    async def fetch_earnings_paginated(
        self,
        params: Optional[EarningsFilterParams] = None,
        max_results: int = 5000,
        **kwargs
    ) -> List[BenzingaEarning]:
        """
        Fetch earnings with automatic pagination.
        
        Args:
            params: Filter parameters
            max_results: Maximum total results to fetch
            **kwargs: Additional query parameters
            
        Returns:
            List of all BenzingaEarning objects
        """
        all_earnings = []
        page_size = min(1000, max_results)  # Polygon max is 50000, but 1000 is practical
        
        query_params: Dict[str, Any] = {
            "apiKey": self.api_key,
            "limit": page_size,
            "sort": kwargs.get("sort", "last_updated.desc")
        }
        
        # Apply filter params
        if params:
            if params.ticker:
                query_params["ticker"] = params.ticker.upper()
            if params.date:
                query_params["date"] = params.date
            if params.date_gte:
                query_params["date.gte"] = params.date_gte
            if params.date_lte:
                query_params["date.lte"] = params.date_lte
            if params.importance_gte is not None:
                query_params["importance.gte"] = params.importance_gte
            if params.date_status:
                query_params["date_status"] = params.date_status
        
        while len(all_earnings) < max_results:
            data = await self._request_with_retry(query_params)
            
            if not data:
                break
            
            results = data.get("results", [])
            if not results:
                break
            
            for item in results:
                try:
                    earning = BenzingaEarning.from_polygon_response(item)
                    all_earnings.append(earning)
                except Exception as e:
                    logger.warning("parse_error", error=str(e))
            
            # Check for next page
            next_url = data.get("next_url")
            if not next_url or len(all_earnings) >= max_results:
                break
            
            # Extract cursor from next_url for pagination
            # Polygon uses cursor-based pagination
            if "cursor=" in next_url:
                cursor = next_url.split("cursor=")[1].split("&")[0]
                query_params["cursor"] = cursor
            else:
                break
            
            logger.debug("pagination", fetched_so_far=len(all_earnings))
        
        self.stats["earnings_fetched"] += len(all_earnings)
        
        logger.info(
            "earnings_paginated_fetch_complete",
            total=len(all_earnings),
            max_requested=max_results
        )
        
        return all_earnings[:max_results]
    
    async def fetch_today_earnings(self) -> List[BenzingaEarning]:
        """Fetch today's earnings."""
        today = datetime.now().strftime("%Y-%m-%d")
        params = EarningsFilterParams(date=today, limit=500)
        return await self.fetch_earnings(params=params)
    
    async def fetch_upcoming_earnings(
        self, 
        days: int = 7,
        min_importance: Optional[int] = None
    ) -> List[BenzingaEarning]:
        """
        Fetch upcoming earnings for the next N days.
        
        Args:
            days: Number of days to look ahead
            min_importance: Minimum importance filter (0-5)
            
        Returns:
            List of upcoming earnings
        """
        today = datetime.now()
        end_date = today + timedelta(days=days)
        
        params = EarningsFilterParams(
            date_gte=today.strftime("%Y-%m-%d"),
            date_lte=end_date.strftime("%Y-%m-%d"),
            importance_gte=min_importance,
            limit=1000,
            sort="date.asc"
        )
        
        return await self.fetch_earnings(params=params)
    
    async def fetch_recent_earnings(
        self, 
        days: int = 7
    ) -> List[BenzingaEarning]:
        """
        Fetch recent earnings from the past N days.
        
        Args:
            days: Number of days to look back
            
        Returns:
            List of recent earnings
        """
        today = datetime.now()
        start_date = today - timedelta(days=days)
        
        params = EarningsFilterParams(
            date_gte=start_date.strftime("%Y-%m-%d"),
            date_lte=today.strftime("%Y-%m-%d"),
            limit=1000,
            sort="date.desc"
        )
        
        return await self.fetch_earnings(params=params)
    
    async def fetch_updated_since(
        self, 
        since: str,
        limit: int = 100
    ) -> List[BenzingaEarning]:
        """
        Fetch earnings updated since a specific timestamp.
        
        Args:
            since: ISO 8601 timestamp
            limit: Max results
            
        Returns:
            List of updated earnings
        """
        return await self.fetch_earnings(
            **{
                "last_updated.gte": since,
                "limit": limit,
                "sort": "last_updated.asc"
            }
        )
    
    async def fetch_ticker_earnings(
        self,
        ticker: str,
        limit: int = 20
    ) -> List[BenzingaEarning]:
        """
        Fetch earnings history for a specific ticker.
        
        Args:
            ticker: Stock ticker symbol
            limit: Max results
            
        Returns:
            List of earnings for the ticker
        """
        params = EarningsFilterParams(
            ticker=ticker.upper(),
            limit=limit,
            sort="date.desc"
        )
        return await self.fetch_earnings(params=params)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get client statistics."""
        return self.stats.copy()
