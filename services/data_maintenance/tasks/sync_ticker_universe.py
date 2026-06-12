"""
Sync Ticker Universe Task
Sincroniza el universo de tickers con Polygon.io

Semántica de flags (auditoría 2026-06-12):
- is_actively_trading: el símbolo está activo en market=stocks (universo operable).
- is_active:           el símbolo existe/cotiza en algún mercado (stocks U otc).
- delisted_utc:        se fija al detectar que desaparece de todos los mercados.

Ejecuta las siguientes acciones:
1. Obtiene todos los tickers activos de Polygon (stocks y otc)
2. Agrega tickers nuevos de stocks a la BD (reactiva símbolos reusados)
3. Desactiva tickers que ya no están en Polygon (delistados), con delisted_utc
4. Mantiene is_active coherente para tickers OTC ya presentes en la BD
5. Actualiza company_name y exchange si faltan

Se ejecuta en el mantenimiento nocturno (idealmente después de enrich_metadata).
"""

import asyncio
import os
import sys
sys.path.append('/app')

from datetime import date, datetime
from typing import Dict, List, Set, Optional
import httpx

from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import get_logger

POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "vjzI76TMiepqrMZKphpfs3SA54JFkhEx")

logger = get_logger(__name__)


class SyncTickerUniverseTask:
    """
    Tarea: Sincronizar universo de tickers con Polygon
    
    Acciones:
    1. Obtener TODOS los tickers activos de Polygon (paginando)
    2. Comparar con BD
    3. Agregar nuevos tickers
    4. Desactivar tickers delistados
    5. Actualizar nombres faltantes
    """
    
    name = "sync_ticker_universe"
    
    def __init__(self, redis_client: RedisClient, timescale_client: TimescaleClient):
        self.redis = redis_client
        self.db = timescale_client
    
    async def execute(self, target_date: date) -> Dict:
        """
        Ejecutar sincronización del universo de tickers
        
        Args:
            target_date: Fecha objetivo (para logging)
        
        Returns:
            Dict con resultado de la sincronización
        """
        logger.info("sync_ticker_universe_starting", target_date=str(target_date))
        
        stats = {
            "success": True,
            "polygon_total": 0,
            "polygon_otc_total": 0,
            "db_total": 0,
            "new_tickers_added": 0,
            "tickers_deactivated": 0,
            "tickers_delisted": 0,
            "otc_reactivated": 0,
            "names_updated": 0,
            "errors": []
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # 1. Obtener todos los tickers activos de Polygon (stocks + otc)
                logger.info("fetching_polygon_universe")
                polygon_tickers = await self._fetch_all_polygon_tickers(client, market="stocks")
                stats["polygon_total"] = len(polygon_tickers)
                
                if not polygon_tickers:
                    logger.error("no_tickers_from_polygon")
                    stats["success"] = False
                    stats["errors"].append("No se pudieron obtener tickers de Polygon")
                    return stats
                
                otc_tickers = await self._fetch_all_polygon_tickers(client, market="otc")
                stats["polygon_otc_total"] = len(otc_tickers)
                otc_symbols = {t['ticker'] for t in otc_tickers}
                
                # Crear set de símbolos y dict con datos
                polygon_symbols = {t['ticker'] for t in polygon_tickers}
                polygon_data = {t['ticker']: t for t in polygon_tickers}
                
                # 2. Obtener tickers actuales de BD
                db_symbols = await self._get_db_active_symbols()
                db_all_symbols = await self._get_db_all_symbols()
                stats["db_total"] = len(db_symbols)
                
                logger.info(
                    "universe_comparison",
                    polygon_count=len(polygon_symbols),
                    polygon_otc_count=len(otc_symbols),
                    db_count=len(db_symbols)
                )
                
                # 3. Calcular diferencias
                new_symbols = polygon_symbols - db_symbols  # En Polygon pero no en BD
                deactivate_symbols = db_symbols - polygon_symbols  # En BD pero no en Polygon
                common_symbols = polygon_symbols & db_symbols  # En ambos
                
                logger.info(
                    "sync_differences",
                    new_count=len(new_symbols),
                    deactivate_count=len(deactivate_symbols),
                    common_count=len(common_symbols)
                )
                
                # 4. Agregar tickers nuevos
                if new_symbols:
                    added = await self._add_new_tickers(
                        [polygon_data[s] for s in new_symbols]
                    )
                    stats["new_tickers_added"] = added
                
                # 5. Desactivar tickers delistados.
                #    Si tampoco están en OTC, marcar muerte real (is_active + delisted_utc)
                if deactivate_symbols:
                    deactivated = await self._deactivate_tickers(list(deactivate_symbols))
                    stats["tickers_deactivated"] = deactivated
                
                # 5b. Muerte real: cualquier símbolo de la BD con is_active=true que ya
                #     no exista en NINGÚN mercado (cubre también filas históricas)
                fully_delisted = db_all_symbols - polygon_symbols - otc_symbols
                if fully_delisted:
                    delisted = await self._mark_fully_delisted(list(fully_delisted))
                    stats["tickers_delisted"] = delisted
                
                # 5c. Coherencia OTC: símbolos de la BD activos en Polygon-OTC deben
                #     tener is_active=true (sin tocar is_actively_trading: OTC no
                #     forma parte del universo operable)
                otc_in_db = otc_symbols & db_all_symbols
                if otc_in_db:
                    reactivated = await self._ensure_otc_active(list(otc_in_db))
                    stats["otc_reactivated"] = reactivated
                
                # 6. Actualizar nombres faltantes en tickers existentes
                names_missing = await self._get_symbols_without_name()
                if names_missing:
                    updated = await self._update_names_from_polygon(
                        names_missing,
                        polygon_data
                    )
                    stats["names_updated"] = updated
                
                logger.info(
                    "sync_ticker_universe_completed",
                    **stats
                )
                
                return stats
        
        except Exception as e:
            logger.error(
                "sync_ticker_universe_failed",
                error=str(e),
                error_type=type(e).__name__
            )
            stats["success"] = False
            stats["errors"].append(str(e))
            return stats
    
    async def _fetch_all_polygon_tickers(
        self, client: httpx.AsyncClient, market: str = "stocks"
    ) -> List[Dict]:
        """
        Obtener TODOS los tickers activos de Polygon (paginando)
        
        Filtra por:
        - market=stocks u otc
        - locale=us
        - active=true
        """
        all_tickers = []
        next_url = None
        page = 1
        max_pages = 30  # stocks ~13 páginas, otc ~19
        
        while page <= max_pages:
            try:
                if next_url:
                    url = next_url
                else:
                    url = (
                        f"https://api.polygon.io/v3/reference/tickers"
                        f"?market={market}&locale=us&active=true&limit=1000"
                        f"&apiKey={POLYGON_API_KEY}"
                    )
                
                resp = await client.get(url)
                
                if resp.status_code != 200:
                    logger.warning(
                        "polygon_request_failed",
                        status=resp.status_code,
                        page=page
                    )
                    break
                
                data = resp.json()
                results = data.get('results', [])
                
                if not results:
                    break
                
                all_tickers.extend(results)
                
                logger.debug(
                    "polygon_page_fetched",
                    page=page,
                    count=len(results),
                    total=len(all_tickers)
                )
                
                # Siguiente página
                next_url = data.get('next_url')
                if not next_url:
                    break
                
                # Agregar apiKey si no está
                if 'apiKey' not in next_url:
                    next_url = f"{next_url}&apiKey={POLYGON_API_KEY}"
                
                page += 1
                await asyncio.sleep(0.25)  # Rate limiting
                
            except Exception as e:
                logger.error(
                    "polygon_fetch_error",
                    page=page,
                    error=str(e)
                )
                break
        
        logger.info(
            "polygon_fetch_completed",
            market=market,
            total_tickers=len(all_tickers),
            pages=page
        )
        
        return all_tickers
    
    async def _get_db_active_symbols(self) -> Set[str]:
        """Obtener símbolos activos de la BD"""
        try:
            query = """
                SELECT symbol 
                FROM tickers_unified 
                WHERE is_actively_trading = true
            """
            rows = await self.db.fetch(query)
            return {row['symbol'] for row in rows}
        except Exception as e:
            logger.error("failed_to_get_db_symbols", error=str(e))
            return set()
    
    async def _get_db_all_symbols(self) -> Set[str]:
        """Símbolos con is_active=true (existen en algún mercado según la BD)"""
        try:
            rows = await self.db.fetch(
                """
                SELECT symbol FROM tickers_unified
                WHERE is_active = true
                  -- Índices sintéticos propios (TRDL:TICK...) no existen en
                  -- Polygon: excluirlos para que no se marquen como delistados
                  AND COALESCE(exchange, '') != 'TRDL INDEX'
                """
            )
            return {row['symbol'] for row in rows}
        except Exception as e:
            logger.error("failed_to_get_db_all_symbols", error=str(e))
            return set()
    
    async def _get_symbols_without_name(self) -> List[str]:
        """Obtener símbolos activos sin company_name"""
        try:
            query = """
                SELECT symbol 
                FROM tickers_unified 
                WHERE is_actively_trading = true
                  AND (company_name IS NULL OR company_name = '')
            """
            rows = await self.db.fetch(query)
            return [row['symbol'] for row in rows]
        except Exception as e:
            logger.error("failed_to_get_symbols_without_name", error=str(e))
            return []
    
    async def _add_new_tickers(self, tickers: List[Dict]) -> int:
        """
        Agregar nuevos tickers a la BD
        
        Args:
            tickers: Lista de dicts con datos de Polygon
        
        Returns:
            Cantidad de tickers agregados
        """
        added = 0
        
        query = """
            INSERT INTO tickers_unified (
                symbol, company_name, exchange, type, market, locale,
                cik, composite_figi, share_class_figi,
                is_actively_trading, is_active, created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, true, true, NOW(), NOW())
            ON CONFLICT (symbol) DO UPDATE SET
                company_name = COALESCE(EXCLUDED.company_name, tickers_unified.company_name),
                exchange = COALESCE(EXCLUDED.exchange, tickers_unified.exchange),
                type = COALESCE(EXCLUDED.type, tickers_unified.type),
                market = COALESCE(EXCLUDED.market, tickers_unified.market),
                is_actively_trading = true,
                is_active = true,
                delisted_utc = NULL,
                updated_at = NOW()
        """
        
        for ticker in tickers:
            try:
                await self.db.execute(
                    query,
                    ticker.get('ticker'),
                    ticker.get('name'),
                    ticker.get('primary_exchange'),
                    ticker.get('type'),
                    ticker.get('market', 'stocks'),
                    ticker.get('locale', 'us'),
                    ticker.get('cik'),
                    ticker.get('composite_figi'),
                    ticker.get('share_class_figi')
                )
                added += 1
            except Exception as e:
                logger.debug(f"Failed to add ticker {ticker.get('ticker')}: {e}")
        
        logger.info("new_tickers_added", count=added)
        return added
    
    async def _deactivate_tickers(self, symbols: List[str]) -> int:
        """
        Desactivar tickers que ya no están en Polygon
        
        Args:
            symbols: Lista de símbolos a desactivar
        
        Returns:
            Cantidad de tickers desactivados
        """
        if not symbols:
            return 0
        
        # Dividir en batches de 500 para evitar queries muy grandes
        batch_size = 500
        deactivated = 0
        
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i + batch_size]
            
            try:
                # Crear placeholders para el IN clause
                placeholders = ', '.join(f'${j+1}' for j in range(len(batch)))
                
                query = f"""
                    UPDATE tickers_unified 
                    SET is_actively_trading = false, updated_at = NOW()
                    WHERE symbol IN ({placeholders})
                """
                
                await self.db.execute(query, *batch)
                deactivated += len(batch)
                
            except Exception as e:
                logger.error(
                    "failed_to_deactivate_batch",
                    batch_start=i,
                    error=str(e)
                )
        
        logger.info("tickers_deactivated", count=deactivated)
        return deactivated
    
    @staticmethod
    def _parse_update_count(status: Optional[str]) -> int:
        """asyncpg devuelve 'UPDATE n'; extraer n (0 si no parseable)"""
        try:
            return int(str(status).split()[-1])
        except (ValueError, IndexError):
            return 0
    
    async def _mark_fully_delisted(self, symbols: List[str]) -> int:
        """
        Marcar muerte real: el símbolo no existe en NINGÚN mercado de Polygon.
        Fija is_active=false y delisted_utc (si no estaba ya fijada).
        """
        batch_size = 500
        total = 0
        
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i + batch_size]
            placeholders = ', '.join(f'${j+1}' for j in range(len(batch)))
            try:
                status = await self.db.execute(
                    f"""
                    UPDATE tickers_unified
                    SET is_active = false,
                        is_actively_trading = false,
                        delisted_utc = COALESCE(delisted_utc, NOW()),
                        updated_at = NOW()
                    WHERE symbol IN ({placeholders})
                      AND is_active = true
                    """,
                    *batch
                )
                total += self._parse_update_count(status)
            except Exception as e:
                logger.error("failed_to_mark_delisted_batch", batch_start=i, error=str(e))
        
        if total:
            logger.info("tickers_fully_delisted", count=total)
        return total
    
    async def _ensure_otc_active(self, symbols: List[str]) -> int:
        """
        Coherencia OTC: símbolos presentes en la BD que Polygon lista como
        activos en market=otc deben tener is_active=true. No se tocan
        is_actively_trading (OTC queda fuera del universo operable).
        """
        batch_size = 500
        total = 0
        
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i + batch_size]
            placeholders = ', '.join(f'${j+1}' for j in range(len(batch)))
            try:
                status = await self.db.execute(
                    f"""
                    UPDATE tickers_unified
                    SET is_active = true,
                        market = 'otc',
                        delisted_utc = NULL,
                        updated_at = NOW()
                    WHERE symbol IN ({placeholders})
                      AND (is_active IS DISTINCT FROM true OR market IS DISTINCT FROM 'otc')
                    """,
                    *batch
                )
                total += self._parse_update_count(status)
            except Exception as e:
                logger.error("failed_to_ensure_otc_batch", batch_start=i, error=str(e))
        
        if total:
            logger.info("otc_tickers_reactivated", count=total)
        return total
    
    async def _update_names_from_polygon(
        self,
        symbols: List[str],
        polygon_data: Dict[str, Dict]
    ) -> int:
        """
        Actualizar nombres faltantes desde datos de Polygon
        
        Args:
            symbols: Lista de símbolos sin nombre
            polygon_data: Dict con datos de Polygon indexado por símbolo
        
        Returns:
            Cantidad de nombres actualizados
        """
        updated = 0
        
        query = """
            UPDATE tickers_unified 
            SET 
                company_name = $2,
                exchange = COALESCE($3, exchange),
                updated_at = NOW()
            WHERE symbol = $1
        """
        
        for symbol in symbols:
            if symbol in polygon_data:
                ticker = polygon_data[symbol]
                name = ticker.get('name')
                exchange = ticker.get('primary_exchange')
                
                if name:
                    try:
                        await self.db.execute(query, symbol, name, exchange)
                        updated += 1
                    except Exception as e:
                        logger.debug(f"Failed to update name for {symbol}: {e}")
        
        logger.info("names_updated", count=updated)
        return updated

