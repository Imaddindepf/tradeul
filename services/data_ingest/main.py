"""
Data Ingest Service
Consumes snapshots from Polygon API and publishes to Redis streams
"""

import asyncio
from datetime import datetime
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

from snapshot_consumer import SnapshotConsumer

# Configure logging
configure_logging(service_name="data_ingest")
logger = get_logger(__name__)


# =============================================
# GLOBALS
# =============================================

redis_client: Optional[RedisClient] = None
snapshot_consumer: Optional[SnapshotConsumer] = None
background_task: Optional[asyncio.Task] = None
is_running = False


# =============================================
# LIFECYCLE
# =============================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for the service"""
    global redis_client, snapshot_consumer, background_task
    
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
            # Check if we should be running (based on market session)
            session = await get_current_market_session()
            
            if session and session != MarketSession.CLOSED:
                # Mercado abierto: consume rápido
                await snapshot_consumer.consume_snapshot()
                await asyncio.sleep(settings.snapshot_interval)
            else:
                # Mercado cerrado: sigue consumiendo último snapshot pero menos frecuente
                # Útil para análisis de fin de semana
                await snapshot_consumer.consume_snapshot()
                await asyncio.sleep(300)  # Cada 5 minutos en lugar de 1 segundo
        
        except asyncio.CancelledError:
            logger.info("Snapshot consumer loop cancelled")
            break
        except Exception as e:
            logger.error("Error in snapshot consumer loop", error=str(e))
            await asyncio.sleep(30)  # Wait before retry


async def get_current_market_session() -> Optional[MarketSession]:
    """Get current market session from Market Session Service"""
    try:
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
        "stats": stats
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

