"""
Sync Redis Task
Sincroniza caches de Redis con datos actualizados de TimescaleDB
"""

import asyncio
import sys
sys.path.append('/app')

import json
from datetime import date
from typing import Dict, List

from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import get_logger

logger = get_logger(__name__)


class SyncRedisTask:
    """
    Tarea: Sincronizar caches de Redis
    
    Sincroniza:
    - Metadata de tickers (market cap, float, sector)
    - Promedios de volumen (30 días)
    - ATR calculado
    - Otros indicadores cacheados
    """
    
    name = "redis_sync"
    
    def __init__(self, redis_client: RedisClient, timescale_client: TimescaleClient):
        self.redis = redis_client
        self.db = timescale_client
    
    async def execute(self, target_date: date) -> Dict:
        """
        Ejecutar sincronización de Redis
        
        Args:
            target_date: Fecha objetivo
        
        Returns:
            Dict con resultado
        """
        logger.info("redis_sync_task_starting")
        
        try:
            # 1. Sincronizar metadata
            metadata_synced = await self._sync_metadata()
            
            # 2. Sincronizar promedios de volumen
            volume_avg_synced = await self._sync_volume_averages()
            
            # 3. Limpiar caches obsoletos
            cleaned = await self._cleanup_old_caches()
            
            logger.info(
                "redis_sync_task_completed",
                metadata_synced=metadata_synced,
                volume_avg_synced=volume_avg_synced,
                caches_cleaned=cleaned
            )
            
            return {
                "success": True,
                "metadata_synced": metadata_synced,
                "volume_avg_synced": volume_avg_synced,
                "caches_cleaned": cleaned
            }
        
        except Exception as e:
            logger.error(
                "redis_sync_task_failed",
                error=str(e),
                error_type=type(e).__name__
            )
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _sync_metadata(self) -> int:
        """
        Sincronizar metadata de tickers a Redis
        
        Formato Redis:
        ticker:metadata:{symbol} = {
            "market_cap": ...,
            "float_shares": ...,
            "sector": ...,
            "industry": ...,
            ...
        }
        """
        try:
            # Obtener toda la metadata de TimescaleDB
            query = """
                SELECT 
                    symbol,
                    market_cap,
                    float_shares,
                    shares_outstanding,
                    sector,
                    industry,
                    avg_volume_30d
                FROM ticker_metadata
                WHERE market_cap IS NOT NULL
                   OR sector IS NOT NULL
            """
            
            rows = await self.db.fetch(query)
            
            if not rows:
                logger.warning("no_metadata_to_sync")
                return 0
            
            # Sincronizar a Redis en batch
            pipeline = self.redis.client.pipeline()
            
            for row in rows:
                key = f"ticker:metadata:{row['symbol']}"
                data = {
                    "symbol": row['symbol'],
                    "market_cap": row['market_cap'],
                    "float_shares": row['float_shares'],
                    "shares_outstanding": row['shares_outstanding'],
                    "sector": row['sector'],
                    "industry": row['industry'],
                    "avg_volume_30d": row['avg_volume_30d']
                }
                
                # Eliminar campos None
                data = {k: v for k, v in data.items() if v is not None}
                
                pipeline.set(key, json.dumps(data), ex=86400)  # TTL 24h
            
            await pipeline.execute()
            
            logger.info(
                "metadata_synced_to_redis",
                count=len(rows)
            )
            
            return len(rows)
        
        except Exception as e:
            logger.error("metadata_sync_failed", error=str(e))
            return 0
    
    async def _sync_volume_averages(self) -> int:
        """
        Sincronizar promedios de volumen a Redis
        
        Formato Redis:
        ticker:avg_volume:{symbol} = {
            "avg_volume_30d": ...,
            "avg_volume_10d": ...,
            "avg_volume_5d": ...
        }
        """
        try:
            # Calcular promedios de volumen (30, 10, 5 días)
            query = """
                WITH recent_data AS (
                    SELECT 
                        symbol,
                        trading_date as date,
                        volume,
                        ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY trading_date DESC) as rn
                    FROM market_data_daily
                    WHERE trading_date >= CURRENT_DATE - INTERVAL '30 days'
                )
                SELECT 
                    symbol,
                    AVG(CASE WHEN rn <= 30 THEN volume END) as avg_volume_30d,
                    AVG(CASE WHEN rn <= 10 THEN volume END) as avg_volume_10d,
                    AVG(CASE WHEN rn <= 5 THEN volume END) as avg_volume_5d
                FROM recent_data
                GROUP BY symbol
                HAVING COUNT(*) >= 5
            """
            
            rows = await self.db.fetch(query)
            
            if not rows:
                logger.warning("no_volume_data_to_sync")
                return 0
            
            # También actualizar ticker_metadata
            update_query = """
                UPDATE ticker_metadata
                SET avg_volume_30d = $2,
                    updated_at = NOW()
                WHERE symbol = $1
            """
            
            # Sincronizar a Redis
            pipeline = self.redis.client.pipeline()
            
            for row in rows:
                # Redis cache
                key = f"ticker:avg_volume:{row['symbol']}"
                data = {
                    "avg_volume_30d": int(row['avg_volume_30d']) if row['avg_volume_30d'] else None,
                    "avg_volume_10d": int(row['avg_volume_10d']) if row['avg_volume_10d'] else None,
                    "avg_volume_5d": int(row['avg_volume_5d']) if row['avg_volume_5d'] else None
                }
                
                pipeline.set(key, json.dumps(data), ex=86400)  # TTL 24h
                
                # Actualizar ticker_metadata también
                if row['avg_volume_30d']:
                    await self.db.execute(
                        update_query,
                        row['symbol'],
                        int(row['avg_volume_30d'])
                    )
            
            await pipeline.execute()
            
            logger.info(
                "volume_averages_synced",
                count=len(rows)
            )
            
            return len(rows)
        
        except Exception as e:
            logger.error("volume_sync_failed", error=str(e))
            return 0
    
    async def _cleanup_old_caches(self) -> int:
        """Limpiar caches obsoletos de Redis"""
        try:
            cleaned = 0
            
            # Limpiar metadata de tickers inactivos
            # (Los que ya no están en ticker_universe)
            active_symbols_query = """
                SELECT symbol FROM ticker_universe WHERE is_active = true
            """
            active_rows = await self.db.fetch(active_symbols_query)
            active_symbols = {row['symbol'] for row in active_rows}
            
            # Obtener todos los keys de metadata en Redis
            pattern = "ticker:metadata:*"
            cursor = 0
            
            while True:
                cursor, keys = await self.redis.client.scan(
                    cursor,
                    match=pattern,
                    count=100
                )
                
                for key in keys:
                    symbol = key.decode('utf-8').split(':')[-1]
                    if symbol not in active_symbols:
                        await self.redis.client.delete(key)
                        cleaned += 1
                
                if cursor == 0:
                    break
            
            if cleaned > 0:
                logger.info("old_caches_cleaned", count=cleaned)
            
            return cleaned
        
        except Exception as e:
            logger.error("cleanup_failed", error=str(e))
            return 0

