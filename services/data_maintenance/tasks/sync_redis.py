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
            # 0. Sincronizar universo de tickers (BD → Redis SET)
            universe_synced = await self._sync_universe()
            
            # 1. Sincronizar metadata
            metadata_synced = await self._sync_metadata()
            
            # 2. Sincronizar promedios de volumen
            volume_avg_synced = await self._sync_volume_averages()
            
            # 3. Limpiar caches obsoletos
            cleaned = await self._cleanup_old_caches()
            
            logger.info(
                "redis_sync_task_completed",
                universe_synced=universe_synced,
                metadata_synced=metadata_synced,
                volume_avg_synced=volume_avg_synced,
                caches_cleaned=cleaned
            )
            
            return {
                "success": True,
                "universe_synced": universe_synced,
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
    
    async def _sync_universe(self) -> int:
        """
        Sincronizar ticker_universe de BD a Redis SET
        
        Mantiene sincronizado el SET ticker:universe con la BD
        para que siempre refleje los símbolos activos.
        """
        try:
            logger.info("syncing_ticker_universe")
            
            # Obtener todos los símbolos activos de tickers_unified
            query = """
                SELECT symbol FROM tickers_unified WHERE is_actively_trading = true
            """
            rows = await self.db.fetch(query)
            symbols = [row['symbol'] for row in rows]
            
            if not symbols:
                logger.warning("no_active_symbols_in_db")
                return 0
            
            # Limpiar Redis SET anterior
            await self.redis.client.delete("ticker:universe")
            
            # Agregar todos los símbolos al SET en batch
            pipeline = self.redis.client.pipeline()
            
            batch_size = 1000
            synced = 0
            
            for i in range(0, len(symbols), batch_size):
                batch = symbols[i:i + batch_size]
                
                # SADD puede recibir múltiples valores
                if batch:
                    pipeline.sadd("ticker:universe", *batch)
                    synced += len(batch)
                
                # Ejecutar cada 1000 símbolos
                if synced % batch_size == 0:
                    await pipeline.execute()
                    pipeline = self.redis.client.pipeline()
                    logger.debug("universe_batch_synced", synced=synced)
            
            # Ejecutar batch final
            await pipeline.execute()
            
            # Verificar resultado
            redis_count = await self.redis.client.scard("ticker:universe")
            
            logger.info(
                "universe_synced",
                db_count=len(symbols),
                redis_count=redis_count,
                synced=synced
            )
            
            return synced
            
        except Exception as e:
            logger.error("universe_sync_failed", error=str(e))
            return 0
    
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
            # Obtener toda la metadata de TimescaleDB (TODOS los campos)
            query = """
                SELECT 
                    symbol, company_name, exchange, sector, industry,
                    market_cap, float_shares, shares_outstanding,
                    avg_volume_30d, avg_volume_10d, avg_price_30d, beta,
                    description, homepage_url, phone_number, address,
                    total_employees, list_date,
                    logo_url, icon_url,
                    cik, composite_figi, share_class_figi, ticker_root, ticker_suffix,
                    type, currency_name, locale, market, round_lot, delisted_utc,
                    is_etf, is_actively_trading, updated_at
                FROM tickers_unified
                WHERE is_actively_trading = true
            """
            
            rows = await self.db.fetch(query)
            
            if not rows:
                logger.warning("no_metadata_to_sync")
                return 0
            
            # Sincronizar a Redis en batch
            pipeline = self.redis.client.pipeline()
            synced_count = 0
            failed_symbols = []
            
            for row in rows:
                try:
                    key = f"metadata:ticker:{row['symbol']}"  # ✅ Formato estandarizado
                    
                    # Convertir row a dict y manejar campos especiales
                    data = dict(row)
                    
                    # Convertir datetime/date a string ISO para serialización JSON
                    if data.get('updated_at'):
                        data['updated_at'] = data['updated_at'].isoformat()
                    if data.get('delisted_utc'):
                        data['delisted_utc'] = data['delisted_utc'].isoformat()
                    if data.get('list_date'):
                        data['list_date'] = data['list_date'].isoformat()
                    
                    # Convertir address dict a JSON string si existe
                    if isinstance(data.get('address'), dict):
                        data['address'] = json.dumps(data['address'])

                    # Convertir objetos Decimal a float para JSON serialization
                    from decimal import Decimal
                    for key, value in data.items():
                        if isinstance(value, Decimal):
                            data[key] = float(value)

                    # Eliminar campos None
                    data = {k: v for k, v in data.items() if v is not None}
                    
                    # Verificar que JSON es serializable
                    json_str = json.dumps(data)
                    
                    pipeline.set(key, json_str)  # SIN TTL - persiste siempre
                    synced_count += 1
                
                except Exception as e:
                    failed_symbols.append(row['symbol'])
                    logger.error(f"failed_to_prepare_metadata", symbol=row['symbol'], error=str(e))
            
            # Ejecutar pipeline
            try:
                await pipeline.execute()
                logger.info(f"metadata_pipeline_executed", success=synced_count, failed=len(failed_symbols))
            except Exception as e:
                logger.error(f"pipeline_execute_failed", error=str(e), failed_symbols=failed_symbols[:10])
                return 0
            
            logger.info(
                "metadata_synced_to_redis",
                count=len(rows)
            )
            
            # CRÍTICO: Forzar BGSAVE para persistir datos inmediatamente
            try:
                await self.redis.client.bgsave()
                logger.info("redis_data_persisted_with_bgsave")
                
                # Esperar 2 segundos para que el save inicie
                await asyncio.sleep(2)
            except Exception as save_err:
                logger.error("bgsave_failed", error=str(save_err))
            
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
            
            # También actualizar tickers_unified
            update_query = """
                UPDATE tickers_unified
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
                
                pipeline.set(key, json.dumps(data))
                pipeline.expire(key, 86400)  # ✅ TTL de 24 horas - previene crecimiento infinito
                
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
            # (Los que ya no están en tickers_unified)
            active_symbols_query = """
                SELECT symbol FROM tickers_unified WHERE is_actively_trading = true
            """
            active_rows = await self.db.fetch(active_symbols_query)
            active_symbols = {row['symbol'] for row in active_rows}
            
            # Obtener todos los keys de metadata en Redis
            pattern = "metadata:ticker:*"  # ✅ Formato estandarizado
            cursor = 0
            
            while True:
                cursor, keys = await self.redis.client.scan(
                    cursor,
                    match=pattern,
                    count=100
                )
                
                for key in keys:
                    # Handle both bytes and str (depends on Redis client config)
                    key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                    symbol = key_str.split(':')[-1]
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

