"""
Cache Provider

Maneja cache de metadata en Redis.
"""

import json
from typing import Optional
from datetime import datetime, timezone

import sys
sys.path.append('/app')

from shared.utils.redis_client import RedisClient
from shared.models.scanner import TickerMetadata
from shared.utils.logger import get_logger

logger = get_logger(__name__)


class CacheProvider:
    """
    Provider para cache de metadata en Redis
    """
    
    def __init__(self, redis_client: RedisClient):
        self.redis = redis_client
        self.key_prefix = "metadata:ticker:"
    
    async def get_metadata(self, symbol: str) -> Optional[TickerMetadata]:
        """
        Obtiene metadata de cache
        """
        key = f"{self.key_prefix}{symbol}"
        
        try:
            cached_data = await self.redis.get(key)
            
            if not cached_data:
                return None
            
            # Deserializar (redis.get puede devolver string o dict según configuración)
            if isinstance(cached_data, str):
                data = json.loads(cached_data)
            else:
                data = cached_data
            
            # Convertir a TickerMetadata usando **data (desempaquetado)
            # Esto incluye TODOS los campos automáticamente
            if "updated_at" in data and isinstance(data["updated_at"], str):
                data["updated_at"] = datetime.fromisoformat(data["updated_at"])
            
            metadata = TickerMetadata(**data)
            
            return metadata
        
        except Exception as e:
            logger.error("cache_get_failed", symbol=symbol, error=str(e))
            return None
    
    async def set_metadata(self, metadata: TickerMetadata, ttl: int = 3600) -> bool:
        """
        Guarda metadata en cache
        
        Args:
            metadata: TickerMetadata object
            ttl: Time to live en segundos (default 1 hora)
        """
        key = f"{self.key_prefix}{metadata.symbol}"
        
        try:
            # Serializar TODOS los campos (usar model_dump de Pydantic)
            data = metadata.model_dump(mode='json')
            
            serialized = json.dumps(data)
            
            # Guardar con TTL usando set con ttl parameter
            await self.redis.set(key, serialized, ttl=ttl)
            
            return True
        
        except Exception as e:
            logger.error("cache_set_failed", symbol=metadata.symbol, error=str(e))
            return False
    
    async def delete_metadata(self, symbol: str) -> bool:
        """
        Elimina metadata del cache
        """
        key = f"{self.key_prefix}{symbol}"
        
        try:
            await self.redis.delete(key)
            return True
        
        except Exception as e:
            logger.error("cache_delete_failed", symbol=symbol, error=str(e))
            return False
    
    async def clear_all(self) -> int:
        """
        Limpia todo el cache de metadata
        Retorna cantidad de keys eliminados
        """
        try:
            pattern = f"{self.key_prefix}*"
            keys = await self.redis.keys(pattern)
            
            if not keys:
                return 0
            
            deleted = 0
            for key in keys:
                await self.redis.delete(key)
                deleted += 1
            
            logger.info("cache_cleared", count=deleted)
            return deleted
        
        except Exception as e:
            logger.error("cache_clear_failed", error=str(e))
            return 0

