"""
Screener Service - Main Application

High-performance stock screener using DuckDB for analytical queries.
Calculates 60+ technical indicators from Polygon flat files.
"""

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - initialize and cleanup"""
    global engine
    
    logger.info("starting_screener_service", data_path=str(settings.data_path))
    
    # Initialize engine
    engine = ScreenerEngine(settings.data_path)
    set_engine(engine)
    
    stats = engine.get_stats()
    logger.info("screener_engine_ready", **stats)
    
    yield
    
    # Cleanup
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


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
    )

