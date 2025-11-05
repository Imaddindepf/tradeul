"""
Cargador de Universo de Tickers desde Polygon
Obtiene todos los tickers activos de US stocks y los sincroniza con Redis y TimescaleDB
"""

import asyncio
import sys
from datetime import datetime, date
from typing import List, Dict, Any, Optional
import structlog
import httpx
from pydantic import BaseModel

from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.config.settings import settings


logger = structlog.get_logger()


class PolygonTicker(BaseModel):
    """Modelo para ticker de Polygon"""
    ticker: str
    name: str
    market: str
    locale: str
    primary_exchange: Optional[str] = None
    type: Optional[str] = None
    active: bool = True
    currency_symbol: Optional[str] = None
    cik: Optional[str] = None
    composite_figi: Optional[str] = None
    share_class_figi: Optional[str] = None
    last_updated_utc: Optional[str] = None


class TickerUniverseLoader:
    """
    Gestor del universo de tickers
    
    Responsabilidades:
    1. Cargar tickers desde Polygon /v3/reference/tickers
    2. Filtrar: market=stocks, locale=us, active=true
    3. Guardar en Redis (caché + set)
    4. Guardar en TimescaleDB (persistencia)
    5. Actualizar periódicamente (diario/semanal)
    """
    
    def __init__(
        self,
        redis_client: RedisClient,
        timescale_client: TimescaleClient,
        polygon_api_key: str,
    ):
        self.redis = redis_client
        self.timescale = timescale_client
        self.api_key = polygon_api_key
        self.base_url = "https://api.polygon.io"
        
        # Configuración
        self.market = "stocks"
        self.locale = "us"
        self.active_only = True
        self.limit = 1000  # Max permitido por Polygon
        
    async def fetch_all_tickers(self) -> List[PolygonTicker]:
        """
        Obtiene TODOS los tickers activos de US stocks desde Polygon
        
        Usa paginación automática para obtener todos los resultados.
        """
        logger.info(
            "fetching_tickers_from_polygon",
            market=self.market,
            locale=self.locale,
            active_only=self.active_only
        )
        
        all_tickers = []
        next_url = None
        page = 1
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                try:
                    if next_url:
                        # Polygon devuelve next_url relativo (sin host)
                        # Ejemplo: "/v3/reference/tickers?cursor=..."
                        if next_url.startswith('http'):
                            # Ya es URL completa
                            url = f"{next_url}&apiKey={self.api_key}"
                        else:
                            # Es path relativo
                            url = f"{self.base_url}{next_url}&apiKey={self.api_key}"
                    else:
                        # Primera request
                        url = (
                            f"{self.base_url}/v3/reference/tickers"
                            f"?market={self.market}"
                            f"&locale={self.locale}"
                            f"&active={'true' if self.active_only else 'false'}"
                            f"&limit={self.limit}"
                            f"&apiKey={self.api_key}"
                        )
                    
                    logger.debug(
                        "fetching_page",
                        page=page,
                        url=url.replace(self.api_key, "***")
                    )
                    
                    response = await client.get(url)
                    response.raise_for_status()
                    data = response.json()
                    
                    # Procesar resultados
                    results = data.get("results", [])
                    if not results:
                        break
                    
                    for ticker_data in results:
                        try:
                            ticker = PolygonTicker(**ticker_data)
                            all_tickers.append(ticker)
                        except Exception as e:
                            logger.warning(
                                "invalid_ticker_data",
                                ticker_data=ticker_data,
                                error=str(e)
                            )
                    
                    logger.info(
                        "page_fetched",
                        page=page,
                        tickers_in_page=len(results),
                        total_so_far=len(all_tickers)
                    )
                    
                    # Verificar si hay más páginas
                    next_url = data.get("next_url")
                    if not next_url:
                        break
                    
                    page += 1
                    
                    # Rate limiting: 5 requests per second
                    await asyncio.sleep(0.2)
                    
                except httpx.HTTPError as e:
                    logger.error(
                        "http_error_fetching_tickers",
                        page=page,
                        error=str(e)
                    )
                    break
                except Exception as e:
                    logger.error(
                        "error_fetching_tickers",
                        page=page,
                        error=str(e)
                    )
                    break
        
        logger.info(
            "fetch_completed",
            total_tickers=len(all_tickers),
            total_pages=page
        )
        
        return all_tickers
    
    async def save_to_redis(self, tickers: List[PolygonTicker]) -> int:
        """
        Guarda tickers en Redis
        
        Estructura:
        - SET ticker:universe -> {symbol1, symbol2, ...}
        - HASH ticker:data:{symbol} -> {name, market, type, ...}
        """
        logger.info("saving_to_redis", count=len(tickers))
        
        pipeline = await self.redis.client.pipeline()
        
        # Limpiar set anterior
        await self.redis.client.delete("ticker:universe")
        
        saved = 0
        for ticker in tickers:
            try:
                # Añadir al set
                pipeline.sadd("ticker:universe", ticker.ticker)
                
                # Guardar datos del ticker
                ticker_key = f"ticker:data:{ticker.ticker}"
                ticker_data = {
                    "symbol": ticker.ticker,
                    "name": ticker.name,
                    "market": ticker.market,
                    "locale": ticker.locale,
                    "type": ticker.type or "",
                    "exchange": ticker.primary_exchange or "",
                    "active": "1" if ticker.active else "0",
                    "cik": ticker.cik or "",
                    "figi": ticker.composite_figi or "",
                    "updated_at": ticker.last_updated_utc or datetime.utcnow().isoformat()
                }
                
                pipeline.hset(ticker_key, mapping=ticker_data)
                
                # TTL: 7 días (se refresca semanalmente)
                pipeline.expire(ticker_key, 604800)
                
                saved += 1
                
                # Ejecutar en batches de 1000
                if saved % 1000 == 0:
                    await pipeline.execute()
                    pipeline = await self.redis.client.pipeline()
                    logger.debug("redis_batch_saved", count=saved)
                
            except Exception as e:
                logger.warning(
                    "error_saving_ticker_to_redis",
                    symbol=ticker.ticker,
                    error=str(e)
                )
        
        # Ejecutar batch final
        if saved % 1000 != 0:
            await pipeline.execute()
        
        logger.info("redis_save_completed", saved=saved)
        return saved
    
    async def save_to_timescaledb(self, tickers: List[PolygonTicker]) -> int:
        """
        Guarda tickers en TimescaleDB (tabla ticker_universe)
        
        Usa UPSERT para actualizar tickers existentes.
        """
        logger.info("saving_to_timescaledb", count=len(tickers))
        
        if not tickers:
            return 0
        
        # Preparar batch insert
        values = []
        for ticker in tickers:
            values.append({
                "symbol": ticker.ticker,
                "is_active": ticker.active,
                "last_seen": datetime.utcnow(),
                "added_at": datetime.utcnow()
            })
        
        # UPSERT query
        query = """
            INSERT INTO ticker_universe (symbol, is_active, last_seen, added_at)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (symbol) 
            DO UPDATE SET
                is_active = EXCLUDED.is_active,
                last_seen = EXCLUDED.last_seen
        """
        
        saved = 0
        batch_size = 1000
        
        for i in range(0, len(values), batch_size):
            batch = values[i:i + batch_size]
            
            try:
                async with self.timescale.pool.acquire() as conn:
                    async with conn.transaction():
                        for item in batch:
                            await conn.execute(
                                query,
                                item["symbol"],
                                item["is_active"],
                                item["last_seen"],
                                item["added_at"]
                            )
                            saved += 1
                
                logger.debug(
                    "timescaledb_batch_saved",
                    saved=saved,
                    total=len(tickers)
                )
                
            except Exception as e:
                logger.error(
                    "error_saving_batch_to_timescaledb",
                    batch_start=i,
                    error=str(e)
                )
        
        logger.info("timescaledb_save_completed", saved=saved)
        return saved
    
    async def update_ticker_metadata(self, tickers: List[PolygonTicker]) -> int:
        """
        Actualiza tabla ticker_metadata con datos básicos de Polygon
        
        Luego el Historical Service enriquecerá con datos de FMP
        (market cap, float, etc.)
        """
        logger.info("updating_ticker_metadata", count=len(tickers))
        
        query = """
            INSERT INTO ticker_metadata (
                symbol, 
                company_name, 
                exchange, 
                is_actively_trading,
                updated_at
            )
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (symbol) 
            DO UPDATE SET
                company_name = EXCLUDED.company_name,
                exchange = EXCLUDED.exchange,
                is_actively_trading = EXCLUDED.is_actively_trading,
                updated_at = EXCLUDED.updated_at
        """
        
        updated = 0
        batch_size = 1000
        
        for i in range(0, len(tickers), batch_size):
            batch = tickers[i:i + batch_size]
            
            try:
                async with self.timescale.pool.acquire() as conn:
                    async with conn.transaction():
                        for ticker in batch:
                            await conn.execute(
                                query,
                                ticker.ticker,
                                ticker.name,
                                ticker.primary_exchange or "",
                                ticker.active,
                                datetime.utcnow()
                            )
                            updated += 1
                
                logger.debug(
                    "metadata_batch_updated",
                    updated=updated,
                    total=len(tickers)
                )
                
            except Exception as e:
                logger.error(
                    "error_updating_metadata_batch",
                    batch_start=i,
                    error=str(e)
                )
        
        logger.info("metadata_update_completed", updated=updated)
        return updated
    
    async def load_universe(self) -> Dict[str, int]:
        """
        Proceso completo de carga del universo
        
        Returns:
            Dict con estadísticas: {
                "fetched": int,
                "saved_redis": int,
                "saved_timescaledb": int,
                "updated_metadata": int
            }
        """
        logger.info("starting_universe_load")
        
        stats = {
            "fetched": 0,
            "saved_redis": 0,
            "saved_timescaledb": 0,
            "updated_metadata": 0
        }
        
        try:
            # 1. Fetch desde Polygon
            tickers = await self.fetch_all_tickers()
            stats["fetched"] = len(tickers)
            
            if not tickers:
                logger.warning("no_tickers_fetched")
                return stats
            
            # 2. Guardar en Redis
            stats["saved_redis"] = await self.save_to_redis(tickers)
            
            # 3. Guardar en TimescaleDB
            stats["saved_timescaledb"] = await self.save_to_timescaledb(tickers)
            
            # 4. Actualizar metadata
            stats["updated_metadata"] = await self.update_ticker_metadata(tickers)
            
            logger.info(
                "universe_load_completed",
                **stats
            )
            
            return stats
            
        except Exception as e:
            logger.error(
                "universe_load_failed",
                error=str(e),
                stats=stats
            )
            raise
    
    async def get_universe_stats(self) -> Dict[str, Any]:
        """
        Obtiene estadísticas del universo actual
        """
        stats = {}
        
        # Redis
        try:
            stats["redis_count"] = await self.redis.client.scard("ticker:universe")
        except:
            stats["redis_count"] = 0
        
        # TimescaleDB
        try:
            async with self.timescale.pool.acquire() as conn:
                # Total tickers
                result = await conn.fetchrow(
                    "SELECT COUNT(*) as total FROM ticker_universe WHERE is_active = true"
                )
                stats["timescaledb_active"] = result["total"]
                
                # Total tickers (incluyendo inactivos)
                result = await conn.fetchrow(
                    "SELECT COUNT(*) as total FROM ticker_universe"
                )
                stats["timescaledb_total"] = result["total"]
                
                # Última actualización
                result = await conn.fetchrow(
                    "SELECT MAX(last_seen) as last_update FROM ticker_universe"
                )
                stats["last_update"] = result["last_update"]
        except:
            stats["timescaledb_active"] = 0
            stats["timescaledb_total"] = 0
            stats["last_update"] = None
        
        return stats


