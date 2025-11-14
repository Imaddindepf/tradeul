"""
Tier Manager
Gestiona la clasificación de tickers en tiers según popularidad y prioridad
"""

import sys
sys.path.append('/app')

from typing import List, Dict, Optional
from datetime import datetime

from shared.utils.timescale_client import TimescaleClient
from shared.utils.redis_client import RedisClient
from shared.utils.logger import get_logger

from ..models.sync_models import SyncTier, SyncFrequency, TierStats

logger = get_logger(__name__)


class TierManager:
    """
    Gestiona tiers de tickers para sincronización óptima
    
    Tier 1: Top 500 tickers (daily sync)
    - Market cap > $1B
    - Volume > 500K/día
    - Búsquedas frecuentes (>20 en 30 días)
    
    Tier 2: Mid 2000 tickers (weekly sync)
    - Market cap $100M - $1B
    - Volume > 100K/día
    - Búsquedas ocasionales (5-20 en 30 días)
    
    Tier 3: Long tail ~8500 tickers (on-demand only)
    - Resto de tickers
    - Solo sincronizar cuando usuario lo solicita
    """
    
    def __init__(
        self,
        db: TimescaleClient,
        redis: RedisClient
    ):
        self.db = db
        self.redis = redis
        
        # Tier limits
        self.TIER_1_LIMIT = 500
        self.TIER_2_LIMIT = 2000
        
        # Thresholds
        self.TIER_1_SEARCH_THRESHOLD = 20  # searches in 30 days
        self.TIER_2_SEARCH_THRESHOLD = 5
    
    async def classify_all_tickers(self) -> Dict[str, int]:
        """
        Clasificar todos los tickers en tiers
        
        Returns:
            Dict con conteo por tier
        """
        logger.info("tier_classification_started")
        
        try:
            # Obtener todos los tickers activos con metadata
            query = """
            SELECT 
                tm.symbol,
                tm.market_cap,
                tm.avg_volume_30d,
                COALESCE(tsc.search_count_30d, 0) as search_count
            FROM ticker_metadata tm
            LEFT JOIN ticker_sync_config tsc ON tm.symbol = tsc.ticker
            WHERE tm.is_actively_trading = TRUE
            """
            
            tickers = await self.db.fetch(query)
            logger.info("tickers_fetched", count=len(tickers))
            
            # Calcular priority score para cada ticker
            scored_tickers = []
            for ticker in tickers:
                score = self._calculate_priority_score(
                    market_cap=ticker['market_cap'],
                    avg_volume=ticker['avg_volume_30d'],
                    search_count=ticker['search_count']
                )
                
                scored_tickers.append({
                    'symbol': ticker['symbol'],
                    'score': score,
                    'search_count': ticker['search_count']
                })
            
            # Ordenar por score descendente
            scored_tickers.sort(key=lambda x: x['score'], reverse=True)
            
            # Asignar tiers
            tier_1_tickers = []
            tier_2_tickers = []
            tier_3_tickers = []
            
            for i, ticker in enumerate(scored_tickers):
                symbol = ticker['symbol']
                score = ticker['score']
                search_count = ticker['search_count']
                
                # Determinar tier
                if i < self.TIER_1_LIMIT or search_count >= self.TIER_1_SEARCH_THRESHOLD:
                    tier = SyncTier.TIER_1
                    tier_1_tickers.append(symbol)
                elif i < (self.TIER_1_LIMIT + self.TIER_2_LIMIT) or search_count >= self.TIER_2_SEARCH_THRESHOLD:
                    tier = SyncTier.TIER_2
                    tier_2_tickers.append(symbol)
                else:
                    tier = SyncTier.TIER_3
                    tier_3_tickers.append(symbol)
                
                # Guardar en BD
                await self._save_tier_config(
                    symbol=symbol,
                    tier=tier,
                    search_count=search_count,
                    priority_score=score
                )
            
            # Actualizar Redis sets
            await self._update_redis_tiers(
                tier_1=tier_1_tickers,
                tier_2=tier_2_tickers,
                tier_3=tier_3_tickers
            )
            
            counts = {
                'tier_1': len(tier_1_tickers),
                'tier_2': len(tier_2_tickers),
                'tier_3': len(tier_3_tickers),
                'total': len(scored_tickers)
            }
            
            logger.info("tier_classification_completed", **counts)
            return counts
            
        except Exception as e:
            logger.error("tier_classification_failed", error=str(e))
            raise
    
    def _calculate_priority_score(
        self,
        market_cap: Optional[int],
        avg_volume: Optional[int],
        search_count: int
    ) -> float:
        """
        Calcular priority score para un ticker
        
        Formula:
        score = (market_cap / 1M) * 0.3 +
                (avg_volume / 10K) * 0.3 +
                (search_count * 1000) * 0.4
        """
        score = 0.0
        
        # Market cap weight (30%)
        if market_cap:
            score += (market_cap / 1_000_000) * 0.3
        
        # Volume weight (30%)
        if avg_volume:
            score += (avg_volume / 10_000) * 0.3
        
        # Search count weight (40%) - user interest is most important
        score += search_count * 1000 * 0.4
        
        return round(score, 2)
    
    async def _save_tier_config(
        self,
        symbol: str,
        tier: SyncTier,
        search_count: int,
        priority_score: float
    ):
        """Guardar configuración de tier en BD"""
        
        sync_frequency = {
            SyncTier.TIER_1: SyncFrequency.DAILY,
            SyncTier.TIER_2: SyncFrequency.WEEKLY,
            SyncTier.TIER_3: SyncFrequency.ON_DEMAND
        }[tier]
        
        query = """
        INSERT INTO ticker_sync_config (
            ticker, tier, sync_frequency, search_count_30d, priority_score, updated_at
        )
        VALUES ($1, $2, $3, $4, $5, NOW())
        ON CONFLICT (ticker) DO UPDATE SET
            tier = EXCLUDED.tier,
            sync_frequency = EXCLUDED.sync_frequency,
            search_count_30d = EXCLUDED.search_count_30d,
            priority_score = EXCLUDED.priority_score,
            updated_at = NOW()
        """
        
        await self.db.execute(
            query,
            symbol,
            tier.value,
            sync_frequency.value,
            search_count,
            priority_score
        )
    
    async def _update_redis_tiers(
        self,
        tier_1: List[str],
        tier_2: List[str],
        tier_3: List[str]
    ):
        """Actualizar Redis sets con tiers"""
        
        # Limpiar sets anteriores
        await self.redis.delete("dilution:tiers:tier_1")
        await self.redis.delete("dilution:tiers:tier_2")
        await self.redis.delete("dilution:tiers:tier_3")
        
        # Agregar nuevos tickers a cada tier
        if tier_1:
            await self.redis.sadd("dilution:tiers:tier_1", *tier_1)
        
        if tier_2:
            await self.redis.sadd("dilution:tiers:tier_2", *tier_2)
        
        if tier_3:
            await self.redis.sadd("dilution:tiers:tier_3", *tier_3)
        
        logger.info("redis_tiers_updated")
    
    async def promote_ticker(self, ticker: str) -> bool:
        """
        Promover ticker a tier superior si cumple condiciones
        
        Returns:
            True si fue promovido
        """
        try:
            # Obtener configuración actual
            config = await self._get_ticker_config(ticker)
            
            if not config:
                logger.warning("ticker_config_not_found", ticker=ticker)
                return False
            
            current_tier = config['tier']
            search_count = config['search_count_30d']
            
            # No se puede promover desde Tier 1
            if current_tier == SyncTier.TIER_1.value:
                return False
            
            # Tier 3 → Tier 2: needs 5+ searches
            if current_tier == SyncTier.TIER_3.value and search_count >= self.TIER_2_SEARCH_THRESHOLD:
                await self._change_tier(ticker, SyncTier.TIER_2)
                logger.info("ticker_promoted", ticker=ticker, from_tier=3, to_tier=2)
                return True
            
            # Tier 2 → Tier 1: needs 20+ searches
            if current_tier == SyncTier.TIER_2.value and search_count >= self.TIER_1_SEARCH_THRESHOLD:
                await self._change_tier(ticker, SyncTier.TIER_1)
                logger.info("ticker_promoted", ticker=ticker, from_tier=2, to_tier=1)
                return True
            
            return False
            
        except Exception as e:
            logger.error("ticker_promotion_failed", ticker=ticker, error=str(e))
            return False
    
    async def demote_ticker(self, ticker: str) -> bool:
        """
        Degradar ticker a tier inferior si cumple condiciones
        
        Returns:
            True si fue degradado
        """
        try:
            config = await self._get_ticker_config(ticker)
            
            if not config:
                return False
            
            current_tier = config['tier']
            search_count = config['search_count_30d']
            last_synced = config['last_synced_at']
            
            # No se puede degradar desde Tier 3
            if current_tier == SyncTier.TIER_3.value:
                return False
            
            # Degradar si no hay búsquedas y último sync > 60 días
            if search_count == 0:
                if last_synced is None:
                    days_since_sync = 999
                else:
                    days_since_sync = (datetime.now() - last_synced).days
                
                if days_since_sync > 60:
                    new_tier = SyncTier(current_tier + 1)
                    await self._change_tier(ticker, new_tier)
                    logger.info("ticker_demoted", ticker=ticker, from_tier=current_tier, to_tier=new_tier.value)
                    return True
            
            return False
            
        except Exception as e:
            logger.error("ticker_demotion_failed", ticker=ticker, error=str(e))
            return False
    
    async def _get_ticker_config(self, ticker: str) -> Optional[Dict]:
        """Obtener configuración actual de ticker"""
        query = """
        SELECT ticker, tier, search_count_30d, last_synced_at
        FROM ticker_sync_config
        WHERE ticker = $1
        """
        return await self.db.fetchrow(query, ticker.upper())
    
    async def _change_tier(self, ticker: str, new_tier: SyncTier):
        """Cambiar tier de un ticker"""
        
        sync_frequency = {
            SyncTier.TIER_1: SyncFrequency.DAILY,
            SyncTier.TIER_2: SyncFrequency.WEEKLY,
            SyncTier.TIER_3: SyncFrequency.ON_DEMAND
        }[new_tier]
        
        # Actualizar BD
        query = """
        UPDATE ticker_sync_config
        SET tier = $2, sync_frequency = $3, updated_at = NOW()
        WHERE ticker = $1
        """
        await self.db.execute(query, ticker.upper(), new_tier.value, sync_frequency.value)
        
        # Actualizar Redis
        # Remover de todos los tiers
        await self.redis.srem("dilution:tiers:tier_1", ticker.upper())
        await self.redis.srem("dilution:tiers:tier_2", ticker.upper())
        await self.redis.srem("dilution:tiers:tier_3", ticker.upper())
        
        # Agregar al nuevo tier
        tier_key = f"dilution:tiers:tier_{new_tier.value}"
        await self.redis.sadd(tier_key, ticker.upper())
    
    async def get_tier_stats(self) -> Dict[int, TierStats]:
        """
        Obtener estadísticas de cada tier
        
        Returns:
            Dict con stats por tier
        """
        stats = {}
        
        for tier in [1, 2, 3]:
            query = """
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN search_count_30d >= $2 THEN 1 END) as popular
            FROM ticker_sync_config
            WHERE tier = $1
            """
            
            threshold = {
                1: self.TIER_1_SEARCH_THRESHOLD,
                2: self.TIER_2_SEARCH_THRESHOLD,
                3: 0
            }[tier]
            
            result = await self.db.fetchrow(query, tier, threshold)
            
            sync_freq = {
                1: "daily",
                2: "weekly",
                3: "on-demand"
            }[tier]
            
            stats[tier] = TierStats(
                tier=tier,
                total_tickers=result['total'],
                sync_frequency=sync_freq,
                tickers_needing_sync=0,  # To be implemented
                popular_tickers=result['popular']
            )
        
        return stats
    
    async def get_tickers_by_tier(self, tier: SyncTier) -> List[str]:
        """
        Obtener lista de tickers en un tier específico
        
        Returns:
            Lista de símbolos
        """
        # Intentar desde Redis primero (más rápido)
        redis_key = f"dilution:tiers:tier_{tier.value}"
        tickers = await self.redis.smembers(redis_key)
        
        if tickers:
            return list(tickers)
        
        # Fallback a BD si Redis está vacío
        query = """
        SELECT ticker
        FROM ticker_sync_config
        WHERE tier = $1
        ORDER BY priority_score DESC
        """
        
        results = await self.db.fetch(query, tier.value)
        return [r['ticker'] for r in results]

