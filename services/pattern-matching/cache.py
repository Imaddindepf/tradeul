"""
Pattern Matching Service - Redis Cache Layer
Professional caching for historical pattern search results
"""

import json
import hashlib
from typing import Optional, Dict, Any
from datetime import datetime

import redis.asyncio as redis
import structlog

from config import settings

logger = structlog.get_logger(__name__)


class PatternCache:
    """
    Redis cache for pattern matching results
    
    Strategy:
    - Historical searches: Long TTL (6 hours) - past data doesn't change
    - Realtime searches: Short TTL (60 seconds) - data is live
    - Index stats: Medium TTL (5 minutes) - changes with updates
    """
    
    def __init__(self):
        self._client: Optional[redis.Redis] = None
        self._connected = False
        
        # TTLs in seconds
        self.TTL_HISTORICAL = 6 * 60 * 60  # 6 hours
        self.TTL_REALTIME = 60             # 1 minute
        self.TTL_STATS = 300               # 5 minutes
        
        # Stats tracking
        self._hits = 0
        self._misses = 0
    
    async def connect(self) -> bool:
        """Initialize Redis connection"""
        try:
            self._client = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                password=settings.redis_password,
                db=settings.redis_db,
                decode_responses=True,
                socket_connect_timeout=5,
            )
            # Test connection
            await self._client.ping()
            self._connected = True
            logger.info("cache_connected", host=settings.redis_host, port=settings.redis_port)
            return True
        except Exception as e:
            logger.warning("cache_connection_failed", error=str(e))
            self._connected = False
            return False
    
    async def close(self):
        """Close Redis connection"""
        if self._client:
            await self._client.close()
            self._connected = False
            logger.info("cache_closed")
    
    def _generate_key(self, prefix: str, params: Dict[str, Any]) -> str:
        """Generate consistent cache key from parameters"""
        # Sort params for consistent hashing
        sorted_params = sorted(params.items())
        params_str = json.dumps(sorted_params, sort_keys=True)
        hash_suffix = hashlib.md5(params_str.encode()).hexdigest()[:12]
        return f"pm:{prefix}:{hash_suffix}"
    
    def _historical_key(
        self,
        symbol: str,
        date: str,
        time: str,
        k: int,
        cross_asset: bool,
        window_minutes: int
    ) -> str:
        """Generate cache key for historical search"""
        return self._generate_key("hist", {
            "s": symbol.upper(),
            "d": date,
            "t": time,
            "k": k,
            "ca": cross_asset,
            "w": window_minutes,
        })
    
    async def get_historical(
        self,
        symbol: str,
        date: str,
        time: str,
        k: int,
        cross_asset: bool,
        window_minutes: int
    ) -> Optional[Dict[str, Any]]:
        """Get cached historical search result"""
        if not self._connected:
            return None
        
        key = self._historical_key(symbol, date, time, k, cross_asset, window_minutes)
        
        try:
            cached = await self._client.get(key)
            if cached:
                self._hits += 1
                logger.debug("cache_hit", key=key)
                result = json.loads(cached)
                result["_cached"] = True
                result["_cache_key"] = key
                return result
            
            self._misses += 1
            logger.debug("cache_miss", key=key)
            return None
            
        except Exception as e:
            logger.warning("cache_get_error", key=key, error=str(e))
            return None
    
    async def set_historical(
        self,
        symbol: str,
        date: str,
        time: str,
        k: int,
        cross_asset: bool,
        window_minutes: int,
        result: Dict[str, Any]
    ) -> bool:
        """Cache historical search result"""
        if not self._connected:
            return False
        
        key = self._historical_key(symbol, date, time, k, cross_asset, window_minutes)
        
        try:
            # Add cache metadata
            result_to_cache = {
                **result,
                "_cached_at": datetime.now().isoformat(),
            }
            
            await self._client.setex(
                key,
                self.TTL_HISTORICAL,
                json.dumps(result_to_cache)
            )
            logger.debug("cache_set", key=key, ttl=self.TTL_HISTORICAL)
            return True
            
        except Exception as e:
            logger.warning("cache_set_error", key=key, error=str(e))
            return False
    
    async def invalidate_pattern(self, pattern: str = "pm:hist:*") -> int:
        """Invalidate cache entries matching pattern"""
        if not self._connected:
            return 0
        
        try:
            keys = []
            async for key in self._client.scan_iter(match=pattern):
                keys.append(key)
            
            if keys:
                deleted = await self._client.delete(*keys)
                logger.info("cache_invalidated", pattern=pattern, deleted=deleted)
                return deleted
            return 0
            
        except Exception as e:
            logger.warning("cache_invalidate_error", error=str(e))
            return 0
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        stats = {
            "connected": self._connected,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / max(1, self._hits + self._misses) * 100, 2),
            "ttl_historical_hours": self.TTL_HISTORICAL / 3600,
        }
        
        if self._connected:
            try:
                # Count cached keys
                count = 0
                async for _ in self._client.scan_iter(match="pm:*"):
                    count += 1
                stats["cached_entries"] = count
                
                # Redis info
                info = await self._client.info("memory")
                stats["redis_memory_used"] = info.get("used_memory_human", "unknown")
                
            except Exception as e:
                stats["error"] = str(e)
        
        return stats


# Global cache instance
pattern_cache = PatternCache()

