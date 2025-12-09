"""
HTTP Clients for Chat Service

Following the pattern from api_gateway/http_clients.py:
- Connection pooling
- Configured limits
- Singleton pattern
"""

import os
import json
from typing import Optional, Dict, Any, List
import httpx
import structlog

logger = structlog.get_logger(__name__)


class TimescaleClient:
    """
    Async client for TimescaleDB using asyncpg
    """
    
    def __init__(self):
        self._pool = None
    
    async def connect(self):
        """Create connection pool"""
        import asyncpg
        
        self._pool = await asyncpg.create_pool(
            host=os.getenv("POSTGRES_HOST", "timescaledb"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            database=os.getenv("POSTGRES_DB", "tradeul"),
            user=os.getenv("POSTGRES_USER", "tradeul_user"),
            password=os.getenv("POSTGRES_PASSWORD"),
            min_size=5,
            max_size=20,
            command_timeout=30.0,
        )
        logger.info("timescale_pool_created")
    
    async def fetch(self, query: str, *args) -> List[Dict]:
        """Execute SELECT and return list of dicts"""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *args)
            return [dict(row) for row in rows]
    
    async def fetchrow(self, query: str, *args) -> Optional[Dict]:
        """Execute SELECT and return one dict"""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, *args)
            return dict(row) if row else None
    
    async def fetchval(self, query: str, *args) -> Any:
        """Execute SELECT and return single value"""
        async with self._pool.acquire() as conn:
            return await conn.fetchval(query, *args)
    
    async def execute(self, query: str, *args) -> str:
        """Execute INSERT/UPDATE/DELETE"""
        async with self._pool.acquire() as conn:
            return await conn.execute(query, *args)
    
    async def close(self):
        """Close pool"""
        if self._pool:
            await self._pool.close()
            logger.info("timescale_pool_closed")


class RedisClient:
    """
    Async client for Redis
    """
    
    def __init__(self):
        self._client = None
    
    async def connect(self):
        """Connect to Redis"""
        import redis.asyncio as redis
        
        self._client = redis.Redis(
            host=os.getenv("REDIS_HOST", "redis"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            password=os.getenv("REDIS_PASSWORD"),
            decode_responses=True,
        )
        # Test connection
        await self._client.ping()
        logger.info("redis_connected")
    
    async def xadd(self, stream: str, fields: Dict) -> str:
        """Add to a stream"""
        return await self._client.xadd(stream, fields)
    
    async def publish(self, channel: str, message: str):
        """Publish to a pub/sub channel"""
        await self._client.publish(channel, message)
    
    async def get(self, key: str) -> Optional[str]:
        """Get value"""
        return await self._client.get(key)
    
    async def set(self, key: str, value: str, ex: Optional[int] = None):
        """Set value"""
        await self._client.set(key, value, ex=ex)
    
    async def close(self):
        """Close connection"""
        if self._client:
            await self._client.close()
            logger.info("redis_closed")


class PolygonClient:
    """
    Client for Polygon API - for fetching ticker prices
    """
    
    BASE_URL = "https://api.polygon.io"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=10.0,
            headers={"User-Agent": "Tradeul-Chat/1.0"}
        )
    
    async def get_snapshot(self, symbol: str) -> Optional[Dict]:
        """Get ticker snapshot with current price"""
        try:
            response = await self._client.get(
                f"/v2/snapshot/locale/us/markets/stocks/tickers/{symbol}",
                params={"apiKey": self.api_key}
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("ticker")
            return None
        except Exception as e:
            logger.error("polygon_snapshot_error", symbol=symbol, error=str(e))
            return None
    
    async def close(self):
        await self._client.aclose()


class ChatHTTPClientManager:
    """
    Centralized client manager for Chat Service
    """
    
    def __init__(self):
        self.timescale: Optional[TimescaleClient] = None
        self.redis: Optional[RedisClient] = None
        self.polygon: Optional[PolygonClient] = None
        self._initialized = False
    
    async def initialize(self):
        """Initialize all clients"""
        if self._initialized:
            return
        
        # TimescaleDB
        self.timescale = TimescaleClient()
        await self.timescale.connect()
        
        # Redis
        self.redis = RedisClient()
        await self.redis.connect()
        
        # Polygon (for ticker prices)
        polygon_key = os.getenv("POLYGON_API_KEY")
        if polygon_key:
            self.polygon = PolygonClient(polygon_key)
            logger.info("polygon_client_initialized")
        
        self._initialized = True
        logger.info("chat_http_clients_initialized")
    
    async def close(self):
        """Close all clients"""
        if self.timescale:
            await self.timescale.close()
        if self.redis:
            await self.redis.close()
        if self.polygon:
            await self.polygon.close()
        
        self._initialized = False
        logger.info("chat_http_clients_closed")
    
    async def get_ticker_price(self, symbol: str) -> Optional[Dict]:
        """
        Get current ticker price for embedding in chat messages
        Returns: {price, change, changePercent}
        """
        if not self.polygon:
            return None
        
        snapshot = await self.polygon.get_snapshot(symbol.upper())
        if not snapshot:
            return None
        
        try:
            # Extract price data
            day = snapshot.get("day", {})
            prev_day = snapshot.get("prevDay", {})
            
            price = day.get("c") or snapshot.get("lastTrade", {}).get("p", 0)
            prev_close = prev_day.get("c", 0)
            
            if price and prev_close:
                change = price - prev_close
                change_percent = (change / prev_close) * 100
            else:
                change = 0
                change_percent = 0
            
            return {
                "price": round(price, 2) if price else None,
                "change": round(change, 2),
                "changePercent": round(change_percent, 2),
                "volume": day.get("v", 0),
            }
        except Exception as e:
            logger.error("ticker_price_error", symbol=symbol, error=str(e))
            return None


# Singleton
http_clients = ChatHTTPClientManager()

