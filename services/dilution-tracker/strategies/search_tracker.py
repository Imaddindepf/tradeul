"""
Search Tracker
Rastrea búsquedas de usuarios para optimizar sincronización y cache
"""

import sys
sys.path.append('/app')

from typing import List, Dict, Optional
from datetime import datetime, timedelta
from uuid import UUID

from shared.utils.timescale_client import TimescaleClient
from shared.utils.redis_client import RedisClient
from shared.utils.logger import get_logger

logger = get_logger(__name__)


class SearchTracker:
    """
    Rastrea búsquedas de tickers para:
    1. Identificar tickers populares
    2. Pre-warm cache de tickers frecuentes
    3. Promover tickers a tiers superiores
    4. Mejorar experiencia de usuario
    """
    
    def __init__(
        self,
        db: TimescaleClient,
        redis: RedisClient
    ):
        self.db = db
        self.redis = redis
        
        # Redis keys
        self.POPULARITY_KEY = "dilution:ticker:popularity"
        self.RECENT_SEARCHES_KEY = "dilution:recent_searches"
        self.TRENDING_KEY = "dilution:trending:7d"
    
    async def track_search(
        self,
        ticker: str,
        user_id: Optional[UUID] = None,
        session_id: Optional[str] = None
    ) -> bool:
        """
        Registrar búsqueda de ticker
        
        Args:
            ticker: Símbolo buscado
            user_id: ID de usuario (opcional)
            session_id: ID de sesión (opcional)
        
        Returns:
            True si se registró exitosamente
        """
        try:
            ticker = ticker.upper()
            
            # 1. Guardar en BD para histórico
            await self._save_to_db(ticker, user_id, session_id)
            
            # 2. Incrementar contador en Redis (para ranking en tiempo real)
            await self.redis.zincrby(self.POPULARITY_KEY, 1, ticker)
            
            # 3. Agregar a lista de búsquedas recientes
            await self._add_to_recent(ticker)
            
            # 4. Actualizar contadores en ticker_sync_config (trigger automático)
            # El trigger SQL lo hará automáticamente
            
            logger.debug("search_tracked", ticker=ticker)
            return True
            
        except Exception as e:
            logger.error("search_tracking_failed", ticker=ticker, error=str(e))
            return False
    
    async def _save_to_db(
        self,
        ticker: str,
        user_id: Optional[UUID],
        session_id: Optional[str]
    ):
        """Guardar búsqueda en BD"""
        query = """
        INSERT INTO dilution_searches (ticker, user_id, session_id, searched_at)
        VALUES ($1, $2, $3, NOW())
        """
        await self.db.execute(query, ticker, user_id, session_id)
    
    async def _add_to_recent(self, ticker: str):
        """Agregar a lista de búsquedas recientes (últimos 100)"""
        # Usar lista con timestamp
        data = {
            'ticker': ticker,
            'timestamp': datetime.now().isoformat()
        }
        
        await self.redis.lpush(self.RECENT_SEARCHES_KEY, data)
        
        # Mantener solo últimos 100
        await self.redis.ltrim(self.RECENT_SEARCHES_KEY, 0, 99)
    
    async def get_trending_tickers(
        self,
        days: int = 7,
        limit: int = 100
    ) -> List[Dict]:
        """
        Obtener tickers más buscados en los últimos N días
        
        Args:
            days: Número de días atrás
            limit: Límite de resultados
        
        Returns:
            Lista de tickers con conteo de búsquedas
        """
        try:
            # Intentar desde cache Redis primero
            if days == 7:
                cached = await self.redis.get(self.TRENDING_KEY)
                if cached:
                    return cached
            
            # Consultar BD
            query = """
            SELECT 
                ticker,
                COUNT(*) as search_count,
                COUNT(DISTINCT COALESCE(user_id::text, session_id)) as unique_searches,
                MAX(searched_at) as last_searched
            FROM dilution_searches
            WHERE searched_at > NOW() - INTERVAL '1 day' * $1
            GROUP BY ticker
            ORDER BY search_count DESC
            LIMIT $2
            """
            
            results = await self.db.fetch(query, days, limit)
            
            trending = [
                {
                    'ticker': row['ticker'],
                    'search_count': row['search_count'],
                    'unique_searches': row['unique_searches'],
                    'last_searched': row['last_searched'].isoformat()
                }
                for row in results
            ]
            
            # Cachear resultados si es el query de 7 días
            if days == 7:
                await self.redis.set(
                    self.TRENDING_KEY,
                    trending,
                    ttl=3600  # 1 hora
                )
            
            logger.info("trending_tickers_fetched", count=len(trending), days=days)
            return trending
            
        except Exception as e:
            logger.error("get_trending_failed", error=str(e))
            return []
    
    async def get_popular_tickers_realtime(self, limit: int = 50) -> List[Dict]:
        """
        Obtener tickers más populares desde Redis (tiempo real)
        
        Returns:
            Lista de tickers ordenados por popularidad
        """
        try:
            # Obtener top N desde sorted set
            results = await self.redis.zrevrange(
                self.POPULARITY_KEY,
                0,
                limit - 1,
                withscores=True
            )
            
            if not results:
                return []
            
            popular = [
                {
                    'ticker': ticker,
                    'popularity_score': int(score)
                }
                for ticker, score in results
            ]
            
            return popular
            
        except Exception as e:
            logger.error("get_popular_realtime_failed", error=str(e))
            return []
    
    async def get_recent_searches(self, limit: int = 20) -> List[Dict]:
        """
        Obtener búsquedas más recientes
        
        Returns:
            Lista de búsquedas recientes
        """
        try:
            recent = await self.redis.lrange(
                self.RECENT_SEARCHES_KEY,
                0,
                limit - 1
            )
            
            return recent if recent else []
            
        except Exception as e:
            logger.error("get_recent_searches_failed", error=str(e))
            return []
    
    async def get_ticker_search_stats(self, ticker: str) -> Optional[Dict]:
        """
        Obtener estadísticas de búsqueda para un ticker específico
        
        Returns:
            Dict con estadísticas
        """
        try:
            ticker = ticker.upper()
            
            query = """
            SELECT 
                COUNT(*) as total_searches,
                COUNT(DISTINCT COALESCE(user_id::text, session_id)) as unique_users,
                MIN(searched_at) as first_search,
                MAX(searched_at) as last_search,
                COUNT(CASE WHEN searched_at > NOW() - INTERVAL '7 days' THEN 1 END) as searches_7d,
                COUNT(CASE WHEN searched_at > NOW() - INTERVAL '30 days' THEN 1 END) as searches_30d
            FROM dilution_searches
            WHERE ticker = $1
            """
            
            result = await self.db.fetchrow(query, ticker)
            
            if not result or result['total_searches'] == 0:
                return None
            
            # Obtener ranking desde Redis
            rank = await self.redis.zrevrank(self.POPULARITY_KEY, ticker)
            
            return {
                'ticker': ticker,
                'total_searches': result['total_searches'],
                'unique_users': result['unique_users'],
                'first_search': result['first_search'].isoformat() if result['first_search'] else None,
                'last_search': result['last_search'].isoformat() if result['last_search'] else None,
                'searches_7d': result['searches_7d'],
                'searches_30d': result['searches_30d'],
                'popularity_rank': rank + 1 if rank is not None else None
            }
            
        except Exception as e:
            logger.error("get_ticker_stats_failed", ticker=ticker, error=str(e))
            return None
    
    async def identify_warming_candidates(
        self,
        min_searches: int = 10,
        days: int = 7
    ) -> List[str]:
        """
        Identificar tickers que deberían pre-warmearse en cache
        
        Args:
            min_searches: Mínimo de búsquedas requeridas
            days: Período en días
        
        Returns:
            Lista de tickers candidatos
        """
        try:
            query = """
            SELECT ticker, COUNT(*) as search_count
            FROM dilution_searches
            WHERE searched_at > NOW() - INTERVAL '1 day' * $2
            GROUP BY ticker
            HAVING COUNT(*) >= $1
            ORDER BY search_count DESC
            """
            
            results = await self.db.fetch(query, min_searches, days)
            
            candidates = [r['ticker'] for r in results]
            
            logger.info(
                "warming_candidates_identified",
                count=len(candidates),
                min_searches=min_searches,
                days=days
            )
            
            return candidates
            
        except Exception as e:
            logger.error("identify_warming_candidates_failed", error=str(e))
            return []
    
    async def should_ticker_be_cached(self, ticker: str) -> bool:
        """
        Determinar si un ticker debería estar en cache
        basado en popularidad
        
        Returns:
            True si debería estar en cache
        """
        try:
            ticker = ticker.upper()
            
            # Obtener conteo de búsquedas últimos 7 días
            query = """
            SELECT COUNT(*) as count
            FROM dilution_searches
            WHERE ticker = $1 AND searched_at > NOW() - INTERVAL '7 days'
            """
            
            result = await self.db.fetchrow(query, ticker)
            count = result['count'] if result else 0
            
            # Cachear si tiene 3+ búsquedas en 7 días
            return count >= 3
            
        except Exception as e:
            logger.error("should_cache_check_failed", ticker=ticker, error=str(e))
            return False
    
    async def cleanup_old_searches(self, days: int = 90):
        """
        Limpiar búsquedas antiguas de la BD
        (mantener solo últimos N días)
        
        Args:
            days: Días a mantener
        """
        try:
            query = """
            DELETE FROM dilution_searches
            WHERE searched_at < NOW() - INTERVAL '1 day' * $1
            """
            
            result = await self.db.execute(query, days)
            
            logger.info("old_searches_cleaned", days=days)
            
        except Exception as e:
            logger.error("cleanup_old_searches_failed", error=str(e))
    
    async def get_search_analytics(self) -> Dict:
        """
        Obtener analytics generales de búsquedas
        
        Returns:
            Dict con métricas de analytics
        """
        try:
            query = """
            SELECT 
                COUNT(*) as total_searches,
                COUNT(DISTINCT ticker) as unique_tickers,
                COUNT(DISTINCT COALESCE(user_id::text, session_id)) as unique_users,
                COUNT(CASE WHEN searched_at > NOW() - INTERVAL '24 hours' THEN 1 END) as searches_24h,
                COUNT(CASE WHEN searched_at > NOW() - INTERVAL '7 days' THEN 1 END) as searches_7d,
                COUNT(CASE WHEN searched_at > NOW() - INTERVAL '30 days' THEN 1 END) as searches_30d
            FROM dilution_searches
            WHERE searched_at > NOW() - INTERVAL '90 days'
            """
            
            result = await self.db.fetchrow(query)
            
            return {
                'total_searches': result['total_searches'],
                'unique_tickers': result['unique_tickers'],
                'unique_users': result['unique_users'],
                'searches_24h': result['searches_24h'],
                'searches_7d': result['searches_7d'],
                'searches_30d': result['searches_30d'],
                'avg_searches_per_day': round(result['searches_30d'] / 30, 2)
            }
            
        except Exception as e:
            logger.error("get_search_analytics_failed", error=str(e))
            return {}

