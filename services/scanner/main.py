"""
Scanner Service
Core scanning engine that combines real-time and historical data,
calculates indicators (RVOL), and applies configurable filters

ARQUITECTURA EVENT-DRIVEN:
- Se suscribe a DAY_CHANGED del EventBus (market_session es la fuente de verdad)
- Se suscribe a SESSION_CHANGED para capturar volumen regular al inicio de POST_MARKET
- NO detecta días nuevos por sí mismo
- Limpia cachés de gaps/tracking cuando market_session notifica nuevo día

POST-MARKET VOLUME CAPTURE:
- Cuando la sesión cambia de MARKET_OPEN a POST_MARKET
- Captura el volumen de sesión regular (09:30-16:00 ET) para todos los tickers del scanner
- Usa Polygon Aggregates API para sumar velas de minuto
- Permite calcular postmarket_volume = current_volume - regular_volume
"""

import asyncio
from datetime import datetime, date
from contextlib import asynccontextmanager
from typing import Optional, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import sys
sys.path.append('/app')

from shared.config.settings import settings
from shared.models.scanner import ScannerResult, ScannerTicker, FilterConfig
from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import get_logger, configure_logging
from shared.utils.redis_stream_manager import (
    initialize_stream_manager,
    get_stream_manager
)
from shared.utils.snapshot_manager import SnapshotManager
from shared.events import EventBus, EventType, Event

from scanner_engine import ScannerEngine
from scanner_categories import ScannerCategory
from http_clients import http_clients
from postmarket_capture import PostMarketVolumeCapture


# Configure logging
configure_logging(service_name="scanner")
logger = get_logger(__name__)


# =============================================
# GLOBALS
# =============================================

redis_client: Optional[RedisClient] = None
timescale_client: Optional[TimescaleClient] = None
scanner_engine: Optional[ScannerEngine] = None
event_bus: Optional[EventBus] = None
postmarket_capture: Optional[PostMarketVolumeCapture] = None
background_tasks: List[asyncio.Task] = []
is_running = False

# Estado de mercado (se actualiza via EventBus, no en cada iteración)
is_holiday_mode: bool = False
current_trading_date: Optional[date] = None
current_session: Optional[str] = None  # Para detectar transiciones de sesión


# =============================================
# Market Status (Event-Driven)
# =============================================

async def check_initial_market_status() -> None:
    """
    Lee el estado del mercado UNA VEZ al iniciar.
    """
    global is_holiday_mode, current_trading_date
    
    try:
        status_data = await redis_client.get(f"{settings.key_prefix_market}:session:status")
        
        if status_data:
            is_holiday = status_data.get('is_holiday', False)
            is_trading_day = status_data.get('is_trading_day', True)
            trading_date_str = status_data.get('trading_date')
            
            is_holiday_mode = is_holiday or not is_trading_day
            
            if trading_date_str:
                current_trading_date = date.fromisoformat(trading_date_str)
            
            logger.info(
                "📅 market_status_checked",
                is_holiday=is_holiday,
                is_trading_day=is_trading_day,
                holiday_mode=is_holiday_mode,
                trading_date=trading_date_str
            )
            
            if is_holiday_mode:
                logger.warning(
                    "🚨 HOLIDAY_MODE_ACTIVE - Scanner reducirá frecuencia",
                    reason="Market is closed for holiday"
                )
        else:
            logger.warning("market_status_not_found_in_redis")
            is_holiday_mode = False
    
    except Exception as e:
        logger.error("error_checking_market_status", error=str(e))
        is_holiday_mode = False


async def handle_day_changed(event: Event) -> None:
    """
    Handler para el evento DAY_CHANGED.
    Limpia cachés de gaps y tracking cuando cambia el día de trading.
    
    IMPORTANTE: Solo limpia si NO es día festivo.
    """
    global is_holiday_mode, current_trading_date
    
    new_date_str = event.data.get('new_date')
    logger.info("📆 day_changed_event_received", new_date=new_date_str)
    
    # Re-verificar estado del mercado
    await check_initial_market_status()
    
    # Solo limpiar cachés si NO es festivo
    if not is_holiday_mode:
        logger.info("clearing_scanner_caches", reason="new_trading_day")
        
        if scanner_engine and scanner_engine.gap_tracker:
            scanner_engine.gap_tracker.clear_for_new_day()
        
        if scanner_engine:
            scanner_engine.clear_postmarket_cache()
            scanner_engine._user_scans_frozen = False
    else:
        logger.info(
            "⏭️ skipping_cache_clear",
            reason="holiday_mode_active",
            date=new_date_str
        )


