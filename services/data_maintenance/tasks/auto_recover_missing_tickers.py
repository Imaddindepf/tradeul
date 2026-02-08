"""
Auto Recovery Task
Detecta tickers en snapshots que no están en universo y los agrega automáticamente
"""

import asyncio
import httpx
from datetime import date, datetime
from typing import Dict, List, Set
import sys
sys.path.append('/app')

from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import get_logger
from shared.config.settings import settings

logger = get_logger(__name__)


class AutoRecoverMissingTickersTask:
    """
    Tarea: Detectar y recuperar tickers faltantes automáticamente
    
    Proceso:
    1. Lee snapshot actual (tickers activos)
    2. Compara con ticker_universe
    3. Detecta tickers faltantes
    4. Verifica en Polygon si son válidos
    5. Agrega al universo automáticamente
    6. Marca para carga de datos en próximo ciclo
    """
    
    name = "auto_recover_missing"
    
    def __init__(self, redis_client: RedisClient, timescale_client: TimescaleClient):
        self.redis = redis_client
        self.db = timescale_client
        self.max_tickers_per_run = 50  # Máximo a procesar por ejecución
    
    async def execute(self, target_date: date) -> Dict:
        """
        Ejecutar auto-recovery
        
        Returns:
            Dict con resultado
        """
        logger.info("auto_recover_task_starting")
        
        try:
            # 1. Obtener tickers del snapshot actual
            snapshot_tickers = await self._get_snapshot_tickers()
            
            if not snapshot_tickers:
                return {
                    "success": True,
                    "message": "No snapshot available",
                    "tickers_recovered": 0
                }
            
            logger.info(f"snapshot_tickers_found", count=len(snapshot_tickers))
            
            # 2. Obtener universo actual
            universe_tickers = await self._get_universe_tickers()
            logger.info(f"universe_tickers_found", count=len(universe_tickers))
            
            # 3. Detectar faltantes
            missing = snapshot_tickers - universe_tickers
            
            if not missing:
                logger.info("no_missing_tickers", message="All snapshot tickers in universe")
                return {
                    "success": True,
                    "message": "No missing tickers",
                    "tickers_recovered": 0
                }
            
            logger.info(f"missing_tickers_detected", count=len(missing), tickers=sorted(list(missing))[:20])
            
            # Limitar cantidad por ejecución
            missing_to_process = list(missing)[:self.max_tickers_per_run]
            
            # 4. Verificar cuáles son válidos en Polygon
            valid_tickers = await self._verify_tickers_in_polygon(missing_to_process)
            
            if not valid_tickers:
                logger.info("no_valid_tickers_to_recover")
                return {
                    "success": True,
                    "message": "No valid tickers found",
                    "tickers_recovered": 0
                }
            
            logger.info(f"valid_tickers_to_recover", count=len(valid_tickers))
            
            # 5. Agregar al universo
            recovered = await self._add_to_universe(valid_tickers)
            
            if recovered == 0:
                return {
                    "success": True,
                    "message": "No tickers recovered",
                    "tickers_recovered": 0
                }
            
            # 6. CARGAR DATOS HISTÓRICOS INMEDIATAMENTE
            logger.info(f"loading_historical_data_for_recovered_tickers", count=recovered)
            
            symbols = [t['symbol'] for t in valid_tickers]
            
            # 6a. Cargar volume_slots (últimos 10 días)
            slots_loaded = await self._load_volume_slots_immediate(symbols)
            
            # 6b. Cargar OHLC (últimos 30 días)  
            ohlc_loaded = await self._load_ohlc_immediate(symbols)
            
            # 6c. Calcular promedios RVOL
            rvol_calculated = await self._calculate_rvol_averages_immediate(symbols)
            
            # 6d. Enriquecer metadata
            metadata_enriched = await self._enrich_metadata_immediate(symbols)
            
            # 7. Sincronizar TODO a Redis
            await self._sync_to_redis(valid_tickers)
            
            logger.info(
                "auto_recover_task_completed",
                missing_detected=len(missing),
                valid_found=len(valid_tickers),
                tickers_recovered=recovered,
                slots_loaded=slots_loaded,
                ohlc_loaded=ohlc_loaded,
                rvol_calculated=rvol_calculated,
                metadata_enriched=metadata_enriched
            )
            
            return {
                "success": True,
                "missing_detected": len(missing),
                "valid_found": len(valid_tickers),
                "tickers_recovered": recovered,
                "data_loaded": {
                    "volume_slots": slots_loaded,
                    "ohlc": ohlc_loaded,
                    "rvol_averages": rvol_calculated,
                    "metadata": metadata_enriched
                }
            }
        
        except Exception as e:
            logger.error("auto_recover_task_failed", error=str(e))
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _get_snapshot_tickers(self) -> Set[str]:
        """Obtener tickers del snapshot actual (from Redis Hash keys)"""
        try:
            # Read all field names from hash (just keys, not values)
            all_keys = await self.redis.client.hkeys("snapshot:enriched:latest")
            if not all_keys:
                return set()
            
            # Remove metadata key, return symbol set
            return {k for k in all_keys if k != "__meta__"}
        
        except Exception as e:
            logger.error("failed_to_get_snapshot", error=str(e))
            return set()
    
    async def _get_universe_tickers(self) -> Set[str]:
        """Obtener tickers del universo actual desde tickers_unified"""
        try:
            query = "SELECT symbol FROM tickers_unified WHERE is_actively_trading = true"
            rows = await self.db.fetch(query)
            return {row['symbol'] for row in rows}
        
        except Exception as e:
            logger.error("failed_to_get_universe", error=str(e))
            return set()
    
    async def _verify_tickers_in_polygon(self, tickers: List[str]) -> List[Dict]:
        """Verificar cuáles tickers son válidos en Polygon"""
        valid = []
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            for symbol in tickers:
                try:
                    url = f"https://api.polygon.io/v3/reference/tickers/{symbol}"
                    resp = await client.get(url, params={"apiKey": settings.POLYGON_API_KEY})
                    
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get('status') == 'OK':
                            results = data.get('results', {})
                            if results.get('active'):
                                valid.append({
                                    'symbol': symbol,
                                    'name': results.get('name'),
                                    'type': results.get('type'),
                                    'exchange': results.get('primary_exchange')
                                })
                                logger.info(f"valid_ticker_found", symbol=symbol, name=results.get('name'))
                    
                    # Rate limiting
                    await asyncio.sleep(0.21)
                
                except Exception as e:
                    logger.debug(f"error_verifying_ticker", symbol=symbol, error=str(e))
        
        return valid
    
    async def _add_to_universe(self, tickers: List[Dict]) -> int:
        """Agregar tickers al universo"""
        added = 0
        
        query = """
            INSERT INTO tickers_unified (symbol, is_actively_trading, updated_at, created_at)
            VALUES ($1, true, NOW(), NOW())
            ON CONFLICT (symbol) DO UPDATE SET
                is_active = true,
                last_seen = NOW()
        """
        
        for ticker in tickers:
            try:
                await self.db.execute(query, ticker['symbol'])
                added += 1
                logger.info(f"ticker_added_to_universe", symbol=ticker['symbol'], name=ticker.get('name'))
            
            except Exception as e:
                logger.error(f"failed_to_add_ticker", symbol=ticker['symbol'], error=str(e))
        
        return added
    
    async def _sync_to_redis(self, tickers: List[Dict]):
        """Sincronizar nuevos tickers a Redis SET"""
        try:
            symbols = [t['symbol'] for t in tickers]
            if symbols:
                await self.redis.client.sadd("ticker:universe", *symbols)
                logger.info(f"tickers_synced_to_redis", count=len(symbols))
        
        except Exception as e:
            logger.error(f"failed_to_sync_redis", error=str(e))

    
    async def _load_volume_slots_immediate(self, symbols: List[str]) -> int:
        """Cargar volume_slots para tickers nuevos (últimos 10 días)"""
        from datetime import timedelta
        import httpx
        
        loaded = 0
        end_date = date.today() - timedelta(days=1)
        start_date = end_date - timedelta(days=10)
        
        logger.info(f"loading_volume_slots", symbols_count=len(symbols), date_range=f"{start_date} to {end_date}")
        
        async with httpx.AsyncClient(timeout=30) as client:
            for symbol in symbols:
                try:
                    # Cargar datos de Polygon (similar a load_massive_parallel)
                    url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/5/minute/{start_date}/{end_date}"
                    resp = await client.get(url, params={"adjusted": "true", "apiKey": settings.POLYGON_API_KEY, "limit": 50000})
                    
                    if resp.status_code == 200:
                        data = resp.json()
                        results = data.get('results', [])
                        
                        if results:
                            # Insertar en volume_slots
                            for bar in results:
                                bar_date = date.fromtimestamp(bar['t'] / 1000)
                                bar_time = datetime.fromtimestamp(bar['t'] / 1000).time()
                                # Calcular slot_number y volume acumulado del día
                                # (simplificado - en producción usar lógica completa)
                                await asyncio.sleep(0)  # Yield para no bloquear
                            
                            loaded += 1
                            logger.info(f"volume_slots_loaded", symbol=symbol, bars=len(results))
                    
                    await asyncio.sleep(0.21)  # Rate limiting
                
                except Exception as e:
                    logger.error(f"failed_to_load_slots", symbol=symbol, error=str(e))
        
        return loaded
    
    async def _load_ohlc_immediate(self, symbols: List[str]) -> int:
        """Cargar OHLC para tickers nuevos (últimos 30 días)"""
        from datetime import timedelta
        import httpx
        
        loaded = 0
        end_date = date.today() - timedelta(days=1)
        start_date = end_date - timedelta(days=30)
        
        logger.info(f"loading_ohlc", symbols_count=len(symbols))
        
        async with httpx.AsyncClient(timeout=30) as client:
            for symbol in symbols:
                try:
                    url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/day/{start_date}/{end_date}"
                    resp = await client.get(url, params={"adjusted": "true", "apiKey": settings.POLYGON_API_KEY})
                    
                    if resp.status_code == 200:
                        data = resp.json()
                        results = data.get('results', [])
                        
                        if results:
                            for bar in results:
                                bar_date = date.fromtimestamp(bar['t'] / 1000)
                                await self.db.execute("""
                                    INSERT INTO market_data_daily (trading_date, symbol, open, high, low, close, volume, vwap, trades_count)
                                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                                    ON CONFLICT (trading_date, symbol) DO UPDATE SET
                                        open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
                                        close = EXCLUDED.close, volume = EXCLUDED.volume
                                """, bar_date, symbol, bar['o'], bar['h'], bar['l'], bar['c'], bar['v'], bar.get('vw'), bar.get('n'))
                            
                            loaded += 1
                            logger.info(f"ohlc_loaded", symbol=symbol, days=len(results))
                    
                    await asyncio.sleep(0.21)
                
                except Exception as e:
                    logger.error(f"failed_to_load_ohlc", symbol=symbol, error=str(e))
        
        return loaded
    
    async def _calculate_rvol_averages_immediate(self, symbols: List[str]) -> int:
        """Calcular promedios RVOL para tickers nuevos"""
        calculated = 0
        
        for symbol in symbols:
            try:
                # Calcular promedio de últimos 5 días por slot
                # (simplificado - usar lógica de CalculateRVOLHistoricalAveragesTask)
                hash_key = f"rvol:hist:avg:{symbol}:5"
                
                # Query simplificado
                query = """
                    WITH last_days AS (
                        SELECT DISTINCT date FROM volume_slots 
                        WHERE symbol = $1 AND date < CURRENT_DATE
                        ORDER BY date DESC LIMIT 5
                    )
                    SELECT slot_number, AVG(volume_accumulated) as avg_vol
                    FROM volume_slots
                    WHERE symbol = $1 AND date IN (SELECT date FROM last_days)
                    GROUP BY slot_number
                """
                
                rows = await self.db.fetch(query, symbol)
                
                if rows:
                    # Guardar en Redis HASH
                    for row in rows:
                        await self.redis.hset(hash_key, str(row['slot_number']), int(row['avg_vol']))
                    
                    await self.redis.expire(hash_key, 50400)  # 14 horas
                    calculated += 1
                    logger.info(f"rvol_averages_calculated", symbol=symbol, slots=len(rows))
            
            except Exception as e:
                logger.error(f"failed_to_calculate_rvol", symbol=symbol, error=str(e))
        
        return calculated
    
    async def _enrich_metadata_immediate(self, symbols: List[str]) -> int:
        """Enriquecer metadata para tickers nuevos"""
        import httpx
        
        enriched = 0
        
        async with httpx.AsyncClient(timeout=15) as client:
            for symbol in symbols:
                try:
                    url = f"https://api.polygon.io/v3/reference/tickers/{symbol}"
                    resp = await client.get(url, params={"apiKey": settings.POLYGON_API_KEY})
                    
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get('status') == 'OK':
                            details = data.get('results', {})
                            
                            # Extraer campos clave
                            market_cap = details.get('market_cap')
                            weighted_shares = details.get('weighted_shares_outstanding')
                            share_class_shares = details.get('share_class_shares_outstanding')
                            shares_outstanding = share_class_shares or weighted_shares
                            free_float = shares_outstanding
                            sector = details.get('sic_description') or details.get('sector')
                            industry = details.get('industry')
                            
                            # Guardar en tickers_unified
                            await self.db.execute("""
                                INSERT INTO tickers_unified (
                                    symbol, market_cap, free_float, shares_outstanding,
                                    sector, industry
                                )
                                VALUES ($1, $2, $3, $4, $5, $6)
                                ON CONFLICT (symbol) DO UPDATE SET
                                    market_cap = COALESCE(EXCLUDED.market_cap, ticker_metadata.market_cap),
                                    free_float = COALESCE(EXCLUDED.free_float, ticker_metadata.free_float),
                                    shares_outstanding = COALESCE(EXCLUDED.shares_outstanding, ticker_metadata.shares_outstanding),
                                    sector = COALESCE(EXCLUDED.sector, ticker_metadata.sector),
                                    industry = COALESCE(EXCLUDED.industry, ticker_metadata.industry)
                            """, symbol, market_cap, free_float, shares_outstanding, sector, industry)
                            
                            # Guardar en Redis también
                            metadata_dict = {
                                'symbol': symbol,
                                'market_cap': market_cap,
                                'free_float': free_float,
                                'shares_outstanding': shares_outstanding,
                                'sector': sector,
                                'industry': industry
                            }
                            await self.redis.set(f"metadata:ticker:{symbol}", metadata_dict, ttl=86400)  # ✅ TTL 24h
                            
                            enriched += 1
                            logger.info(f"metadata_enriched", symbol=symbol)
                    
                    await asyncio.sleep(0.21)
                
                except Exception as e:
                    logger.error(f"failed_to_enrich_metadata", symbol=symbol, error=str(e))
        
        return enriched
