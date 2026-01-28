"""
Configuration Manager for Prediction Markets
Loads runtime config from database (cache TTL, thresholds, etc.)
"""

from typing import Optional, Dict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import asyncio
import structlog
import asyncpg

logger = structlog.get_logger(__name__)


@dataclass
class LoadedConfig:
    """Runtime configuration from database"""
    config_values: Dict[str, str] = field(default_factory=dict)
    loaded_at: Optional[datetime] = None
    is_from_db: bool = False


class ConfigurationManager:
    """Manages runtime configuration from database (TTL, thresholds, etc.)"""
    
    def __init__(self, database_url: Optional[str] = None, cache_ttl_seconds: int = 300):
        self._database_url = database_url
        self._cache_ttl = timedelta(seconds=cache_ttl_seconds)
        self._pool: Optional[asyncpg.Pool] = None
        self._config: Optional[LoadedConfig] = None
        self._lock = asyncio.Lock()
        
    async def connect(self, database_url: Optional[str] = None) -> bool:
        url = database_url or self._database_url
        if not url:
            logger.warning("no_database_url", using="defaults")
            return False
        try:
            self._pool = await asyncpg.create_pool(url, min_size=1, max_size=5, command_timeout=10)
            logger.info("config_manager_connected")
            return True
        except Exception as e:
            logger.error("config_manager_connection_failed", error=str(e))
            return False
    
    async def disconnect(self):
        if self._pool:
            await self._pool.close()
            self._pool = None
    
    async def get_config(self, force_reload: bool = False) -> LoadedConfig:
        async with self._lock:
            if not force_reload and self._config and self._config.loaded_at:
                if datetime.utcnow() - self._config.loaded_at < self._cache_ttl:
                    return self._config
            
            if self._pool:
                try:
                    self._config = await self._load_from_database()
                    return self._config
                except Exception as e:
                    logger.error("config_load_failed", error=str(e))
            
            if not self._config:
                self._config = self._get_default_config()
            return self._config
    
    async def _load_from_database(self) -> LoadedConfig:
        async with self._pool.acquire() as conn:
            config = LoadedConfig(loaded_at=datetime.utcnow(), is_from_db=True)
            try:
                cfgs = await conn.fetch("SELECT key, value FROM prediction_market_config")
                for c in cfgs:
                    config.config_values[c['key']] = str(c['value']).strip('"')
                logger.info("config_loaded_from_db", values=len(config.config_values))
            except Exception:
                pass  # Table might not exist
            return config
    
    def _get_default_config(self) -> LoadedConfig:
        logger.info("config_using_defaults")
        return LoadedConfig(
            config_values={},
            loaded_at=datetime.utcnow(),
            is_from_db=False,
        )
    
    # Config accessors
    async def get_cache_ttl(self) -> int:
        return int((await self.get_config()).config_values.get('cache_ttl_seconds', '300'))
    
    async def get_refresh_interval(self) -> int:
        return int((await self.get_config()).config_values.get('refresh_interval_seconds', '300'))