async def handle_session_changed(event: Event) -> None:
    """
    Handler para el evento SESSION_CHANGED.
    
    Detecta transiciones de sesión y ejecuta acciones específicas:
    - PRE_MARKET → MARKET_OPEN: Captura gaps de premarket (congelar change_percent a las 09:30)
    - MARKET_OPEN → POST_MARKET: Inicia captura de volumen regular
    - POST_MARKET → CLOSED: Freeze user scans con TTL dinámico
    
    El volumen regular se obtiene sumando velas de minuto de la API de Polygon
    para el período 09:30-16:00 ET. Esto permite calcular el postmarket_volume
    de manera precisa.
    
    El freeze de user scans extiende el TTL para que los datos persistan hasta
    que el maintenance service los limpie en el próximo trading day (3:45 AM ET).
    """
    global current_session
    
    new_session = event.data.get('new_session')
    previous_session = event.data.get('previous_session')
    trading_date = event.data.get('trading_date')
    
    logger.info(
        "session_changed_event_received",
        previous_session=previous_session,
        new_session=new_session,
        trading_date=trading_date
    )
    
    # Detectar transición MARKET_OPEN → POST_MARKET
    if previous_session == "MARKET_OPEN" and new_session == "POST_MARKET":
        logger.info(
            "detected_transition_to_postmarket",
            trading_date=trading_date
        )
        
        # Trigger captura de volumen regular
        if scanner_engine and trading_date:
            asyncio.create_task(
                scanner_engine.trigger_postmarket_capture(trading_date)
            )
    
    # Freeze ALL scanner categories (built-in + user) when transitioning to CLOSED.
    # During POST_MARKET the scanner still produces fresh data with normal TTL.
    # Once CLOSED, the enriched snapshot expires and no new results are produced.
    # Extend TTL so data persists until maintenance clears scanner:category:*
    # on the next trading day (3:45 AM ET).
    if new_session == "CLOSED" and scanner_engine:
        frozen = await scanner_engine.freeze_user_scans_for_close()
        if frozen > 0:
            logger.info(
                "scans_frozen_on_session_change",
                frozen=frozen,
                transition=f"{previous_session} -> {new_session}"
            )
    
    # Actualizar estado global de sesión
    current_session = new_session


# =============================================
# LIFECYCLE
# =============================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for the service"""
    global redis_client, timescale_client, scanner_engine, event_bus, postmarket_capture
    
    logger.info("Starting Scanner Service")
    
    # Initialize clients
    redis_client = RedisClient()
    await redis_client.connect()
    
    timescale_client = TimescaleClient()
    await timescale_client.connect()
    
    # Initialize HTTP clients with connection pooling (ahora incluye Polygon Aggregates)
    await http_clients.initialize(
        market_session_host=settings.market_session_host,
        market_session_port=settings.market_session_port,
        polygon_api_key=settings.polygon_api_key
    )
    logger.info("http_clients_initialized_with_pooling")
    
    # 🔥 Initialize Redis Stream Manager (auto-trimming)
    stream_manager = initialize_stream_manager(redis_client)
    await stream_manager.start()
    logger.info("✅ RedisStreamManager initialized and started")
    
    # 🔥 Initialize Snapshot Manager (deltas instead of full snapshots)
    snapshot_manager = SnapshotManager(
        redis_client=redis_client,
        full_snapshot_interval=300,  # 5 min
        delta_compression_threshold=100,
        min_price_change_percent=0.001,  # 0.1%
        min_rvol_change_percent=0.05     # 5%
    )
    logger.info("✅ SnapshotManager initialized")
    
    # 🌙 Initialize PostMarket Volume Capture (para post-market volume preciso)
    postmarket_capture = PostMarketVolumeCapture(
        redis_client=redis_client,
        polygon_client=http_clients.polygon_aggregates,
        max_concurrent=50  # Plan avanzado de Polygon permite ~100 req/s
    )
    logger.info("✅ PostMarketVolumeCapture initialized")
    
    # Initialize scanner engine (ahora con postmarket_capture)
    scanner_engine = ScannerEngine(
        redis_client,
        timescale_client,
        snapshot_manager=snapshot_manager,
        postmarket_capture=postmarket_capture
    )
    await scanner_engine.initialize()
    
    # 📅 Verificar estado del mercado UNA VEZ al iniciar
    await check_initial_market_status()
    
    # 🔔 Inicializar EventBus y suscribirse a eventos
    event_bus = EventBus(redis_client, "scanner")
    event_bus.subscribe(EventType.DAY_CHANGED, handle_day_changed)
    event_bus.subscribe(EventType.SESSION_CHANGED, handle_session_changed)
    await event_bus.start_listening()
    logger.info("✅ EventBus initialized - subscribed to DAY_CHANGED, SESSION_CHANGED")
    
    logger.info("Scanner Service started (paused)")
    
    yield
    
    # Cleanup
    logger.info("Shutting down Scanner Service")
    
    for task in background_tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    
    # 🔔 Stop EventBus
    if event_bus:
        await event_bus.stop_listening()
        logger.info("✅ EventBus stopped")
    
    # 🔥 Stop Stream Manager
    stream_manager = get_stream_manager()
    await stream_manager.stop()
    logger.info("✅ RedisStreamManager stopped")
    
    # Close HTTP clients
    await http_clients.close()
    
    if timescale_client:
        await timescale_client.disconnect()
    
    if redis_client:
        await redis_client.disconnect()
    
    logger.info("Scanner Service stopped")


