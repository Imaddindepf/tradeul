"""
Screener Service - Main Application

High-performance stock screener using DuckDB for analytical queries.
Calculates 60+ technical indicators from Polygon flat files.
"""

import asyncio
import glob
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog
import uvicorn

from config import settings
from core.engine import ScreenerEngine
from api.routes import screener_router, indicators_router
from api.routes.screener import set_engine

# Configure logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer() if settings.debug else structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.make_filtering_bound_logger(20),
)

logger = structlog.get_logger(__name__)

# Engine instance
engine: ScreenerEngine = None
refresh_task: asyncio.Task = None


def get_newest_file_date() -> str:
    """Get the newest date from CSV.GZ filenames"""
    data_pattern = settings.data_path / settings.daily_data_pattern
    files = glob.glob(str(data_pattern))
    if not files:
        return None
    # Extract dates from filenames like 2025-12-30.csv.gz
    dates = []
    for f in files:
        try:
            # Get filename without path and extension
            name = f.split('/')[-1].replace('.csv.gz', '')
            dates.append(name)
        except:
            pass
    return max(dates) if dates else None


async def auto_refresh_loop():
    """Background task that checks for new data every hour"""
    global engine
    
    while True:
        try:
            await asyncio.sleep(3600)  # Check every hour
            
            if not engine:
                continue
            
            # Get current loaded date range
            stats = engine.get_stats()
            loaded_to = stats.get("date_range", {}).get("to")
            
            # Get newest available file
            newest_file = get_newest_file_date()
            
            if loaded_to and newest_file and newest_file > loaded_to:
                logger.info("new_data_detected", loaded_to=loaded_to, newest_file=newest_file)
                result = engine.refresh()
                logger.info("auto_refresh_completed", **result)
            else:
                logger.debug("no_new_data", loaded_to=loaded_to, newest_file=newest_file)
                
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("auto_refresh_error", error=str(e))
            await asyncio.sleep(60)  # Wait a bit before retrying


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - initialize and cleanup"""
    global engine, refresh_task
    
    logger.info("starting_screener_service", data_path=str(settings.data_path))
    
    # Initialize engine
    engine = ScreenerEngine(settings.data_path)
    set_engine(engine)
    
    stats = engine.get_stats()
    logger.info("screener_engine_ready", **stats)
    
    # Start auto-refresh background task
    refresh_task = asyncio.create_task(auto_refresh_loop())
    logger.info("auto_refresh_scheduler_started", interval_hours=1)
    
    yield
    
    # Cleanup
    if refresh_task:
        refresh_task.cancel()
        try:
            await refresh_task
        except asyncio.CancelledError:
            pass
    if engine:
        engine.close()
    logger.info("screener_service_stopped")


# Create FastAPI app
app = FastAPI(
    title="Tradeul Screener Service",
    description="High-performance stock screener with 60+ technical indicators",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(screener_router, prefix=settings.api_prefix)
app.include_router(indicators_router, prefix=settings.api_prefix)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    stats = engine.get_stats() if engine else None
    return {
        "status": "healthy",
        "service": settings.service_name,
        "version": "1.0.0",
        "stats": stats,
    }


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Tradeul Screener",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }


@app.post("/refresh")
async def refresh_data():
    """Manually trigger data refresh"""
    if not engine:
        return {"status": "error", "error": "Engine not initialized"}
    
    result = engine.refresh()
    return result


@app.get("/refresh/status")
async def refresh_status():
    """Get refresh status and newest available data"""
    stats = engine.get_stats() if engine else {}
    newest_file = get_newest_file_date()
    loaded_to = stats.get("date_range", {}).get("to")
    
    return {
        "loaded_to": loaded_to,
        "newest_available": newest_file,
        "needs_refresh": newest_file > loaded_to if (newest_file and loaded_to) else False,
        "auto_refresh_interval": "1 hour",
    }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
    )

