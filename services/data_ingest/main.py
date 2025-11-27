"""
Data Ingest Service
Consumes snapshots from Polygon API and publishes to Redis streams

IMPORTANTE: En días festivos (Thanksgiving, Christmas, etc.) este servicio
NO sobrescribe el snapshot anterior porque Polygon devuelve datos vacíos.

Usa enfoque event-driven:
- Al iniciar: lee estado de mercado UNA VEZ
- Se suscribe a DAY_CHANGED para actualizar cuando cambie el día
- Si es festivo: mantiene snapshot del último día de trading
"""

import asyncio
from datetime import datetime, date
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
import httpx

import sys
sys.path.append('/app')

from shared.config.settings import settings
from shared.models.polygon import PolygonSnapshot, PolygonSnapshotResponse
from shared.enums.market_session import MarketSession
from shared.utils.redis_client import RedisClient
from shared.utils.logger import get_logger, configure_logging
from shared.utils.redis_stream_manager import (
    initialize_stream_manager,
    get_stream_manager
)
from shared.events import EventBus, EventType, Event

from snapshot_consumer import SnapshotConsumer

# Configure logging
configure_logging(service_name="data_ingest")
logger = get_logger(__name__)


# =============================================
# GLOBALS
# =============================================

redis_client: Optional[RedisClient] = None
snapshot_consumer: Optional[SnapshotConsumer] = None
event_bus: Optional[EventBus] = None
background_task: Optional[asyncio.Task] = None
is_running = False

# Estado de festivo (se actualiza con eventos, no en cada iteración)
is_holiday_mode = False
current_trading_date: Optional[date] = None


# =============================================
# HOLIDAY MODE MANAGEMENT (Event-Driven)
# =============================================

async def check_initial_market_status() -> None:
    """
    Lee el estado del mercado UNA VEZ al iniciar.
    Esto se ejecuta solo al arrancar el servicio.
    """
    global is_holiday_mode, current_trading_date
    
    try:
        # Leer estado completo del mercado desde Redis
        status_data = await redis_client.get(f"{settings.key_prefix_market}:session:status")
        
        if status_data:
            is_holiday = status_data.get('is_holiday', False)
            is_trading_day = status_data.get('is_trading_day', True)
            trading_date_str = status_data.get('trading_date')
            
            # Es festivo si: is_holiday=True O is_trading_day=False (y es día de semana)
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
                    "🚨 HOLIDAY_MODE_ACTIVE - No se sobrescribirá el snapshot",
                    reason="Market is closed for holiday"
                )
        else:
            logger.warning("market_status_not_found_in_redis")
            is_holiday_mode = False
    
    except Exception as e:
        logger.error("error_checking_market_status", error=str(e))
        # En caso de error, asumimos día normal (mejor consumir que no)
        is_holiday_mode = False


async def handle_day_changed(event: Event) -> None:
    """
    Handler para el evento DAY_CHANGED.
    Se ejecuta automáticamente cuando market_session detecta un nuevo día.
    """
    global is_holiday_mode, current_trading_date
    
    new_date_str = event.data.get('new_date')
    logger.info("📆 day_changed_event_received", new_date=new_date_str)
    
    # Re-verificar estado del mercado (ya que cambió el día)
    await check_initial_market_status()


# =============================================
# LIFECYCLE
# =============================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for the service"""
    global redis_client, snapshot_consumer, event_bus, background_task
    
    logger.info("Starting Data Ingest Service")
    
    # Initialize Redis client
    redis_client = RedisClient()
    await redis_client.connect()
    
    # 🔥 Initialize Redis Stream Manager (auto-trimming)
    stream_manager = initialize_stream_manager(redis_client)
    await stream_manager.start()
    logger.info("✅ RedisStreamManager initialized and started")
    
    # Initialize snapshot consumer
    snapshot_consumer = SnapshotConsumer(redis_client)
    
    # 📅 Verificar estado del mercado UNA VEZ al iniciar
    await check_initial_market_status()
    
    # 🔔 Inicializar EventBus y suscribirse a DAY_CHANGED
    event_bus = EventBus(redis_client, "data_ingest")
    event_bus.subscribe(EventType.DAY_CHANGED, handle_day_changed)
    await event_bus.start_listening()
    logger.info("✅ EventBus initialized - subscribed to DAY_CHANGED")
    
    logger.info("Data Ingest Service started (paused)")
    
    yield
    
    # Cleanup
    logger.info("Shutting down Data Ingest Service")
    
    if background_task:
        background_task.cancel()
        try:
            await background_task
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
    
    if redis_client:
        await redis_client.disconnect()
    
    logger.info("Data Ingest Service stopped")


