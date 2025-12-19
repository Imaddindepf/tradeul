"""
Cache Service
=============
Servicio de caché para perfiles de dilución.

Maneja:
- Caché L1: Redis (instantáneo, ~10ms)
- Caché L2: PostgreSQL (rápido, ~50ms)
- Locks distribuidos para evitar scraping duplicado
"""

import asyncio
from datetime import datetime, date
from decimal import Decimal
from typing import Any, Optional

from shared.utils.logger import get_logger
from shared.utils.redis_client import RedisClient
from models.sec_dilution_models import SECDilutionProfile
from repositories.sec_dilution_repository import SECDilutionRepository

logger = get_logger(__name__)


class CacheService:
    """
    Servicio de caché para perfiles de dilución con Redis y PostgreSQL.
    """
    
    REDIS_KEY_PREFIX = "sec_dilution:profile"
    REDIS_TTL = 86400  # 24 horas
    
    def __init__(self, redis: RedisClient, repository: SECDilutionRepository):
        """
        Args:
            redis: Cliente Redis
            repository: Repositorio de dilución
        """
        self.redis = redis
        self.repository = repository
    
    async def acquire_ticker_lock(self, ticker: str, timeout: int = 300) -> bool:
        """
        Adquirir lock distribuido en Redis para un ticker.
        
        Usa SETNX con TTL para garantizar que solo un proceso puede scrapear
        el mismo ticker simultáneamente, incluso con múltiples workers.
        
        Args:
            ticker: Ticker symbol
            timeout: Tiempo máximo de espera en segundos (default 5 minutos)
            
        Returns:
            True si adquirió el lock, False si otro proceso ya lo tiene
        """
        lock_key = f"sec_dilution:lock:{ticker}"
        lock_value = f"{id(self)}:{datetime.now().isoformat()}"
        
        try:
            acquired = await self.redis.client.setnx(lock_key, lock_value)
            
            if acquired:
                await self.redis.client.expire(lock_key, 600)
                logger.debug("ticker_lock_acquired", ticker=ticker, lock_key=lock_key)
                return True
            else:
                logger.debug("ticker_lock_busy", ticker=ticker, lock_key=lock_key)
                return False
        except Exception as e:
            logger.error("ticker_lock_acquire_failed", ticker=ticker, error=str(e))
            return False
    
    async def release_ticker_lock(self, ticker: str) -> bool:
        """
        Liberar lock distribuido en Redis.
        
        Args:
            ticker: Ticker symbol
            
        Returns:
            True si se liberó correctamente
        """
        lock_key = f"sec_dilution:lock:{ticker}"
        try:
            await self.redis.delete(lock_key)
            logger.debug("ticker_lock_released", ticker=ticker, lock_key=lock_key)
            return True
        except Exception as e:
            logger.error("ticker_lock_release_failed", ticker=ticker, error=str(e))
            return False
    
    async def get_from_cache_only(self, ticker: str) -> Optional[SECDilutionProfile]:
        """
        Obtener perfil de dilución SOLO desde caché (NO bloquea).
        
        Estrategia:
        1. Redis (instantáneo) - ~10ms
        2. PostgreSQL (rápido) - ~50ms
        3. Si no hay datos -> retorna None (NO hace scraping)
        
        Args:
            ticker: Ticker symbol
            
        Returns:
            SECDilutionProfile si está en caché, None si no
        """
        try:
            ticker = ticker.upper()
            
            # 1. Intentar desde Redis
            cached_profile = await self.get_from_redis(ticker)
            if cached_profile:
                logger.info("cache_check_hit_redis", ticker=ticker)
                return cached_profile
            
            # 2. Intentar desde PostgreSQL
            db_profile = await self.repository.get_profile(ticker)
            if db_profile:
                logger.info("cache_check_hit_db", ticker=ticker)
                # Cachear en Redis para próximas consultas
                await self.save_to_redis(ticker, db_profile)
                return db_profile
            
            # 3. No hay datos en caché
            logger.info("cache_check_miss", ticker=ticker)
            return None
            
        except Exception as e:
            logger.error("get_from_cache_only_failed", ticker=ticker, error=str(e))
            return None
    
    async def invalidate_cache(self, ticker: str) -> bool:
        """
        Invalidar caché Redis para un ticker.
        
        Args:
            ticker: Ticker symbol
            
        Returns:
            True si se invalidó correctamente
        """
        try:
            redis_key = f"{self.REDIS_KEY_PREFIX}:{ticker.upper()}"
            await self.redis.delete(redis_key)
            logger.info("cache_invalidated", ticker=ticker)
            return True
        except Exception as e:
            logger.error("cache_invalidation_failed", ticker=ticker, error=str(e))
            return False
    
    async def get_from_redis(self, ticker: str) -> Optional[SECDilutionProfile]:
        """Obtener profile desde Redis"""
        try:
            redis_key = f"{self.REDIS_KEY_PREFIX}:{ticker}"
            cached_data = await self.redis.get(redis_key, deserialize=True)
            
            if not cached_data:
                return None
            
            return SECDilutionProfile(**cached_data)
            
        except Exception as e:
            logger.error("redis_get_failed", ticker=ticker, error=str(e))
            return None
    
    async def save_to_redis(self, ticker: str, profile: SECDilutionProfile) -> bool:
        """Guardar profile en Redis"""
        try:
            redis_key = f"{self.REDIS_KEY_PREFIX}:{ticker}"
            
            profile_dict = profile.dict()
            profile_dict = self.serialize_for_redis(profile_dict)
            
            await self.redis.set(
                redis_key,
                profile_dict,
                ttl=self.REDIS_TTL,
                serialize=True
            )
            
            logger.info("redis_save_success", ticker=ticker)
            return True
            
        except Exception as e:
            logger.error("redis_save_failed", ticker=ticker, error=str(e))
            return False
    
    @staticmethod
    def parse_price(value: Any) -> Optional[float]:
        """Parsear precio limpiando símbolos como $ y comas"""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            cleaned = value.replace('$', '').replace('€', '').replace(',', '').strip()
            if not cleaned:
                return None
            try:
                return float(cleaned)
            except ValueError:
                return None
        return None
    
    @staticmethod
    def serialize_for_redis(data: Any) -> Any:
        """Convertir Decimals, dates y datetimes a JSON-serializable"""
        if isinstance(data, dict):
            return {k: CacheService.serialize_for_redis(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [CacheService.serialize_for_redis(item) for item in data]
        elif isinstance(data, Decimal):
            return float(data)
        elif isinstance(data, datetime):
            return data.isoformat()
        elif isinstance(data, date):
            return data.isoformat()
        else:
            return data


# Singleton instance
_cache_service: Optional[CacheService] = None


def get_cache_service(
    redis: RedisClient = None, 
    repository: SECDilutionRepository = None
) -> Optional[CacheService]:
    """Get or create cache service instance"""
    global _cache_service
    if _cache_service is None and redis and repository:
        _cache_service = CacheService(redis, repository)
    return _cache_service

