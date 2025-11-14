"""
Historical Service - REFACTORED
Loads and caches historical/reference data from Polygon
Provides metadata like float, market cap, avg volume, etc.

REFACTOR CHANGES:
- Event-driven architecture with EventBus
- Shared functions to avoid code duplication
- Robust warmup strategy (4 layers of protection)
- Automatic cleanup on startup
- Coordinated universe + warmup execution
"""

import asyncio
import time
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi import Query

import sys
sys.path.append('/app')

from shared.config.settings import settings
from shared.models.scanner import TickerMetadata
from shared.models.fmp import FMPProfile, FMPQuote
from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import get_logger, configure_logging
from shared.events import (
    EventBus,
    EventType,
    Event,
    create_day_changed_event,
    create_session_changed_event,
    create_warmup_completed_event
)

from historical_loader import HistoricalLoader
from ticker_universe_loader import TickerUniverseLoader
from polygon_data_loader import PolygonDataLoader

# Configure logging
configure_logging(service_name="historical")
logger = get_logger(__name__)


# =============================================
# GLOBALS
# =============================================

redis_client: Optional[RedisClient] = None
timescale_client: Optional[TimescaleClient] = None
historical_loader: Optional[HistoricalLoader] = None
ticker_universe_loader: Optional[TickerUniverseLoader] = None
polygon_data_loader: Optional[PolygonDataLoader] = None
event_bus: Optional[EventBus] = None

# Lock para prevenir ejecuciones simultáneas de warmup
warmup_in_progress = False
warmup_lock = asyncio.Lock()


# =============================================
# SHARED FUNCTIONS (NO DUPLICAR CÓDIGO)
# =============================================

async def _get_active_symbols() -> List[str]:
    """
    Helper: Obtiene símbolos activos del universo
    
    Returns:
        Lista de símbolos activos
    """
    try:
        query = "SELECT symbol FROM ticker_universe WHERE is_active = true ORDER BY symbol"
        rows = await timescale_client.fetch(query)
        return [row["symbol"] for row in rows]
    except Exception as e:
        logger.error("error_getting_active_symbols", error=str(e))
        return []