async def main():
    """
    Script principal para carga manual del universo
    """
    import sys
    
    # Setup logging
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer()
        ]
    )
    
    logger.info("initializing_universe_loader")
    
    # Inicializar clientes
    redis_client = RedisClient()
    timescale_client = TimescaleClient()
    
    try:
        # Conectar
        await redis_client.connect()
        await timescale_client.connect()
        
        # Crear loader
        loader = TickerUniverseLoader(
            redis_client=redis_client,
            timescale_client=timescale_client,
            polygon_api_key=settings.POLYGON_API_KEY
        )
        
        # Cargar universo
        stats = await loader.load_universe()
        
        # Mostrar estadísticas
        print("\n" + "="*60)
        print("✅ CARGA DE UNIVERSO COMPLETADA")
        print("="*60)
        print(f"📊 Tickers obtenidos de Polygon:     {stats['fetched']:,}")
        print(f"💾 Guardados en Redis:                {stats['saved_redis']:,}")
        print(f"🗄️  Guardados en TimescaleDB:         {stats['saved_timescaledb']:,}")
        print(f"📝 Metadata actualizada:              {stats['updated_metadata']:,}")
        print("="*60)
        
        # Verificar estadísticas
        current_stats = await loader.get_universe_stats()
        print("\n📈 ESTADÍSTICAS ACTUALES:")
        print(f"   Redis:          {current_stats['redis_count']:,} tickers")
        print(f"   TimescaleDB:    {current_stats['timescaledb_active']:,} activos / {current_stats['timescaledb_total']:,} total")
        print(f"   Última actualización: {current_stats['last_update']}")
        print()
        
        return 0
        
    except Exception as e:
        logger.error("universe_load_failed", error=str(e))
        print(f"\n❌ Error: {e}\n")
        return 1
        
    finally:
        await redis_client.disconnect()
        await timescale_client.disconnect()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

