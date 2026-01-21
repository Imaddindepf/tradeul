"""
Cache Manager Service
Handles Redis caching for prediction markets data
"""

import json
from typing import Optional, List, Dict, Any
from datetime import datetime
import redis.asyncio as aioredis
from redis.asyncio import Redis
import structlog

from config import settings
from models.processed import PredictionMarketsResponse, ProcessedEvent


logger = structlog.get_logger(__name__)


class CacheManager:
    """
    Manages Redis cache for prediction markets data
    
    Cache keys:
    - prediction_markets:events:all - Full processed response
    - prediction_markets:events:category:{cat} - Events by category
    - prediction_markets:tags - Available tags
    - prediction_markets:last_update - Last successful update timestamp
    """
    
    KEY_PREFIX = "prediction_markets"
    
    def __init__(self):
        self._client: Optional[Redis] = None
    
    async def connect(self) -> None:
        """Establish Redis connection"""
        try:
            self._client = await aioredis.from_url(
                settings.get_redis_url(),
                encoding="utf-8",
                decode_responses=True,
                max_connections=20
            )
            await self._client.ping()
            logger.info("cache_manager_connected")
        except Exception as e:
            logger.error("cache_manager_connect_error", error=str(e))
            raise
    
    async def disconnect(self) -> None:
        """Close Redis connection"""
        if self._client:
            await self._client.close()
            self._client = None
            logger.info("cache_manager_disconnected")
    
    @property
    def client(self) -> Redis:
        if not self._client:
            raise RuntimeError("Cache not connected")
        return self._client
    
    def _key(self, *parts: str) -> str:
        """Build cache key with prefix"""
        return ":".join([self.KEY_PREFIX] + list(parts))
    
    async def set_full_response(
        self,
        response: PredictionMarketsResponse,
        ttl: Optional[int] = None
    ) -> bool:
        """Cache full prediction markets response"""
        try:
            key = self._key("events", "all")
            data = response.model_dump_json()
            
            if ttl is None:
                ttl = settings.events_cache_ttl
            
            await self.client.setex(key, ttl, data)
            
            # Update last update timestamp
            await self.client.set(
                self._key("last_update"),
                datetime.utcnow().isoformat()
            )
            
            logger.debug(
                "cache_set_full_response",
                events=response.total_events,
                ttl=ttl
            )
            return True
            
        except Exception as e:
            logger.error("cache_set_error", error=str(e))
            return False
    
    async def get_full_response(self) -> Optional[PredictionMarketsResponse]:
        """Retrieve cached full response"""
        try:
            key = self._key("events", "all")
            data = await self.client.get(key)
            
            if not data:
                return None
            
            response = PredictionMarketsResponse.model_validate_json(data)
            logger.debug("cache_hit_full_response")
            return response
            
        except Exception as e:
            logger.warning("cache_get_error", error=str(e))
            return None
    
    async def set_events_by_category(
        self,
        category: str,
        events: List[ProcessedEvent],
        ttl: Optional[int] = None
    ) -> bool:
        """Cache events for a specific category"""
        try:
            key = self._key("events", "category", category.lower().replace(" ", "_"))
            data = json.dumps([e.model_dump() for e in events], default=str)
            
            if ttl is None:
                ttl = settings.events_cache_ttl
            
            await self.client.setex(key, ttl, data)
            return True
            
        except Exception as e:
            logger.error("cache_set_category_error", category=category, error=str(e))
            return False
    
    async def get_events_by_category(
        self,
        category: str
    ) -> Optional[List[ProcessedEvent]]:
        """Retrieve cached events for a category"""
        try:
            key = self._key("events", "category", category.lower().replace(" ", "_"))
            data = await self.client.get(key)
            
            if not data:
                return None
            
            events_data = json.loads(data)
            return [ProcessedEvent.model_validate(e) for e in events_data]
            
        except Exception as e:
            logger.warning("cache_get_category_error", category=category, error=str(e))
            return None
    
    async def set_tags(
        self,
        tags: List[Dict[str, Any]],
        ttl: Optional[int] = None
    ) -> bool:
        """Cache available tags"""
        try:
            key = self._key("tags")
            data = json.dumps(tags)
            
            if ttl is None:
                ttl = settings.tags_cache_ttl
            
            await self.client.setex(key, ttl, data)
            return True
            
        except Exception as e:
            logger.error("cache_set_tags_error", error=str(e))
            return False
    
    async def get_tags(self) -> Optional[List[Dict[str, Any]]]:
        """Retrieve cached tags"""
        try:
            key = self._key("tags")
            data = await self.client.get(key)
            
            if not data:
                return None
            
            return json.loads(data)
            
        except Exception as e:
            logger.warning("cache_get_tags_error", error=str(e))
            return None
    
    async def get_last_update(self) -> Optional[datetime]:
        """Get timestamp of last successful update"""
        try:
            key = self._key("last_update")
            data = await self.client.get(key)
            
            if not data:
                return None
            
            return datetime.fromisoformat(data)
            
        except Exception as e:
            logger.warning("cache_get_last_update_error", error=str(e))
            return None
    
    async def invalidate_all(self) -> bool:
        """Invalidate all prediction markets cache"""
        try:
            pattern = f"{self.KEY_PREFIX}:*"
            cursor = 0
            deleted = 0
            
            while True:
                cursor, keys = await self.client.scan(
                    cursor=cursor,
                    match=pattern,
                    count=100
                )
                
                if keys:
                    await self.client.delete(*keys)
                    deleted += len(keys)
                
                if cursor == 0:
                    break
            
            logger.info("cache_invalidated", deleted_keys=deleted)
            return True
            
        except Exception as e:
            logger.error("cache_invalidate_error", error=str(e))
            return False
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        try:
            last_update = await self.get_last_update()
            
            # Check if cache exists
            key = self._key("events", "all")
            ttl = await self.client.ttl(key)
            exists = ttl > 0
            
            return {
                "connected": True,
                "has_data": exists,
                "ttl_remaining": ttl if ttl > 0 else 0,
                "last_update": last_update.isoformat() if last_update else None,
            }
            
        except Exception as e:
            return {
                "connected": False,
                "error": str(e),
            }


# Singleton instance
cache_manager = CacheManager()