async def execute_warmup() -> Dict[str, Any]:
    """
    Función CENTRAL para ejecutar warmup de metadata
    
    REUTILIZADA por:
    - Event handlers (SESSION_CHANGED, DAY_CHANGED)
    - Background fallback (periodic)
    - API endpoint manual
    
    Previene ejecuciones simultáneas con lock
    Marca timestamp al completar
    Publica evento de completado
    
    Returns:
        Stats del warmup ejecutado
    """
    global warmup_in_progress
    
    # Prevenir ejecuciones simultáneas
    async with warmup_lock:
        if warmup_in_progress:
            logger.warning("warmup_already_in_progress_skipping")
            return {"status": "skipped", "reason": "already_in_progress"}
        
        warmup_in_progress = True
    
    try:
        start_time = time.time()
        
        logger.info("🔥 WARMUP INICIANDO", trigger="automatic_or_manual")
        
        # 1. Obtener símbolos del universo
        symbols = await _get_active_symbols()
        
        if not symbols:
            logger.warning("no_symbols_found_skipping_warmup")
            return {"status": "skipped", "reason": "no_symbols"}
        
        logger.info(f"📊 Warmup: {len(symbols)} tickers")
        
        # 2. Cargar datos con paralelización
        loaded = await polygon_data_loader.load_all_ticker_data(
            symbols,
            calculate_avg_volume=True,
            max_concurrent=80
        )
        
        duration = time.time() - start_time
        
        # 3. Marcar timestamp de warmup completado
        await redis_client.set(
            "historical:last_warmup",
            datetime.now().isoformat()
        )
        
        logger.info(
            "✅ WARMUP COMPLETADO",
            tickers_loaded=loaded,
            duration_seconds=int(duration),
            duration_minutes=round(duration/60, 2)
        )
        
        # 4. Publicar evento de warmup completado
        if event_bus:
            await event_bus.publish(
                create_warmup_completed_event(
                    tickers_loaded=loaded,
                    duration_seconds=duration
                )
            )
        
        # 5. NO limpiar cachés - las metadatas son necesarias para el scanner
        # COMENTADO: Esto estaba borrando las metadatas después de cargarlas
        # try:
        #     deleted = await redis_client.delete_pattern("metadata:ticker:*")
        #     logger.info("metadata_cache_cleared_after_warmup", keys_deleted=deleted)
        # except Exception as e:
        #     logger.warning("cache_cleanup_failed", error=str(e))
        
        return {
            "status": "completed",
            "tickers_loaded": loaded,
            "duration_seconds": duration,
            "timestamp": datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error("warmup_execution_error", error=str(e))
        raise
    
    finally:
        warmup_in_progress = False


async def execute_universe_update() -> Dict[str, Any]:
    """
    Función CENTRAL para actualizar universo de tickers
    
    REUTILIZADA por:
    - Event handlers
    - Background fallback
    - API endpoint manual
    
    Marca timestamp al completar
    Publica evento de completado
    
    Returns:
        Stats del universe update
    """
    try:
        logger.info("🌍 UNIVERSE UPDATE INICIANDO")
        
        # Ejecutar carga de universo
        stats = await ticker_universe_loader.load_universe()
        
        # Marcar timestamp
        await redis_client.set(
            "historical:last_universe_update",
            datetime.now().isoformat()
        )
        
        logger.info(
            "✅ UNIVERSE UPDATE COMPLETADO",
            **stats
        )
        
        # Publicar evento (si se necesita)
        # if event_bus:
        #     await event_bus.publish(create_universe_updated_event(...))
        
        return stats
    
    except Exception as e:
        logger.error("universe_update_error", error=str(e))
        raise


async def check_and_cleanup_on_startup():
    """
    Al iniciar servicio, verificar universo
    
    NOTA: Warmup automático DESACTIVADO
    El servicio data_maintenance ahora se encarga de cargar metadata
    Historical solo verifica el universo (necesario para funcionamiento)
    
    Verifica:
    1. ¿Existe universo en Redis/DB?
    2. Si no existe o está obsoleto (>7 días) → cargar
    
    Warmup se ejecuta solo manualmente via: POST /api/warmup
    """
    logger.info("checking_data_status_on_startup")
    
    try:
        # Check 1: ¿Existe universo?
        universe_exists = await redis_client.client.exists("ticker:universe")
        
        if not universe_exists:
            logger.warning("no_universe_found_loading_now")
            await execute_universe_update()
        else:
            # Verificar antigüedad del universo
            last_update = await redis_client.get("historical:last_universe_update")
            
            if last_update:
                try:
                    last_update_date = datetime.fromisoformat(
                        last_update.replace('Z', '+00:00')
                    ).date()
                    
                    # Si es de hace más de 7 días → actualizar
                    days_old = (datetime.now().date() - last_update_date).days
                    if days_old > 7:
                        logger.warning("universe_outdated_updating", days_old=days_old)
                        await execute_universe_update()
                    else:
                        logger.info("universe_up_to_date", days_old=days_old)
                except Exception as e:
                    logger.warning("error_parsing_last_update", error=str(e))
        
        # Warmup desactivado - lo hace data_maintenance
        logger.info("warmup_delegated_to_data_maintenance_use_manual_endpoint_if_needed")
    
    except Exception as e:
        logger.error("startup_check_error", error=str(e))


# =============================================
# EVENT HANDLERS
# =============================================

async def handle_session_changed(event: Event):
    """
    Handler para SESSION_CHANGED
    
    NOTA: Warmup automático DESACTIVADO
    El servicio data_maintenance ahora se encarga de cargar metadata al cierre
    Historical solo SIRVE los datos a través de sus endpoints
    """
    try:
        new_session = event.data.get('new_session')
        previous_session = event.data.get('previous_session')
        
        logger.info(
            "session_changed_event_received",
            new_session=new_session,
            previous_session=previous_session
        )
        
        # Warmup automático desactivado - lo hace data_maintenance
        # Para ejecutar manualmente: POST /api/warmup
        logger.debug("warmup_delegated_to_data_maintenance_service")
    
    except Exception as e:
        logger.error("error_handling_session_changed", error=str(e))


async def handle_day_changed(event: Event):
    """
    Handler para DAY_CHANGED
    
    NOTA: Warmup automático DESACTIVADO
    El servicio data_maintenance ahora se encarga de cargar metadata
    Historical solo SIRVE los datos a través de sus endpoints
    """
    try:
        new_date = event.data.get('new_date')
        previous_date = event.data.get('previous_date')
        
        logger.info("day_changed_event_received", new_date=new_date, previous_date=previous_date)
        
        # Warmup automático desactivado - lo hace data_maintenance
        logger.debug("warmup_delegated_to_data_maintenance_service")
    
    except Exception as e:
        logger.error("error_handling_day_changed", error=str(e))


# =============================================
# BACKGROUND FALLBACK (PERIÓDICO)
# =============================================

async def periodic_warmup_fallback():
    """
    Tarea periódica DESACTIVADA
    
    NOTA: El servicio data_maintenance ahora se encarga del mantenimiento automático
    Historical solo SIRVE los datos a través de sus endpoints
    
    Mantener ejecutándose para compatibilidad pero sin hacer nada
    """
    logger.info("periodic_warmup_fallback_disabled_delegated_to_data_maintenance")
    
    while True:
        try:
            # Solo esperar indefinidamente
            await asyncio.sleep(86400)
        
        except asyncio.CancelledError:
            logger.info("periodic_warmup_fallback_cancelled")
            break


# =============================================
# LIFECYCLE
# =============================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager con Event Bus integrado"""
    global redis_client, timescale_client, event_bus
    global historical_loader, ticker_universe_loader, polygon_data_loader
    
    logger.info("Starting Historical Service (REFACTORED)")
    
    # 1. Initialize clients
    redis_client = RedisClient()
    await redis_client.connect()
    
    timescale_client = TimescaleClient()
    await timescale_client.connect()
    
    # 2. Initialize Event Bus
    event_bus = EventBus(redis_client, "historical")
    
    # 3. Initialize loaders
    historical_loader = HistoricalLoader(redis_client, timescale_client)
    ticker_universe_loader = TickerUniverseLoader(
        redis_client=redis_client,
        timescale_client=timescale_client,
        polygon_api_key=settings.POLYGON_API_KEY
    )
    polygon_data_loader = PolygonDataLoader(
        redis_client=redis_client,
        timescale_client=timescale_client,
        polygon_api_key=settings.POLYGON_API_KEY
    )
    
    # 4. Register event handlers
    event_bus.subscribe(EventType.SESSION_CHANGED, handle_session_changed)
    event_bus.subscribe(EventType.DAY_CHANGED, handle_day_changed)
    
    # 5. Start event listener
    await event_bus.start_listening()
    logger.info("EventBus listener started")
    
    # 6. Check data on startup (NUEVO - verificación automática)
    await check_and_cleanup_on_startup()
    
    # 7. Start fallback task (última red de seguridad)
    fallback_task = asyncio.create_task(periodic_warmup_fallback())
    
    logger.info("Historical Service started successfully")
    logger.info("✅ Event-driven warmup activated (4 layers of protection)")
    
    yield
    
    # Cleanup
    logger.info("Shutting down Historical Service")
    
    # Cancel fallback task
    fallback_task.cancel()
    try:
        await fallback_task
    except asyncio.CancelledError:
        pass
    
    # Stop event listener
    await event_bus.stop_listening()
    
    # Disconnect clients
    if timescale_client:
        await timescale_client.disconnect()
    
    if redis_client:
        await redis_client.disconnect()
    
    logger.info("Historical Service stopped")


app = FastAPI(
    title="Historical Service",
    description="Loads and caches historical/reference data (REFACTORED)",
    version="2.0.0",
    lifespan=lifespan
)


# =============================================
# API ENDPOINTS (REFACTORED)
# =============================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    db_health = await timescale_client.health_check()
    redis_health = await redis_client.ping()
    
    return {
        "status": "healthy" if (db_health and redis_health) else "degraded",
        "service": "historical",
        "version": "2.0.0-refactored",
        "database": "healthy" if db_health else "unhealthy",
        "redis": "healthy" if redis_health else "unhealthy",
        "event_bus": "connected" if event_bus else "disconnected"
    }


@app.get("/api/metadata/{symbol}", response_model=TickerMetadata)
async def get_ticker_metadata(symbol: str):
    """Get metadata for a specific ticker"""
    try:
        symbol = symbol.upper()
        metadata = await historical_loader.get_ticker_metadata(symbol)
        
        if not metadata:
            raise HTTPException(status_code=404, detail=f"Ticker {symbol} not found")
        
        return metadata
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting metadata", symbol=symbol, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/metadata/bulk")
async def get_bulk_metadata(symbols: str):
    """
    Get metadata for multiple tickers
    
    Args:
        symbols: Comma-separated list of symbols (e.g., "AAPL,MSFT,GOOGL")
    """
    try:
        symbol_list = [s.strip().upper() for s in symbols.split(',')]
        
        if len(symbol_list) > 100:
            raise HTTPException(status_code=400, detail="Maximum 100 symbols allowed")
        
        results = await historical_loader.get_bulk_metadata(symbol_list)
        
        return {
            "symbols": symbol_list,
            "count": len(results),
            "results": results
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting bulk metadata", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/rvol/hist-avg")
async def get_rvol_hist_avg(
    symbol: str = Query(..., description="Ticker symbol"),
    slot: int = Query(..., ge=0, le=250, description="Slot number (5m slots from 4:00 ET, 0-250)"),
    days: int = Query(5, ge=1, le=60, description="Lookback trading days (trading days)")
):
    """
    Calcula y cachea el promedio histórico de volumen ACUMULADO hasta un slot
    para los últimos N días de trading.
    - Lee de TimescaleDB (volume_slots)
    - Escribe en Redis HASH: rvol:hist:avg:{symbol}:{days} -> field {slot}
    - Devuelve { symbol, slot, avg }
    """
    try:
        sym = symbol.upper()
        # Últimos N días de TRADING reales con datos, no rango de calendario
        query = (
            "WITH last_days AS ("
            "  SELECT DISTINCT date"
            "  FROM volume_slots"
            "  WHERE symbol = $1 AND date < CURRENT_DATE"
            "  ORDER BY date DESC"
            "  LIMIT $3"
            "), filled AS ("
            "  SELECT vs.date, vs.slot_number,"
            "         MAX(vs.volume_accumulated) OVER ("
            "             PARTITION BY vs.date"
            "             ORDER BY vs.slot_number"
            "             ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW"
            "         ) AS vol_acc"
            "  FROM volume_slots vs"
            "  JOIN last_days d ON vs.date = d.date"
            "  WHERE vs.symbol = $1 AND vs.slot_number <= $2"
            ")"
            "SELECT AVG(v) AS avg_vol FROM ("
            "  SELECT date, MAX(vol_acc) AS v"
            "  FROM filled"
            "  GROUP BY date"
            ") t"
        )
        avg_vol = await timescale_client.fetchval(query, sym, slot, days)
        if avg_vol is None:
            raise HTTPException(status_code=404, detail="No historical data")
        
        # Guardar en Redis HASH (optimizado - mismo formato que bulk)
        hash_key = f"rvol:hist:avg:{sym}:{days}"
        await redis_client.hset(hash_key, str(slot), str(int(avg_vol)))
        await redis_client.expire(hash_key, 50400)  # 14 horas TTL
        
        return {"symbol": sym, "slot": slot, "avg": int(avg_vol)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("error_getting_rvol_hist_avg", symbol=symbol, slot=slot, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/rvol/hist-avg/bulk")
async def get_rvol_hist_avg_bulk(
    symbol: str = Query(..., description="Ticker symbol"),
    days: int = Query(5, ge=1, le=60, description="Lookback trading days (trading days)"),
    max_slot: int = Query(250, ge=1, le=250, description="Maximum slot to compute (0-250, trading day slots)")
):
    """
    Calcula el promedio histórico acumulado por slot para TODOS los slots de un símbolo
    en una sola consulta y lo cachea en Redis usando HASH (optimizado):
      - Hash: rvol:hist:avg:{SYMBOL}:{DAYS} con fields {slot -> avg}
      - TTL: 8 horas (suficiente para día de trading)
      - Límite: 250 slots (4:00 AM - 8:00 PM = 192 slots reales + margen)
    """
    try:
        sym = symbol.upper()
        # Consulta con ventana para rellenar faltantes por día (running max)
        query = (
            "WITH last_days AS ("
            "  SELECT DISTINCT date"
            "  FROM volume_slots"
            "  WHERE symbol = $1 AND date < CURRENT_DATE"
            "  ORDER BY date DESC"
            "  LIMIT $2"
            "), filled AS ("
            "  SELECT vs.date, vs.slot_number,"
            "         MAX(vs.volume_accumulated) OVER ("
            "             PARTITION BY vs.date"
            "             ORDER BY vs.slot_number"
            "             ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW"
            "         ) AS vol_acc"
            "  FROM volume_slots vs"
            "  JOIN last_days d ON vs.date = d.date"
            "  WHERE vs.symbol = $1 AND vs.slot_number <= $3"
            "), slots AS ("
            "  SELECT generate_series(0, $3) AS slot_number"
            ")"
            "SELECT s.slot_number, AVG("
            "  (SELECT MAX(f.vol_acc) FROM filled f WHERE f.date = d.date AND f.slot_number <= s.slot_number)"
            ") AS avg_vol"
            "  FROM (SELECT date FROM last_days) d"
            "  CROSS JOIN slots s"
            " GROUP BY s.slot_number"
            " ORDER BY s.slot_number"
        )
        rows = await timescale_client.fetch(query, sym, days, max_slot)
        if not rows:
            raise HTTPException(status_code=404, detail="No historical data")

        # Preparar hash para Redis (SOLO hash, sin claves individuales)
        hash_key = f"rvol:hist:avg:{sym}:{days}"
        mapping = {}
        for row in rows:
            slot_num = int(row["slot_number"]) if isinstance(row, dict) else int(row[0])
            raw_avg = (row["avg_vol"]) if isinstance(row, dict) else (row[1])
            avg_val = int(raw_avg or 0)
            mapping[str(slot_num)] = str(avg_val)

        # Guardar SOLO hash (optimizado - 1 clave en lugar de 250)
        await redis_client.hmset(hash_key, mapping, serialize=False)
        await redis_client.expire(hash_key, 50400)  # 14 horas TTL

        return {"symbol": sym, "days": days, "slots": len(mapping)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("error_getting_rvol_hist_avg_bulk", symbol=symbol, days=days, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/metadata/load/{symbol}")
async def load_ticker_metadata(symbol: str, background_tasks: BackgroundTasks):
    """Load/refresh metadata for a ticker"""
    try:
        symbol = symbol.upper()
        
        # Load in background
        background_tasks.add_task(
            historical_loader.load_and_cache_ticker,
            symbol
        )
        
        return {
            "status": "loading",
            "symbol": symbol,
            "message": "Metadata loading in background"
        }
    
    except Exception as e:
        logger.error("Error loading metadata", symbol=symbol, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/universe/load")
async def load_universe(background_tasks: BackgroundTasks):
    """
    Carga el universo completo de tickers desde Polygon
    
    REFACTORED: Usa función compartida execute_universe_update()
    """
    try:
        # Ejecutar en background usando función compartida
        background_tasks.add_task(execute_universe_update)
        
        return {
            "status": "loading",
            "message": "Loading ticker universe from Polygon",
            "source": "Polygon /v3/reference/tickers",
            "filters": {
                "market": "stocks",
                "locale": "us",
                "active": True
            }
        }
    
    except Exception as e:
        logger.error("Error loading universe", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/warmup/premarket")
async def warmup_premarket_data(background_tasks: BackgroundTasks):
    """
    🔥 PRE-CARGA TODOS los datos desde Polygon
    
    REFACTORED: Usa función compartida execute_warmup()
    Ya NO duplica código
    
    Con Plan Advanced de Polygon (100 req/seg):
    - Duración: ~5-8 minutos para 12,000+ tickers
    - API calls: ~24,000+ (ticker details + aggregates)
    - Paralelización: 80 requests/segundo (seguro)
    """
    try:
        # Obtener count de símbolos para el response
        symbol_count = await timescale_client.fetchval(
            "SELECT COUNT(*) FROM ticker_universe WHERE is_active = true"
        )
        
        # Ejecutar en background usando función compartida
        background_tasks.add_task(execute_warmup)
        
        return {
            "status": "loading",
            "message": "Pre-market warmup iniciado - Polygon Advanced",
            "source": "Polygon Ticker Details + Aggregates (30 días)",
            "refactored": True,
            "shared_function": "execute_warmup()",
            "parallelization": {
                "max_concurrent_requests": 80,
                "tickers_per_second": 40,
                "estimated_duration_minutes": "5-8"
            },
            "api_calls_estimate": symbol_count * 2,
            "data_loaded": [
                "Market Cap (Polygon ticker details)",
                "Float/Outstanding Shares (Polygon weighted_shares)",
                "Sector/Industry (de SIC code mapeado)",
                "Average Volume 30d (calculado de aggregates históricos)"
            ]
        }
    
    except Exception as e:
        logger.error("Error starting premarket warmup", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/universe/stats")
async def get_universe_stats():
    """
    Obtiene estadísticas del universo de tickers
    """
    try:
        stats = await ticker_universe_loader.get_universe_stats()
        
        # Agregar info de último warmup
        last_warmup = await redis_client.get("historical:last_warmup")
        last_universe_update = await redis_client.get("historical:last_universe_update")
        
        stats["last_warmup"] = last_warmup
        stats["last_universe_update"] = last_universe_update
        
        return stats
    
    except Exception as e:
        logger.error("Error getting universe stats", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/universe/symbols")
async def get_universe_symbols(limit: int = settings.default_query_limit):
    """
    Obtiene una muestra de símbolos del universo
    """
    try:
        # Validar límite máximo
        limit = min(limit, settings.max_query_limit)
        
        # Obtener símbolos de Redis
        symbols = await redis_client.client.srandmember("ticker:universe", limit)
        
        return {
            "count": len(symbols),
            "limit": limit,
            "symbols": [s.decode('utf-8') if isinstance(s, bytes) else s for s in symbols]
        }
    
    except Exception as e:
        logger.error("Error getting universe symbols", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stats")
async def get_stats():
    """Get service statistics"""
    try:
        stats = await historical_loader.get_stats()
        
        # Agregar stats de warmup
        last_warmup = await redis_client.get("historical:last_warmup")
        warmup_status = "unknown"
        
        if last_warmup:
            try:
                warmup_time = datetime.fromisoformat(last_warmup.replace('Z', '+00:00'))
                hours_ago = (datetime.now() - warmup_time.replace(tzinfo=None)).total_seconds() / 3600
                
                if hours_ago < 12:
                    warmup_status = "fresh"
                elif hours_ago < 24:
                    warmup_status = "recent"
                else:
                    warmup_status = "stale"
            except:
                pass
        
        stats["warmup"] = {
            "last_execution": last_warmup,
            "status": warmup_status,
            "in_progress": warmup_in_progress
        }
        
        return stats
    
    except Exception as e:
        logger.error("Error getting stats", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/cache/clear")
async def clear_cache(symbol: Optional[str] = None):
    """
    Clear Redis cache
    
    Args:
        symbol: Optional specific symbol to clear (clears all if not provided)
    """
    try:
        if symbol:
            symbol = symbol.upper()
            await historical_loader.clear_cache(symbol)
            return {"status": "cleared", "symbol": symbol}
        else:
            await historical_loader.clear_all_cache()
            return {"status": "cleared", "scope": "all"}
    
    except Exception as e:
        logger.error("Error clearing cache", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# =============================================
# ADMIN/DEBUG ENDPOINTS
# =============================================

@app.post("/api/admin/force-warmup")
async def force_warmup():
    """
    Forzar ejecución inmediata de warmup (para testing/admin)
    
    NO usa background task, ejecuta sincrónicamente
    """
    try:
        logger.info("force_warmup_requested_by_admin")
        result = await execute_warmup()
        return result
    
    except Exception as e:
        logger.error("Error forcing warmup", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/force-universe-update")
async def force_universe_update():
    """
    Forzar actualización inmediata de universo (para testing/admin)
    """
    try:
        logger.info("force_universe_update_requested_by_admin")
        result = await execute_universe_update()
        return result
    
    except Exception as e:
        logger.error("Error forcing universe update", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# =============================================
# ENTRY POINT
# =============================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.historical_port,
        reload=settings.debug
    )
