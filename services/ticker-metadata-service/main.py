"""
Ticker Metadata Service - Main Entry Point
"""

import os
import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import sys
sys.path.append('/app')

from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import configure_logging, get_logger

from metadata_manager import MetadataManager
from api import metadata_router, company_router, statistics_router

configure_logging(service_name="ticker_metadata_service")
logger = get_logger(__name__)

redis_client: Optional[RedisClient] = None
timescale_client: Optional[TimescaleClient] = None
metadata_manager: Optional[MetadataManager] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client, timescale_client, metadata_manager
    
    logger.info("ticker_metadata_service_starting", version="1.0.0")
    
    try:
        redis_client = RedisClient(
            host=os.getenv("REDIS_HOST", "redis"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            db=int(os.getenv("REDIS_DB", "0"))
        )
        await redis_client.connect()
        logger.info("redis_connected")
        
        timescale_client = TimescaleClient(
            host=os.getenv("TIMESCALE_HOST", "timescaledb"),
            port=int(os.getenv("TIMESCALE_PORT", "5432")),
            database=os.getenv("TIMESCALE_DB", "tradeul"),
            user=os.getenv("TIMESCALE_USER", "tradeul_user"),
            password=os.getenv("TIMESCALE_PASSWORD", "tradeul_password_secure_123"),
            min_size=2,
            max_size=10
        )
        await timescale_client.connect()
        logger.info("timescale_connected")
        
        metadata_manager = MetadataManager(
            redis_client=redis_client,
            timescale_client=timescale_client,
            polygon_api_key=os.getenv("POLYGON_API_KEY", "")
        )
        logger.info("metadata_manager_initialized")
        logger.info("ticker_metadata_service_ready", port=8010)
        
        yield
        
    except Exception as e:
        logger.error("startup_failed", error=str(e))
        raise
    
    finally:
        logger.info("ticker_metadata_service_shutting_down")
        
        if redis_client:
            await redis_client.close()
            logger.info("redis_disconnected")
        
        if timescale_client:
            await timescale_client.close()
            logger.info("timescale_disconnected")
        
        logger.info("ticker_metadata_service_stopped")

app = FastAPI(
    title="Ticker Metadata Service",
    description="Servicio de gestión de metadatos de compañías y tickers",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "ticker-metadata-service",
        "version": "1.0.0",
        "redis": redis_client.is_connected() if redis_client else False,
        "timescale": timescale_client.is_connected() if timescale_client else False
    }

app.include_router(metadata_router.router, prefix="/api/v1/metadata", tags=["Metadata"])
app.include_router(company_router.router, prefix="/api/v1/company", tags=["Company"])
app.include_router(statistics_router.router, prefix="/api/v1/statistics", tags=["Statistics"])

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(
        "unhandled_exception",
        path=request.url.path,
        error=str(e),
        exc_info=True
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8010,
        reload=False,
        log_config=None
    )

