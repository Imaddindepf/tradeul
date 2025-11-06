"""
Redis client wrapper with async support
Provides high-level operations for the scanner system
"""

import json
from typing import Optional, List, Dict, Any, AsyncIterator
from datetime import timedelta
import redis.asyncio as aioredis
from redis.asyncio import Redis
from redis.exceptions import RedisError

from ..config.settings import settings
from .logger import get_logger

logger = get_logger(__name__)


class RedisClient:
    """
    Async Redis client with helper methods for common operations
    """
    
    def __init__(self, redis_url: Optional[str] = None):
        """
        Initialize Redis client
        
        Args:
            redis_url: Redis connection URL (uses settings if not provided)
        """
        self.redis_url = redis_url or settings.get_redis_url()
        self._client: Optional[Redis] = None
        self._pubsub = None
    
    async def connect(self) -> None:
        """Establish Redis connection"""
        try:
            self._client = await aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=50
            )
            await self._client.ping()
            logger.info("Connected to Redis", url=self.redis_url)
        except RedisError as e:
            logger.error("Failed to connect to Redis", error=str(e))
            raise
    
    async def disconnect(self) -> None:
        """Close Redis connection"""
        if self._client:
            await self._client.close()
            logger.info("Disconnected from Redis")
    
    @property
    def client(self) -> Redis:
        """Get Redis client instance"""
        if not self._client:
            raise RuntimeError("Redis client not connected. Call connect() first.")
        return self._client
    
    # =============================================
    # STRING OPERATIONS
    # =============================================
    
    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        serialize: bool = True
    ) -> bool:
        """
        Set a key-value pair
        
        Args:
            key: Redis key
            value: Value to store
            ttl: Time to live in seconds
            serialize: Whether to JSON serialize the value
        
        Returns:
            True if successful
        """
        try:
            if serialize and not isinstance(value, str):
                value = json.dumps(value)
            
            if ttl:
                return await self.client.setex(key, ttl, value)
            else:
                return await self.client.set(key, value)
        except RedisError as e:
            logger.error("Redis SET error", key=key, error=str(e))
            return False
    
    async def get(
        self,
        key: str,
        deserialize: bool = True
    ) -> Optional[Any]:
        """
        Get a value by key
        
        Args:
            key: Redis key
            deserialize: Whether to JSON deserialize the value
        
        Returns:
            Value or None if not found
        """
        try:
            value = await self.client.get(key)
            if value and deserialize:
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return value
            return value
        except RedisError as e:
            logger.error("Redis GET error", key=key, error=str(e))
            return None
    
    async def delete(self, *keys: str) -> int:
        """Delete one or more keys"""
        try:
            return await self.client.delete(*keys)
        except RedisError as e:
            logger.error("Redis DELETE error", keys=keys, error=str(e))
            return 0
    
    # =============================================
    # HASH OPERATIONS
    # =============================================
    
    async def hset(
        self,
        name: str,
        key: str,
        value: Any,
        serialize: bool = True
    ) -> int:
        """Set hash field"""
        try:
            if serialize and not isinstance(value, str):
                value = json.dumps(value)
            return await self.client.hset(name, key, value)
        except RedisError as e:
            logger.error("Redis HSET error", name=name, key=key, error=str(e))
            return 0
    
    async def hget(
        self,
        name: str,
        key: str,
        deserialize: bool = True
    ) -> Optional[Any]:
        """Get hash field"""
        try:
            value = await self.client.hget(name, key)
            if value and deserialize:
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return value
            return value
        except RedisError as e:
            logger.error("Redis HGET error", name=name, key=key, error=str(e))
            return None
    
    async def hmget(
        self,
        name: str,
        keys: List[str],
        deserialize: bool = True
    ) -> List[Optional[Any]]:
        """Get multiple hash fields"""
        try:
            values = await self.client.hmget(name, keys)
            if deserialize:
                result = []
                for value in values:
                    if value:
                        try:
                            result.append(json.loads(value))
                        except json.JSONDecodeError:
                            result.append(value)
                    else:
                        result.append(None)
                return result
            return values
        except RedisError as e:
            logger.error("Redis HMGET error", name=name, keys_count=len(keys), error=str(e))
            return [None] * len(keys)
    
    async def hgetall(
        self,
        name: str,
        deserialize: bool = True
    ) -> Dict[str, Any]:
        """Get all hash fields"""
        try:
            data = await self.client.hgetall(name)
            if deserialize:
                return {
                    k: json.loads(v) if v else None
                    for k, v in data.items()
                }
            return data
        except RedisError as e:
            logger.error("Redis HGETALL error", name=name, error=str(e))
            return {}
    
    async def hmset(
        self,
        name: str,
        mapping: Dict[str, Any],
        serialize: bool = True
    ) -> bool:
        """Set multiple hash fields"""
        try:
            if serialize:
                mapping = {
                    k: json.dumps(v) if not isinstance(v, str) else v
                    for k, v in mapping.items()
                }
            return await self.client.hset(name, mapping=mapping)
        except RedisError as e:
            logger.error("Redis HMSET error", name=name, error=str(e))
            return False
    
    # =============================================
    # SORTED SET OPERATIONS
    # =============================================
    
    async def zadd(
        self,
        name: str,
        mapping: Dict[str, float],
        nx: bool = False,
        gt: bool = False
    ) -> int:
        """Add members to sorted set"""
        try:
            return await self.client.zadd(name, mapping, nx=nx, gt=gt)
        except RedisError as e:
            logger.error("Redis ZADD error", name=name, error=str(e))
            return 0
    
    async def zrange(
        self,
        name: str,
        start: int,
        end: int,
        desc: bool = False,
        withscores: bool = False
    ) -> List:
        """Get range from sorted set"""
        try:
            return await self.client.zrange(
                name,
                start,
                end,
                desc=desc,
                withscores=withscores
            )
        except RedisError as e:
            logger.error("Redis ZRANGE error", name=name, error=str(e))
            return []
    
    async def zrem(self, name: str, *values: str) -> int:
        """Remove members from sorted set"""
        try:
            return await self.client.zrem(name, *values)
        except RedisError as e:
            logger.error("Redis ZREM error", name=name, error=str(e))
            return 0
    
    # =============================================
    # STREAM OPERATIONS
    # =============================================
    
    async def xadd(
        self,
        name: str,
        fields: Dict[str, Any],
        maxlen: Optional[int] = None,
        approximate: bool = True
    ) -> str:
        """
        Add entry to stream
        
        Args:
            name: Stream name
            fields: Data to add
            maxlen: Maximum stream length
            approximate: Use approximate trimming
        
        Returns:
            Entry ID
        """
        try:
            # Serialize complex values
            serialized_fields = {
                k: json.dumps(v) if not isinstance(v, str) else v
                for k, v in fields.items()
            }
            
            return await self.client.xadd(
                name,
                serialized_fields,
                maxlen=maxlen,
                approximate=approximate
            )
        except RedisError as e:
            logger.error("Redis XADD error", name=name, error=str(e))
            return ""
    
    async def xread(
        self,
        streams: Dict[str, str],
        count: Optional[int] = None,
        block: Optional[int] = None
    ) -> List:
        """
        Read from streams
        
        Args:
            streams: Dict of {stream_name: last_id}
            count: Maximum number of entries
            block: Block for N milliseconds
        
        Returns:
            List of stream entries
        """
        try:
            return await self.client.xread(
                streams,
                count=count,
                block=block
            )
        except RedisError as e:
            logger.error("Redis XREAD error", streams=streams, error=str(e))
            return []
    
    async def xlen(self, name: str) -> int:
        """Get stream length"""
        try:
            return await self.client.xlen(name)
        except RedisError as e:
            logger.error("Redis XLEN error", name=name, error=str(e))
            return 0
    
    async def create_consumer_group(
        self,
        stream_name: str,
        group_name: str,
        id: str = '0',
        mkstream: bool = False
    ) -> bool:
        """
        Create a consumer group for a stream
        
        Args:
            stream_name: Name of the stream
            group_name: Name of the consumer group
            id: Starting ID ('0' for beginning, '$' for new messages only)
            mkstream: Create stream if it doesn't exist
            
        Returns:
            True if created, False if already exists
        """
        try:
            await self.client.xgroup_create(
                stream_name,
                group_name,
                id=id,
                mkstream=mkstream
            )
            return True
        except RedisError as e:
            # Group already exists
            if "BUSYGROUP" in str(e):
                return False
            logger.error("Redis XGROUP CREATE error", stream=stream_name, group=group_name, error=str(e))
            raise
    
    async def read_stream(
        self,
        stream_name: str,
        consumer_group: str,
        consumer_name: str,
        count: int = 100,
        block: int = 5000
    ) -> List[tuple]:
        """
        Read from stream using consumer group
        
        Args:
            stream_name: Name of the stream
            consumer_group: Consumer group name
            consumer_name: Consumer name
            count: Max messages to read
            block: Block time in milliseconds
        
        Returns:
            List of (stream_name, messages) tuples
        """
        try:
            # Create consumer group if it doesn't exist
            try:
                await self.client.xgroup_create(
                    stream_name,
                    consumer_group,
                    id='0',
                    mkstream=True
                )
            except RedisError:
                # Group already exists, ignore
                pass
            
            # Read from group
            return await self.client.xreadgroup(
                consumer_group,
                consumer_name,
                {stream_name: '>'},
                count=count,
                block=block
            )
        except RedisError as e:
            logger.error(
                "Redis XREADGROUP error",
                stream=stream_name,
                group=consumer_group,
                error=str(e)
            )
            return []
    
    async def read_stream_range(
        self,
        stream_name: str,
        count: int = 100,
        start: str = "-",
        end: str = "+"
    ) -> List[tuple]:
        """
        Read messages from a stream range (XREVRANGE or XRANGE)
        
        Args:
            stream_name: Name of the stream
            count: Maximum number of messages to read
            start: Start ID (default: "-" for oldest)
            end: End ID (default: "+" for newest)
        
        Returns:
            List of (message_id, data_dict) tuples
        """
        try:
            # Usar XREVRANGE para obtener los mensajes más recientes primero
            messages = await self.client.xrevrange(
                stream_name,
                max=end,
                min=start,
                count=count
            )
            
            # Convertir formato de aioredis a tuplas (id, data)
            result = []
            for msg_id, fields in messages:
                data = {}
                for i in range(0, len(fields), 2):
                    if i + 1 < len(fields):
                        key = fields[i].decode() if isinstance(fields[i], bytes) else fields[i]
                        value = fields[i + 1]
                        # Intentar deserializar JSON si es posible
                        if isinstance(value, bytes):
                            try:
                                data[key] = json.loads(value.decode())
                            except (json.JSONDecodeError, UnicodeDecodeError):
                                data[key] = value.decode()
                        else:
                            data[key] = value
                result.append((msg_id.decode() if isinstance(msg_id, bytes) else msg_id, data))
            
            return result
        except RedisError as e:
            logger.error(
                "Redis XREVRANGE error",
                stream=stream_name,
                error=str(e)
            )
            return []
    
    async def xack(
        self,
        stream_name: str,
        consumer_group: str,
        *message_ids: str
    ) -> int:
        """
        Acknowledge messages in a consumer group
        
        Args:
            stream_name: Name of the stream
            consumer_group: Consumer group name
            message_ids: Message IDs to acknowledge
        
        Returns:
            Number of messages acknowledged
        """
        try:
            return await self.client.xack(
                stream_name,
                consumer_group,
                *message_ids
            )
        except RedisError as e:
            logger.error(
                "Redis XACK error",
                stream=stream_name,
                group=consumer_group,
                error=str(e)
            )
            return 0
    
    async def publish_to_stream(
        self,
        stream_name: str,
        data: Dict[str, Any],
        maxlen: int = 10000
    ) -> str:
        """
        Publish message to stream (simplified wrapper)
        
        Args:
            stream_name: Stream name
            data: Data to publish
            maxlen: Maximum stream length
        
        Returns:
            Message ID
        """
        return await self.xadd(stream_name, data, maxlen=maxlen)
    
    # =============================================
    # PUB/SUB OPERATIONS
    # =============================================
    
    async def publish(self, channel: str, message: Any) -> int:
        """Publish message to channel"""
        try:
            if not isinstance(message, str):
                message = json.dumps(message)
            return await self.client.publish(channel, message)
        except RedisError as e:
            logger.error("Redis PUBLISH error", channel=channel, error=str(e))
            return 0
    
    async def subscribe(self, *channels: str) -> aioredis.client.PubSub:
        """Subscribe to channels"""
        pubsub = self.client.pubsub()
        await pubsub.subscribe(*channels)
        return pubsub
    
    # =============================================
    # UTILITY OPERATIONS
    # =============================================
    
    async def exists(self, *keys: str) -> int:
        """Check if keys exist"""
        try:
            return await self.client.exists(*keys)
        except RedisError as e:
            logger.error("Redis EXISTS error", keys=keys, error=str(e))
            return 0
    
    async def expire(self, key: str, seconds: int) -> bool:
        """Set key expiration"""
        try:
            return await self.client.expire(key, seconds)
        except RedisError as e:
            logger.error("Redis EXPIRE error", key=key, error=str(e))
            return False
    
    async def scan_iter(self, pattern: str) -> AsyncIterator[str]:
        """Scan for keys matching a pattern"""
        async for key in self.client.scan_iter(match=pattern):
            yield key
    
    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching a pattern"""
        try:
            deleted = 0
            async for key in self.scan_iter(pattern):
                if await self.delete(key):
                    deleted += 1
            logger.info("Deleted keys by pattern", pattern=pattern, count=deleted)
            return deleted
        except RedisError as e:
            logger.error("Redis DELETE_PATTERN error", pattern=pattern, error=str(e))
            return 0
    
    async def ttl(self, key: str) -> int:
        """Get key TTL"""
        try:
            return await self.client.ttl(key)
        except RedisError as e:
            logger.error("Redis TTL error", key=key, error=str(e))
            return -2
    
    async def ping(self) -> bool:
        """Ping Redis server"""
        try:
            return await self.client.ping()
        except RedisError:
            return False


# Global Redis client instance
_redis_client: Optional[RedisClient] = None


async def get_redis_client() -> RedisClient:
    """Get or create global Redis client"""
    global _redis_client
    
    if _redis_client is None:
        _redis_client = RedisClient()
        await _redis_client.connect()
    
    return _redis_client


async def close_redis_client() -> None:
    """Close global Redis client"""
    global _redis_client
    
    if _redis_client:
        await _redis_client.disconnect()
        _redis_client = None

