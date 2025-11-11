"""
Ticker Metadata Service - Main Entry Point

FastAPI application que expone endpoints REST para metadatos de tickers.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import sys
sys.path.append('/app')

from shared.config.settings import settings
from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import configure_logging, get_logger

from metadata_manager import MetadataManager
from api import metadata_router, company_router, statistics_router

# Configurar logging
configure_logging(service_name="ticker_metadata_service")
logger = get_logger(__name__)

# ============================================================================
# Global State
# ============================================================================

redis_client: Optional[RedisClient] = None
timescale_client: Optional[TimescaleClient] = None
metadata_manager: Optional[MetadataManager] = None


# ============================================================================
# Lifecycle Management
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestión del ciclo de vida de la aplicación"""
    global redis_client, timescale_client, metadata_manager
    
    logger.info("ticker_metadata_service_starting", version="1.0.0")
    
    try:
        # Inicializar Redis
        redis_client = RedisClient(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB
        )
        await redis_client.connect()
        logger.info("redis_connected")
        
        # Inicializar TimescaleDB
        timescale_client = TimescaleClient(
            host=settings.TIMESCALE_HOST,
            port=settings.TIMESCALE_PORT,
            database=settings.TIMESCALE_DB,
            user=settings.TIMESCALE_USER,
            password=settings.TIMESCALE_PASSWORD,
            min_size=2,
            max_size=10
        )
        await timescale_client.connect()
        logger.info("timescale_connected")
        
        # Inicializar Metadata Manager
        metadata_manager = MetadataManager(
            redis_client=redis_client,
            timescale_client=timescale_client,
            polygon_api_key=settings.POLYGON_API_KEY
        )
        logger.info("metadata_manager_initialized")
        
        # Startup completo
        logger.info("ticker_metadata_service_ready", port=8010)
        
        yield
        
    except Exception as e:
        logger.error("startup_failed", error=str(e))
        raise
    
    finally:
        # Cleanup
        logger.info("ticker_metadata_service_shutting_down")
        
        if redis_client:
            await redis_client.close()
            logger.info("redis_disconnected")
        
        if timescale_client:
            await timescale_client.close()
            logger.info("timescale_disconnected")
        
        logger.info("ticker_metadata_service_stopped")


# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="Ticker Metadata Service",
    description="Servicio de gestión de metadatos de compañías y tickers",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Routes
# ============================================================================

# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "ticker-metadata-service",
        "version": "1.0.0",
        "redis": redis_client.is_connected() if redis_client else False,
        "timescale": timescale_client.is_connected() if timescale_client else False
    }


# Include routers
app.include_router(metadata_router.router, prefix="/api/v1/metadata", tags=["Metadata"])
app.include_router(company_router.router, prefix="/api/v1/company", tags=["Company"])
app.include_router(statistics_router.router, prefix="/api/v1/statistics", tags=["Statistics"])


# ============================================================================
# Error Handlers
# ============================================================================

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(
        "unhandled_exception",
        path=request.url.path,
        error=str(exc),
        exc_info=True
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8010,
        reload=False,
        log_config=None  # Usamos structlog
    )

