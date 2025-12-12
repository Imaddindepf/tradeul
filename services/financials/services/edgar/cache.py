"""
Edgar Service Cache - Gestión de cache en memoria y Redis.

Implementa cache de dos niveles:
1. Memoria (L1): Rápido, para datos frecuentes
2. Redis (L2): Persistente, para datos menos frecuentes
"""

from typing import Optional, Dict, Any, TypeVar, Generic
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import asyncio
import json

from shared.utils.logger import get_logger

logger = get_logger(__name__)

T = TypeVar('T')


@dataclass
class CacheEntry(Generic[T]):
    """Entrada de cache con timestamp."""
    value: T
    created_at: datetime = field(default_factory=datetime.utcnow)
    ttl: timedelta = field(default_factory=lambda: timedelta(hours=24))
    
    @property
    def is_expired(self) -> bool:
        return datetime.utcnow() > self.created_at + self.ttl
    
    @property
    def age_seconds(self) -> float:
        return (datetime.utcnow() - self.created_at).total_seconds()


class MemoryCache:
    """
    Cache en memoria con TTL.
    
    Uso:
        cache = MemoryCache(default_ttl=timedelta(hours=24))
        cache.set("key", value)
        value = cache.get("key")
    """
    
    def __init__(self, default_ttl: timedelta = timedelta(hours=24)):
        self._store: Dict[str, CacheEntry] = {}
        self._default_ttl = default_ttl
        self._lock = asyncio.Lock()
    
    def get(self, key: str) -> Optional[Any]:
        """Obtener valor si existe y no expiró."""
        entry = self._store.get(key)
        if entry is None:
            return None
        if entry.is_expired:
            del self._store[key]
            return None
        return entry.value
    
    def set(self, key: str, value: Any, ttl: Optional[timedelta] = None) -> None:
        """Guardar valor con TTL."""
        self._store[key] = CacheEntry(
            value=value,
            ttl=ttl or self._default_ttl
        )
    
    def delete(self, key: str) -> bool:
        """Eliminar una clave."""
        if key in self._store:
            del self._store[key]
            return True
        return False
    
    def delete_pattern(self, pattern: str) -> int:
        """Eliminar claves que contengan el patrón."""
        keys_to_delete = [k for k in self._store if pattern in k]
        for key in keys_to_delete:
            del self._store[key]
        return len(keys_to_delete)
    
    def clear(self) -> None:
        """Limpiar todo el cache."""
        self._store.clear()
    
    def stats(self) -> Dict[str, Any]:
        """Estadísticas del cache."""
        total = len(self._store)
        expired = sum(1 for e in self._store.values() if e.is_expired)
        return {
            "total_entries": total,
            "expired_entries": expired,
            "active_entries": total - expired,
        }


class EdgarCache:
    """
    Cache especializado para datos de Edgar.
    
    Implementa cache de dos niveles y namespacing por tipo de dato.
    """
    
    NAMESPACE_ENRICHMENT = "edgar:enrichment"
    NAMESPACE_COMPANY = "edgar:company"
    NAMESPACE_FILINGS = "edgar:filings"
    
    def __init__(self, redis_client=None):
        self._memory = MemoryCache()
        self._redis = redis_client
    
    def _make_key(self, namespace: str, symbol: str, *args) -> str:
        """Crear clave de cache."""
        parts = [namespace, symbol.upper()] + [str(a) for a in args]
        return ":".join(parts)
    
    # =========================================================================
    # Enrichment Cache
    # =========================================================================
    
    async def get_enrichment(self, symbol: str) -> Optional[Dict]:
        """Obtener datos de enriquecimiento."""
        key = self._make_key(self.NAMESPACE_ENRICHMENT, symbol)
        
        # L1: Memoria
        result = self._memory.get(key)
        if result is not None:
            logger.debug(f"[{symbol}] Enrichment from memory cache")
            return result
        
        # L2: Redis
        if self._redis:
            try:
                data = await self._redis.get(key)
                if data:
                    result = json.loads(data)
                    self._memory.set(key, result)  # Promover a L1
                    logger.debug(f"[{symbol}] Enrichment from Redis cache")
                    return result
            except Exception as e:
                logger.warning(f"Redis get error: {e}")
        
        return None
    
    async def set_enrichment(
        self, 
        symbol: str, 
        data: Dict,
        ttl: timedelta = timedelta(hours=24)
    ) -> None:
        """Guardar datos de enriquecimiento."""
        key = self._make_key(self.NAMESPACE_ENRICHMENT, symbol)
        
        # L1: Memoria
        self._memory.set(key, data, ttl)
        
        # L2: Redis
        if self._redis:
            try:
                await self._redis.setex(
                    key, 
                    int(ttl.total_seconds()), 
                    json.dumps(data)
                )
            except Exception as e:
                logger.warning(f"Redis set error: {e}")
    
    # =========================================================================
    # Company Info Cache
    # =========================================================================
    
    def get_company(self, symbol: str) -> Optional[Dict]:
        """Obtener info de empresa (solo memoria, datos pequeños)."""
        key = self._make_key(self.NAMESPACE_COMPANY, symbol)
        return self._memory.get(key)
    
    def set_company(self, symbol: str, data: Dict) -> None:
        """Guardar info de empresa."""
        key = self._make_key(self.NAMESPACE_COMPANY, symbol)
        self._memory.set(key, data, timedelta(hours=1))
    
    # =========================================================================
    # Utilities
    # =========================================================================
    
    async def invalidate(self, symbol: str) -> int:
        """Invalidar todo el cache para un símbolo."""
        count = self._memory.delete_pattern(symbol.upper())
        
        if self._redis:
            try:
                keys = await self._redis.keys(f"*{symbol.upper()}*")
                if keys:
                    await self._redis.delete(*keys)
                    count += len(keys)
            except Exception as e:
                logger.warning(f"Redis delete error: {e}")
        
        logger.info(f"[{symbol}] Invalidated {count} cache entries")
        return count
    
    def stats(self) -> Dict[str, Any]:
        """Estadísticas del cache."""
        return {
            "memory": self._memory.stats(),
            "redis_connected": self._redis is not None,
        }


# Singleton global
_cache: Optional[EdgarCache] = None


def get_edgar_cache(redis_client=None) -> EdgarCache:
    """Obtener instancia del cache."""
    global _cache
    if _cache is None:
        _cache = EdgarCache(redis_client)
    return _cache