app = FastAPI(
    title="Data Ingest Service",
    description="Consumes snapshots from Polygon API",
    version="1.0.0",
    lifespan=lifespan
)


# =============================================
# BACKGROUND TASKS
# =============================================

async def consume_snapshots_loop():
    """Background task to consume snapshots continuously"""
    global is_running
    
    logger.info("Starting snapshot consumer loop")
    
    while is_running:
        try:
            # 🚨 HOLIDAY MODE: No consumir snapshots en días festivos
            # Polygon devuelve datos vacíos/ceros, sobrescribiría datos buenos
            if is_holiday_mode:
                logger.debug(
                    "holiday_mode_active_skipping_snapshot",
                    trading_date=str(current_trading_date)
                )
                await asyncio.sleep(300)  # Sleep largo, no hay nada que hacer
                continue
            
            # Check if we should be running (based on market session)
            session = await get_current_market_session()
            
            if session and session != MarketSession.CLOSED:
                # Mercado abierto: consume rápido
                await snapshot_consumer.consume_snapshot()
                await asyncio.sleep(settings.snapshot_interval)
            else:
                # Mercado cerrado (fin de semana normal, no festivo):
                # Sigue consumiendo pero menos frecuente
                await snapshot_consumer.consume_snapshot()
                await asyncio.sleep(300)  # Cada 5 minutos
        
        except asyncio.CancelledError:
            logger.info("Snapshot consumer loop cancelled")
            break
        except Exception as e:
            logger.error("Error in snapshot consumer loop", error=str(e))
            await asyncio.sleep(30)  # Wait before retry


async def get_current_market_session() -> Optional[MarketSession]:
    """Get current market session from Redis (optimizado)"""
    try:
        # Leer de Redis directamente (sin HTTP overhead)
        session_str = await redis_client.get(f"{settings.key_prefix_market}:session:current")
        
        if session_str:
            return MarketSession(session_str)
        
        # Fallback: HTTP si no está en Redis
        url = f"{settings.get_service_url('market_session')}/api/session/current"
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url)
            if response.status_code == 200:
                data = response.json()
                return MarketSession(data["current_session"])
    
    except Exception as e:
        logger.error("Error getting market session", error=str(e))
    
    return None


# =============================================
# API ENDPOINTS
# =============================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "data_ingest",
        "is_running": is_running
    }


@app.post("/api/ingest/start")
async def start_ingestion():
    """Start snapshot ingestion"""
    global background_task, is_running
    
    if is_running:
        return {"status": "already_running"}
    
    is_running = True
    background_task = asyncio.create_task(consume_snapshots_loop())
    
    logger.info("Snapshot ingestion started")
    
    return {"status": "started", "interval": settings.snapshot_interval}


@app.post("/api/ingest/stop")
async def stop_ingestion():
    """Stop snapshot ingestion"""
    global background_task, is_running
    
    if not is_running:
        return {"status": "not_running"}
    
    is_running = False
    
    if background_task:
        background_task.cancel()
        try:
            await background_task
        except asyncio.CancelledError:
            pass
    
    logger.info("Snapshot ingestion stopped")
    
    return {"status": "stopped"}


@app.get("/api/ingest/status")
async def get_status():
    """Get ingestion status"""
    stats = await snapshot_consumer.get_stats()
    
    return {
        "is_running": is_running,
        "holiday_mode": is_holiday_mode,
        "trading_date": str(current_trading_date) if current_trading_date else None,
        "stats": stats
    }


@app.post("/api/ingest/refresh-market-status")
async def refresh_market_status():
    """
    Forzar re-verificación del estado del mercado.
    Útil si market_session actualizó el estado y no llegó el evento.
    """
    await check_initial_market_status()
    
    return {
        "status": "refreshed",
        "holiday_mode": is_holiday_mode,
        "trading_date": str(current_trading_date) if current_trading_date else None
    }


@app.post("/api/ingest/fetch-once")
async def fetch_snapshot_once():
    """Fetch a single snapshot (for testing)"""
    try:
        count = await snapshot_consumer.consume_snapshot()
        
        return {
            "status": "success",
            "tickers_processed": count
        }
    
    except Exception as e:
        logger.error("Error fetching snapshot", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stats")
async def get_detailed_stats():
    """Get detailed service statistics"""
    try:
        stats = await snapshot_consumer.get_stats()
        return stats
    except Exception as e:
        logger.error("Error getting stats", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# =============================================
# ENTRY POINT
# =============================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.data_ingest_port,
        reload=settings.debug
    )

