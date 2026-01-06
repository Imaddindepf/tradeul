"""
Refresh All Metadata Task
=========================

Actualiza TODOS los campos de metadata de Polygon para todos los tickers activos.

Se ejecuta a las 1:00 AM ET (2 horas antes del mantenimiento principal).

Campos actualizados:
- DINÁMICOS: shares_outstanding, market_cap, free_float, free_float_percent, beta
- ESTÁTICOS: company_name, sector, industry, description, cik, exchange, etc.

Flujo:
1. Obtener todos los tickers activos de la BD
2. Consultar Polygon API con alta concurrencia (100+)
3. Actualizar BD (tickers_unified)
4. Sincronizar Redis (limpiar caches de metadata)
5. Publicar evento de actualización

Fuentes:
- Polygon /v3/reference/tickers/{symbol} - Datos principales
- Polygon /vX/reference/tickers/{symbol}/float - Free float (si disponible)
- FMP fallback para free_float si Polygon no lo tiene
"""

import asyncio
import os
import sys
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple
import httpx

sys.path.append('/app')

from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import get_logger

POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "vjzI76TMiepqrMZKphpfs3SA54JFkhEx")

logger = get_logger(__name__)


class RefreshAllMetadataTask:
    """
    Tarea: Actualizar TODA la metadata de tickers desde Polygon
    
    Se ejecuta diariamente a la 1:00 AM ET para asegurar datos frescos
    antes del mantenimiento principal (3:00 AM ET).
    """
    
    name = "refresh_all_metadata"
    
    def __init__(self, redis_client: RedisClient, timescale_client: TimescaleClient):
        self.redis = redis_client
        self.db = timescale_client
        self.concurrency = 100  # Alta concurrencia para plan avanzado de Polygon
        self.semaphore = asyncio.Semaphore(self.concurrency)
        
    async def execute(self, target_date: date) -> Dict:
        """
        Ejecutar actualización completa de metadata
        
        Args:
            target_date: Fecha objetivo (para logging)
        
        Returns:
            Dict con resultado de la actualización
        """
        logger.info(
            "refresh_all_metadata_starting",
            target_date=str(target_date),
            concurrency=self.concurrency
        )
        
        start_time = datetime.now()
        
        stats = {
            "success": True,
            "total_tickers": 0,
            "updated": 0,
            "unchanged": 0,
            "not_found": 0,
            "errors": 0,
            "duration_seconds": 0
        }
        
        try:
            # 1. Obtener todos los tickers activos
            symbols = await self._get_active_symbols()
            stats["total_tickers"] = len(symbols)
            
            if not symbols:
                logger.warning("no_active_symbols_found")
                return stats
            
            logger.info(
                "fetching_metadata_from_polygon",
                total_tickers=len(symbols)
            )
            
            # 2. Fetch de Polygon en paralelo
            updates: List[Dict] = []
            
            async with httpx.AsyncClient(timeout=15.0) as client:
                tasks = [self._fetch_ticker_metadata(client, symbol) for symbol in symbols]
                results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 3. Procesar resultados
            for symbol, result in zip(symbols, results):
                if isinstance(result, Exception):
                    stats["errors"] += 1
                    logger.debug("fetch_error", symbol=symbol, error=str(result))
                elif result is None:
                    stats["not_found"] += 1
                elif result.get("has_data"):
                    stats["updated"] += 1
                    updates.append(result)
                else:
                    stats["unchanged"] += 1
            
            logger.info(
                "polygon_fetch_completed",
                updated=stats["updated"],
                not_found=stats["not_found"],
                errors=stats["errors"]
            )
            
            # 4. Actualizar BD en batches
            if updates:
                await self._update_database(updates)
                logger.info("database_updated", count=len(updates))
            
            # 5. Sincronizar Redis
            await self._sync_redis()
            logger.info("redis_synced")
            
            # 6. Publicar evento
            await self._publish_event(target_date, stats)
            
            stats["duration_seconds"] = round((datetime.now() - start_time).total_seconds(), 2)
            
            logger.info(
                "refresh_all_metadata_completed",
                **stats
            )
            
            return stats
            
        except Exception as e:
            logger.error(
                "refresh_all_metadata_failed",
                error=str(e),
                error_type=type(e).__name__
            )
            stats["success"] = False
            stats["error"] = str(e)
            return stats
    
    async def _get_active_symbols(self) -> List[str]:
        """Obtener todos los símbolos activos de la BD"""
        try:
            query = """
                SELECT symbol
                FROM tickers_unified
                WHERE is_actively_trading = true
                ORDER BY symbol
            """
            rows = await self.db.fetch(query)
            return [row['symbol'] for row in rows]
        except Exception as e:
            logger.error("failed_to_get_active_symbols", error=str(e))
            return []
    
    async def _fetch_ticker_metadata(self, client: httpx.AsyncClient, symbol: str) -> Optional[Dict]:
        """
        Fetch metadata de un ticker desde Polygon
        
        Endpoints:
        - /v3/reference/tickers/{symbol} → shares_outstanding, market_cap
        - /stocks/vX/float?ticker={symbol} → free_float, free_float_percent
        
        Returns:
            Dict con todos los campos o None si no se encontró
        """
        async with self.semaphore:
            try:
                # 1. Polygon Ticker Details (shares_outstanding, market_cap)
                url = f"https://api.polygon.io/v3/reference/tickers/{symbol}"
                resp = await client.get(url, params={"apiKey": POLYGON_API_KEY})
                
                if resp.status_code == 404:
                    return None
                
                if resp.status_code == 429:
                    await asyncio.sleep(1)
                    resp = await client.get(url, params={"apiKey": POLYGON_API_KEY})
                
                if resp.status_code != 200:
                    return None
                
                data = resp.json().get("results", {})
                
                if not data:
                    return None
                
                # 2. Polygon Free Float (endpoint correcto: /stocks/vX/float)
                free_float = None
                free_float_percent = None
                
                try:
                    float_url = f"https://api.polygon.io/stocks/vX/float"
                    float_resp = await client.get(float_url, params={"ticker": symbol, "apiKey": POLYGON_API_KEY})
                    
                    if float_resp.status_code == 200:
                        float_data = float_resp.json()
                        results = float_data.get("results", [])
                        if results and len(results) > 0:
                            # Polygon devuelve array, tomamos el primero
                            float_info = results[0]
                            free_float = float_info.get("free_float")
                            free_float_percent = float_info.get("free_float_percent")
                except Exception:
                    pass  # Si falla, continuamos sin free_float
                
                # 3. Extraer campos directamente de Polygon (sin validaciones, Polygon ya cura datos)
                shares_outstanding = (
                    data.get("share_class_shares_outstanding") or 
                    data.get("weighted_shares_outstanding")
                )
                
                return {
                    "symbol": symbol,
                    "has_data": True,
                    # Campos dinámicos de Polygon (tal cual vienen)
                    "shares_outstanding": int(shares_outstanding) if shares_outstanding else None,
                    "market_cap": int(data.get("market_cap")) if data.get("market_cap") else None,
                    "free_float": int(free_float) if free_float else None,
                    "free_float_percent": float(free_float_percent) if free_float_percent else None,
                    # Campos estáticos
                    "company_name": data.get("name"),
                    "cik": data.get("cik"),
                    "exchange": data.get("primary_exchange"),
                    "sector": data.get("sic_description"),
                    "industry": data.get("sic_description"),
                    "description": data.get("description"),
                    "homepage_url": data.get("homepage_url"),
                    "phone_number": data.get("phone_number"),
                    "address": data.get("address"),
                    "total_employees": data.get("total_employees"),
                    "list_date": data.get("list_date"),
                    "logo_url": data.get("branding", {}).get("logo_url") if data.get("branding") else None,
                    "icon_url": data.get("branding", {}).get("icon_url") if data.get("branding") else None,
                    "composite_figi": data.get("composite_figi"),
                    "share_class_figi": data.get("share_class_figi"),
                    "ticker_root": data.get("ticker_root"),
                    "type": data.get("type"),
                    "currency_name": data.get("currency_name"),
                    "locale": data.get("locale"),
                    "market": data.get("market"),
                    "round_lot": data.get("round_lot"),
                }
                
            except Exception as e:
                logger.debug("fetch_ticker_error", symbol=symbol, error=str(e))
                return None
    
    async def _update_database(self, updates: List[Dict]):
        """Actualizar BD con los nuevos datos de Polygon (sin validaciones, Polygon cura datos)"""
        query = """
            UPDATE tickers_unified SET
                -- Campos dinámicos de Polygon (actualizar si hay nuevo valor)
                shares_outstanding = COALESCE($2::bigint, shares_outstanding),
                market_cap = COALESCE($3::bigint, market_cap),
                free_float = COALESCE($4::bigint, free_float),
                free_float_percent = COALESCE($5::numeric, free_float_percent),
                -- Campos estáticos (COALESCE para no sobrescribir con NULL)
                company_name = COALESCE($6, company_name),
                cik = COALESCE($7, cik),
                exchange = COALESCE($8, exchange),
                sector = COALESCE($9, sector),
                industry = COALESCE($10, industry),
                description = COALESCE($11, description),
                homepage_url = COALESCE($12, homepage_url),
                phone_number = COALESCE($13, phone_number),
                address = COALESCE($14::jsonb, address),
                total_employees = COALESCE($15, total_employees),
                list_date = COALESCE($16::date, list_date),
                logo_url = COALESCE($17, logo_url),
                icon_url = COALESCE($18, icon_url),
                composite_figi = COALESCE($19, composite_figi),
                share_class_figi = COALESCE($20, share_class_figi),
                ticker_root = COALESCE($21, ticker_root),
                type = COALESCE($22, type),
                currency_name = COALESCE($23, currency_name),
                locale = COALESCE($24, locale),
                market = COALESCE($25, market),
                round_lot = COALESCE($26, round_lot),
                -- Timestamp
                updated_at = NOW()
            WHERE symbol = $1
        """
        
        batch_size = 500
        total = len(updates)
        
        for i in range(0, total, batch_size):
            batch = updates[i:i + batch_size]
            
            for update in batch:
                try:
                    import json
                    address_json = json.dumps(update.get("address")) if update.get("address") else None
                    
                    await self.db.execute(
                        query,
                        update["symbol"],
                        update.get("shares_outstanding"),
                        update.get("market_cap"),
                        update.get("free_float"),
                        update.get("free_float_percent"),
                        update.get("company_name"),
                        update.get("cik"),
                        update.get("exchange"),
                        update.get("sector"),
                        update.get("industry"),
                        update.get("description"),
                        update.get("homepage_url"),
                        update.get("phone_number"),
                        address_json,
                        update.get("total_employees"),
                        update.get("list_date"),
                        update.get("logo_url"),
                        update.get("icon_url"),
                        update.get("composite_figi"),
                        update.get("share_class_figi"),
                        update.get("ticker_root"),
                        update.get("type"),
                        update.get("currency_name"),
                        update.get("locale"),
                        update.get("market"),
                        update.get("round_lot"),
                    )
                except Exception as e:
                    logger.debug("update_ticker_error", symbol=update["symbol"], error=str(e))
            
            if (i + batch_size) % 2000 == 0 or (i + batch_size) >= total:
                logger.info("database_update_progress", processed=min(i + batch_size, total), total=total)
    
    async def _sync_redis(self):
        """Sincronizar Redis - limpiar caches de metadata"""
        try:
            patterns = [
                "ticker:metadata:*",
                "screener:metadata:*",
                "ticker:details:*",
            ]
            
            for pattern in patterns:
                try:
                    deleted = await self.redis.delete_pattern(pattern)
                    if deleted > 0:
                        logger.debug("redis_keys_deleted", pattern=pattern, count=deleted)
                except Exception as e:
                    logger.warning("redis_delete_pattern_error", pattern=pattern, error=str(e))
            
        except Exception as e:
            logger.error("redis_sync_failed", error=str(e))
    
    async def _publish_event(self, target_date: date, stats: Dict):
        """Publicar evento de metadata actualizada"""
        try:
            import json
            await self.redis.client.publish(
                "maintenance:metadata_refreshed",
                json.dumps({
                    "event": "all_metadata_refreshed",
                    "date": target_date.isoformat(),
                    "timestamp": datetime.now().isoformat(),
                    "updated": stats.get("updated", 0),
                    "total": stats.get("total_tickers", 0)
                })
            )
        except Exception as e:
            logger.warning("publish_event_failed", error=str(e))

