"""
Cargador de Universo de Tickers desde Polygon
Obtiene todos los tickers activos de US stocks y los sincroniza con Redis y TimescaleDB

NOTA: Usa http_clients.polygon con connection pooling.
"""

import asyncio
import sys
from datetime import datetime, date
from typing import List, Dict, Any, Optional
import structlog
from pydantic import BaseModel

from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.config.settings import settings
from http_clients import http_clients


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
        
        # Usar cliente Polygon con connection pooling
        while True:
            try:
                if next_url:
                    # Polygon devuelve next_url relativo (sin host)
                    # Ejemplo: "/v3/reference/tickers?cursor=..."
                    if next_url.startswith('http'):
                        # Ya es URL completa - extraer path
                        endpoint = next_url.replace("https://api.polygon.io", "")
                    else:
                        # Es path relativo
                        endpoint = next_url
                else:
                    # Primera request
                    endpoint = (
                        f"/v3/reference/tickers"
                        f"?market={self.market}"
                        f"&locale={self.locale}"
                        f"&active={'true' if self.active_only else 'false'}"
                        f"&limit={self.limit}"
                    )
                
                logger.debug(
                    "fetching_page",
                    page=page,
                    endpoint=endpoint
                )
                
                # Usar cliente compartido
                data = await http_clients.polygon.get(endpoint)
                
                if not data:
                    logger.warning("no_data_from_polygon", page=page)
                    break
                
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
                
            except Exception as e:
                logger.error(
                    "error_fetching_tickers",
                    page=page,
                    error=str(e)
                )
                # NO romper - intentar siguiente página después de esperar
                if page > 30:  # Límite de seguridad
                    logger.error("max_pages_exceeded", pages=30)
                    break
                await asyncio.sleep(5)  # Esperar antes de continuar
        
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
        Guarda tickers en TimescaleDB (tabla tickers_unified)
        
        MIGRADO: Usa tickers_unified directamente en lugar de ticker_universe
        Mapeo de campos:
        - symbol → symbol
        - is_active → is_actively_trading
        - last_seen → updated_at
        - added_at → created_at
        
        Usa UPSERT para actualizar tickers existentes.
        """
        logger.info("saving_to_timescaledb_unified", count=len(tickers))
        
        if not tickers:
            return 0
        
        # Preparar batch insert
        values = []
        current_time = datetime.utcnow()
        
        for ticker in tickers:
            values.append({
                "symbol": ticker.ticker,
                "company_name": ticker.name,
                "is_actively_trading": ticker.active,
                "exchange": ticker.primary_exchange,
                "type": ticker.type,
                "market": ticker.market,
                "locale": ticker.locale,
                "cik": ticker.cik,
                "composite_figi": ticker.composite_figi,
                "share_class_figi": ticker.share_class_figi,
                "updated_at": current_time,
                "created_at": current_time
            })
        
        # UPSERT query usando tickers_unified
        query = """
            INSERT INTO tickers_unified (
                symbol, company_name, exchange, type, market, locale,
                cik, composite_figi, share_class_figi,
                is_actively_trading, updated_at, created_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW(), NOW())
            ON CONFLICT (symbol) 
            DO UPDATE SET
                company_name = COALESCE(EXCLUDED.company_name, tickers_unified.company_name),
                exchange = COALESCE(EXCLUDED.exchange, tickers_unified.exchange),
                type = COALESCE(EXCLUDED.type, tickers_unified.type),
                market = COALESCE(EXCLUDED.market, tickers_unified.market),
                locale = COALESCE(EXCLUDED.locale, tickers_unified.locale),
                cik = COALESCE(EXCLUDED.cik, tickers_unified.cik),
                composite_figi = COALESCE(EXCLUDED.composite_figi, tickers_unified.composite_figi),
                share_class_figi = COALESCE(EXCLUDED.share_class_figi, tickers_unified.share_class_figi),
                is_actively_trading = EXCLUDED.is_actively_trading,
                updated_at = NOW()
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
                                item["company_name"],
                                item["exchange"],
                                item["type"],
                                item["market"],
                                item["locale"],
                                item["cik"],
                                item["composite_figi"],
                                item["share_class_figi"],
                                item["is_actively_trading"]
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
    
    # ELIMINADO: update_ticker_metadata()
    # RAZÓN: ticker_metadata ahora es responsabilidad EXCLUSIVA de data_maintenance
    # Historical SOLO maneja ticker_universe
    # Ver: AUDITORIA_SERVICIOS.md - Problema #1
    
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
            "saved_timescaledb": 0
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
            
            # 3. Guardar en TimescaleDB (ticker_universe)
            stats["saved_timescaledb"] = await self.save_to_timescaledb(tickers)
            
            # 4. Metadata se enriquece en data_maintenance (no aquí)
            logger.info("ticker_universe_loaded_metadata_delegated_to_data_maintenance")
            
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
        Obtiene estadísticas del universo actual desde tickers_unified
        
        MIGRADO: Usa tickers_unified directamente
        """
        stats = {}
        
        # Redis
        try:
            stats["redis_count"] = await self.redis.client.scard("ticker:universe")
        except:
            stats["redis_count"] = 0
        
        # TimescaleDB (usando tickers_unified)
        try:
            async with self.timescale.pool.acquire() as conn:
                # Total tickers activos
                result = await conn.fetchrow(
                    "SELECT COUNT(*) as total FROM tickers_unified WHERE is_actively_trading = true"
                )
                stats["timescaledb_active"] = result["total"]
                
                # Total tickers (incluyendo inactivos)
                result = await conn.fetchrow(
                    "SELECT COUNT(*) as total FROM tickers_unified"
                )
                stats["timescaledb_total"] = result["total"]
                
                # Última actualización
                result = await conn.fetchrow(
                    "SELECT MAX(updated_at) as last_update FROM tickers_unified"
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