app = FastAPI(
    title="Scanner Service",
    description="Core scanning engine with RVOL calculation and filtering",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================
# BACKGROUND TASKS (Discovery + Hot Loops)
# =============================================

async def discovery_loop():
    """
    DISCOVERY LOOP - Procesa TODO el universo (lento)
    
    - Frecuencia: cada 10 segundos (normal) o 60 segundos (festivo)
    - Procesa: ~11,000 tickers (universo completo)
    - Objetivo: Detectar nuevos líderes que entran a rankings
    """
    global is_running
    
    logger.info("🔍 Starting DISCOVERY loop")
    
    while is_running:
        try:
            # HOLIDAY MODE: Reducir frecuencia en festivos
            if is_holiday_mode:
                logger.debug("holiday_mode_active_reduced_scan_frequency")
                await asyncio.sleep(60)  # Solo cada minuto en festivos
                continue
            
            start = datetime.now()
            
            # Run FULL scan (procesa todos los snapshots)
            result = await scanner_engine.run_scan()
            
            if result:
                duration = (datetime.now() - start).total_seconds()
                logger.info(
                    "🔍 Discovery scan completed",
                    filtered_count=result.filtered_count,
                    total_scanned=result.total_universe_size,
                    duration_sec=round(duration, 2)
                )
            
            # Wait 10 seconds before next discovery
            await asyncio.sleep(10)
        
        except asyncio.CancelledError:
            logger.info("Discovery loop cancelled")
            break
        except Exception as e:
            logger.error("Error in discovery loop", error=str(e))
            await asyncio.sleep(30)

# =============================================
# API ENDPOINTS
# =============================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    db_health = await timescale_client.health_check()
    redis_health = await redis_client.ping()
    
    return {
        "status": "healthy" if (db_health and redis_health) else "degraded",
        "service": "scanner",
        "is_running": is_running,
        "database": "healthy" if db_health else "unhealthy",
        "redis": "healthy" if redis_health else "unhealthy"
    }


@app.post("/api/scanner/start")
async def start_scanner():
    """Start the scanner (discovery + hot loops)"""
    global background_tasks, is_running
    
    if is_running:
        return {"status": "already_running"}
    
    # Re-check market status before starting
    await check_initial_market_status()
    
    is_running = True
    
    # Iniciar discovery loop
    discovery_task = asyncio.create_task(discovery_loop())
    
    background_tasks = [discovery_task]
    
    logger.info("✅ Scanner started (discovery loop)")
    
    return {
        "status": "started",
        "loops": ["discovery (10s)"]
    }


@app.post("/api/scanner/stop")
async def stop_scanner():
    """Stop the scanner"""
    global background_tasks, is_running
    
    if not is_running:
        return {"status": "not_running"}
    
    is_running = False
    
    # Cancelar ambos tasks
    for task in background_tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    
    background_tasks = []
    
    logger.info("Scanner stopped")
    
    return {"status": "stopped"}


@app.get("/api/scanner/status")
async def get_scanner_status():
    """Get scanner status"""
    stats = await scanner_engine.get_stats()
    
    return {
        "is_running": is_running,
        "stats": stats
    }


@app.post("/api/scanner/scan-once")
async def scan_once():
    """Run a single scan (for testing)"""
    try:
        result = await scanner_engine.run_scan()
        
        if not result:
            return {"status": "no_data"}
        
        return {
            "status": "success",
            "result": result.model_dump()
        }
    
    except Exception as e:
        logger.error("Error running scan", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/scanner/freeze-user-scans")
async def freeze_user_scans():
    """Force freeze user scans with extended TTL (for manual use when market is already closed)"""
    try:
        frozen = await scanner_engine.freeze_user_scans_for_close()
        return {"status": "frozen", "count": frozen}
    except Exception as e:
        logger.error("Error freezing user scans", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/scanner/filtered", response_model=List[ScannerTicker])
async def get_filtered_tickers(limit: int = settings.default_query_limit):
    """Get currently filtered tickers"""
    try:
        # Validar límite máximo
        limit = min(limit, settings.max_query_limit)
        tickers = await scanner_engine.get_filtered_tickers(limit=limit)
        return tickers
    
    except Exception as e:
        logger.error("Error getting filtered tickers", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/filters", response_model=List[FilterConfig])
async def get_filters():
    """Get all configured filters"""
    try:
        filters = await scanner_engine.get_filters()
        return filters
    
    except Exception as e:
        logger.error("Error getting filters", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/filters/reload")
async def reload_filters():
    """Reload filters from database"""
    try:
        await scanner_engine.reload_filters()
        filters = await scanner_engine.get_filters()
        
        return {
            "status": "reloaded",
            "count": len(filters)
        }
    
    except Exception as e:
        logger.error("Error reloading filters", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stats")
async def get_detailed_stats():
    """Get detailed scanner statistics"""
    try:
        stats = await scanner_engine.get_stats()
        return stats
    
    except Exception as e:
        logger.error("Error getting stats", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# =============================================
# SCANNER CATEGORIES (NUEVO - Sistema Profesional)
# =============================================

@app.get("/api/categories")
async def get_available_categories():
    """
    Lista todas las categorías de scanners disponibles
    
    Returns:
        Lista de categorías con descripciones
    """
    return {
        "categories": [
            {
                "name": "gappers_up",
                "display_name": "Gap Up",
                "description": "Tickers con gap up ≥ 2% desde cierre anterior"
            },
            {
                "name": "gappers_down",
                "display_name": "Gap Down",
                "description": "Tickers con gap down ≤ -2% desde cierre anterior"
            },
            {
                "name": "momentum_up",
                "display_name": "Momentum Alcista",
                "description": "Momentum fuerte alcista (cambio ≥ 3%)"
            },
            {
                "name": "momentum_down",
                "display_name": "Momentum Bajista",
                "description": "Momentum fuerte bajista (cambio ≤ -3%)"
            },
            {
                "name": "anomalies",
                "display_name": "Anomalías",
                "description": "Patrones inusuales (RVOL ≥ 3.0)"
            },
            {
                "name": "new_highs",
                "display_name": "Nuevos Máximos",
                "description": "Nuevos máximos del día"
            },
            {
                "name": "new_lows",
                "display_name": "Nuevos Mínimos",
                "description": "Nuevos mínimos del día"
            },
            {
                "name": "winners",
                "display_name": "Mayores Ganadores",
                "description": "Top gainers (cambio ≥ 5%)"
            },
            {
                "name": "losers",
                "display_name": "Mayores Perdedores",
                "description": "Top losers (cambio ≤ -5%)"
            },
            {
                "name": "high_volume",
                "display_name": "Alto Volumen",
                "description": "Volumen inusualmente alto (RVOL ≥ 2.0)"
            },
            {
                "name": "reversals",
                "display_name": "Reversals",
                "description": "Cambios de dirección significativos"
            },
            {
                "name": "post_market",
                "display_name": "Post-Market",
                "description": "Activos en post-market (16:00-20:00 ET) con volumen y cambio significativo"
            }
        ]
    }


@app.get("/api/scanner/postmarket/stats")
async def get_postmarket_stats():
    """
    🌙 Obtiene estadísticas del sistema de captura de volumen post-market
    
    Returns:
        Estadísticas de la captura: símbolos capturados, cache hits, errores, etc.
    """
    try:
        if not postmarket_capture:
            return {
                "status": "not_initialized",
                "message": "PostMarketVolumeCapture no está inicializado"
            }
        
        stats = postmarket_capture.get_stats()
        
        return {
            "status": "active",
            "current_session": scanner_engine.current_session.value if scanner_engine else None,
            "stats": stats
        }
    
    except Exception as e:
        logger.error("Error getting postmarket stats", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/scanner/postmarket/capture")
async def trigger_postmarket_capture_manual():
    """
    🌙 Fuerza la captura de volumen regular manualmente
    
    Útil cuando:
    - El scanner se reinicia durante post-market
    - Testing del sistema
    - Recaptura después de un error
    
    Returns:
        Resultado de la captura: símbolos procesados, volúmenes capturados
    """
    try:
        if not scanner_engine:
            raise HTTPException(status_code=500, detail="Scanner engine no inicializado")
        
        # Obtener fecha de trading actual
        trading_date = None
        try:
            status_data = await redis_client.get(f"{settings.key_prefix_market}:session:status")
            if status_data:
                trading_date = status_data.get('trading_date')
        except Exception:
            pass
        
        if not trading_date:
            # Usar fecha actual como fallback
            trading_date = datetime.now().strftime('%Y-%m-%d')
        
        logger.info(
            "🌙 manual_postmarket_capture_triggered",
            trading_date=trading_date
        )
        
        # Trigger la captura
        await scanner_engine.trigger_postmarket_capture(trading_date)
        
        # Retornar stats después de la captura
        stats = postmarket_capture.get_stats() if postmarket_capture else {}
        
        return {
            "status": "capture_completed",
            "trading_date": trading_date,
            "stats": stats
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error in manual postmarket capture", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/categories/{category_name}")
async def get_category_tickers(category_name: str, limit: int = settings.default_category_limit):
    """
    Obtiene tickers de una categoría específica
    
    Args:
        category_name: Nombre de la categoría (gappers_up, momentum_up, etc.)
        limit: Número máximo de resultados
    
    Returns:
        Lista de tickers rankeados para esa categoría
    """
    try:
        # Validar categoría
        try:
            category = ScannerCategory(category_name)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid category: {category_name}. Use /api/categories to see available categories."
            )
        
        # Validar y limitar el límite máximo
        limit = min(limit, settings.max_category_limit)
        
        # Obtener tickers de la categoría
        tickers = await scanner_engine.get_category(category, limit=limit)
        
        return {
            "category": category_name,
            "count": len(tickers),
            "limit": limit,
            "tickers": tickers
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting category tickers", category=category_name, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/categories/stats")
async def get_categories_stats():
    """
    Obtiene estadísticas de TODAS las categorías
    
    Returns:
        Dict con cantidad de tickers en cada categoría
    """
    try:
        stats = await scanner_engine.get_category_stats()
        
        return {
            "timestamp": datetime.now().isoformat(),
            "session": scanner_engine.current_session,
            "categories": stats
        }
    
    except Exception as e:
        logger.error("Error getting categories stats", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/gappers")
async def get_gappers(direction: str = "both", limit: int = settings.default_gappers_limit):
    """
    🔥 ENDPOINT ESPECIALIZADO PARA GAPPERS
    
    Obtiene los mayores gap up/down del mercado
    
    Args:
        direction: 'up', 'down', o 'both'
        limit: Top N resultados
    
    Returns:
        Lista de tickers con mayor gap
    """
    try:
        if direction not in ['up', 'down', 'both']:
            raise HTTPException(status_code=400, detail="direction must be 'up', 'down', or 'both'")
        
        # Validar límite máximo
        limit = min(limit, settings.max_category_limit)
        
        result = {}
        
        if direction in ['up', 'both']:
            gappers_up = await scanner_engine.get_category(ScannerCategory.GAPPERS_UP, limit=limit)
            result['gappers_up'] = {
                "count": len(gappers_up),
                "tickers": gappers_up
            }
        
        if direction in ['down', 'both']:
            gappers_down = await scanner_engine.get_category(ScannerCategory.GAPPERS_DOWN, limit=limit)
            result['gappers_down'] = {
                "count": len(gappers_down),
                "tickers": gappers_down
            }
        
        return result
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting gappers", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# =============================================
# ENTRY POINT
# =============================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.scanner_port,
        reload=settings.debug
    )

