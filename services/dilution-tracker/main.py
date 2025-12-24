"""
Dilution Tracker Service
Análisis de dilución de acciones
"""

import sys
sys.path.append('/app')

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shared.utils.logger import get_logger
from shared.config.settings import settings
from routers import analysis_router, sec_dilution_router, async_analysis_router
from routers.websocket_router import router as websocket_router, manager as ws_manager
from routers.extraction_router import router as extraction_router  # Debug only
from http_clients import http_clients

logger = get_logger(__name__)


# ============================================================================
# Lifecycle Management
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestión del ciclo de vida - inicializa HTTP clients con connection pooling"""
    logger.info("dilution_tracker_starting")
    
    # Inicializar HTTP Clients compartidos
    await http_clients.initialize(
        polygon_api_key=settings.POLYGON_API_KEY,
        fmp_api_key=settings.FMP_API_KEY,
        sec_api_key=getattr(settings, 'SEC_API_IO_KEY', None),
    )
    logger.info("http_clients_initialized_with_pooling")
    
    # Iniciar listener de Pub/Sub para notificaciones de jobs
    await ws_manager.start_pubsub_listener()
    logger.info("pubsub_listener_initialized")
    
    yield
    
    # Shutdown
    logger.info("dilution_tracker_shutting_down")
    
    # Detener listener de Pub/Sub
    await ws_manager.stop_pubsub_listener()
    
    # Cerrar clientes HTTP
    await http_clients.close()
    logger.info("dilution_tracker_stopped")


# Create FastAPI app
app = FastAPI(
    title="Dilution Tracker",
    description="Análisis de dilución de acciones y cash runway",
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

# Include routers
app.include_router(analysis_router)
app.include_router(sec_dilution_router)      # Principal: /api/sec-dilution/{ticker}/profile
app.include_router(async_analysis_router)
app.include_router(websocket_router)
app.include_router(extraction_router)        # Debug: /api/extraction/{ticker}/...


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "dilution-tracker",
        "version": "1.0.0"
    }


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Dilution Tracker API",
        "version": "1.0.0",
        "docs": "/docs"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
