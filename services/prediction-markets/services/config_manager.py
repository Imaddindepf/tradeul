"""Configuration Manager for Prediction Markets - Loads config from database"""

from typing import Optional, Dict, List, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import asyncio
import structlog
import asyncpg

from models.categories import (
    CategoryConfig, SubcategoryConfig,
    DEFAULT_CATEGORIES, DEFAULT_WHITELIST_TAGS, DEFAULT_BLACKLIST_TAGS,
)

logger = structlog.get_logger(__name__)


@dataclass
class LoadedConfig:
    """Loaded configuration from database"""
    categories: Dict[str, CategoryConfig] = field(default_factory=dict)
    whitelist_tags: Set[str] = field(default_factory=set)
    blacklist_tags: Set[str] = field(default_factory=set)
    tag_category_mapping: Dict[str, Tuple[str, Optional[str]]] = field(default_factory=dict)
    tag_relevance_boost: Dict[str, float] = field(default_factory=dict)
    config_values: Dict[str, str] = field(default_factory=dict)
    loaded_at: Optional[datetime] = None
    is_from_db: bool = False


class ConfigurationManager:
    """Manages dynamic configuration loading from database."""
    
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
            
            cats = await conn.fetch("SELECT * FROM prediction_market_categories WHERE is_active=TRUE ORDER BY priority")
            subs = await conn.fetch("SELECT * FROM prediction_market_subcategories WHERE is_active=TRUE ORDER BY priority")
            kws = await conn.fetch("SELECT * FROM prediction_market_keywords WHERE is_active=TRUE")
            
            for cat in cats:
                subcategories = {}
                for sub in [s for s in subs if s['category_id'] == cat['id']]:
                    keywords = [k['keyword'] for k in kws if k['category_id']==cat['id'] and k['subcategory_id']==sub['id']]
                    subcategories[sub['id']] = SubcategoryConfig(id=sub['id'], name=sub['name'], keywords=keywords, priority=sub['priority'])
                config.categories[cat['id']] = CategoryConfig(id=cat['id'], name=cat['name'], priority=cat['priority'], subcategories=subcategories)
            
            tags = await conn.fetch("SELECT * FROM prediction_market_tag_rules WHERE is_active=TRUE")
            for t in tags:
                if t['rule_type'] == 'blacklist':
                    config.blacklist_tags.add(t['tag_slug'])
                else:
                    config.whitelist_tags.add(t['tag_slug'])
                    if t['target_category_id']:
                        config.tag_category_mapping[t['tag_slug']] = (t['target_category_id'], t['target_subcategory_id'])
                    if t['relevance_boost']:
                        config.tag_relevance_boost[t['tag_slug']] = float(t['relevance_boost'])
            
            cfgs = await conn.fetch("SELECT key, value FROM prediction_market_config")
            for c in cfgs:
                config.config_values[c['key']] = str(c['value']).strip('"')
            
            logger.info("config_loaded_from_db", categories=len(config.categories))
            return config
    
    def _get_default_config(self) -> LoadedConfig:
        logger.info("config_using_defaults")
        return LoadedConfig(
            categories=DEFAULT_CATEGORIES.copy(),
            whitelist_tags=DEFAULT_WHITELIST_TAGS.copy(),
            blacklist_tags=DEFAULT_BLACKLIST_TAGS.copy(),
            loaded_at=datetime.utcnow(), is_from_db=False,
        )
    
    # Config accessors
    async def get_min_volume_threshold(self) -> float:
        return float((await self.get_config()).config_values.get('min_volume_threshold', '100000'))
    
    async def get_min_relevance_score(self) -> float:
        return float((await self.get_config()).config_values.get('min_relevance_score', '0.2'))
    
    async def get_cache_ttl(self) -> int:
        return int((await self.get_config()).config_values.get('cache_ttl_seconds', '300'))
    
    async def get_refresh_interval(self) -> int:
        return int((await self.get_config()).config_values.get('refresh_interval_seconds', '300'))
    
    async def get_max_events_per_category(self) -> int:
        return int((await self.get_config()).config_values.get('max_events_per_category', '50'))
    
    async def is_price_history_enabled(self) -> bool:
        return (await self.get_config()).config_values.get('price_history_enabled', 'true').lower() == 'true'
    
    async def get_max_price_history_markets(self) -> int:
        return int((await self.get_config()).config_values.get('max_price_history_markets', '50'))
    
    # Admin methods
    async def add_keyword(self, category_id: str, subcategory_id: str, keyword: str) -> bool:
        if not self._pool: return False
        try:
            async with self._pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO prediction_market_keywords (category_id, subcategory_id, keyword) 
                    VALUES ($1, $2, $3) 
                    ON CONFLICT (category_id, subcategory_id, keyword) 
                    DO UPDATE SET is_active=TRUE
                """, category_id, subcategory_id, keyword.lower())
            self._config = None
            return True
        except Exception as e:
            import structlog
            structlog.get_logger().error("add_keyword_error", error=str(e))
            return False
    
    async def add_tag_rule(self, tag_slug: str, rule_type: str, target_category_id: str = None) -> bool:
        if not self._pool or rule_type not in ('whitelist', 'blacklist'): return False
        try:
            async with self._pool.acquire() as conn:
                await conn.execute("""INSERT INTO prediction_market_tag_rules (tag_slug, rule_type, target_category_id)
                    VALUES ($1, $2, $3) ON CONFLICT (tag_slug) DO UPDATE SET rule_type=EXCLUDED.rule_type, is_active=TRUE""",
                    tag_slug.lower(), rule_type, target_category_id)
            self._config = None
            return True
        except: return False
    
    async def update_config_value(self, key: str, value: str) -> bool:
        if not self._pool: return False
        try:
            async with self._pool.acquire() as conn:
                await conn.execute("""INSERT INTO prediction_market_config (key, value) VALUES ($1, $2)
                    ON CONFLICT (key) DO UPDATE SET value=$2, updated_at=NOW()""", key, value)
            self._config = None
            return True
        except: return False
    
    async def get_all_keywords(self) -> List[Dict]:
        if not self._pool: return []
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM prediction_market_keywords ORDER BY category_id, subcategory_id")
            return [dict(r) for r in rows]
    
    async def get_all_tag_rules(self) -> List[Dict]:
        if not self._pool: return []
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM prediction_market_tag_rules ORDER BY rule_type, tag_slug")
            return [dict(r) for r in rows]
