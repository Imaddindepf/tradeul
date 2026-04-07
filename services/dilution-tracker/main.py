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
from routers.agent_actions_router import router as agent_actions_router
from routers.ambiguous_review_router import router as ambiguous_review_router
from routers.instrument_context_router import router as instrument_context_router
from routers.websocket_router import router as websocket_router, manager as ws_manager
from routers.extraction_router import router as extraction_router  # Debug only
from routers.debug_router import router as debug_router  # Debug pipeline
from http_clients import http_clients
from services.pipeline.reactive_filing_consumer_v2 import ReactiveFilingConsumerV2
from services.pipeline.reactive_filing_orchestrator_v2 import ReactiveFilingOrchestratorV2
from services.pipeline.bulk_scoring_service import get_bulk_scoring_service

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

    # Reactive SEC filing pipeline v2 — siempre activo en producción
    reactive_consumer = ReactiveFilingConsumerV2()
    await reactive_consumer.start()
    app.state.reactive_consumer = reactive_consumer
    logger.info("reactive_filing_consumer_initialized")

    reactive_orchestrator = ReactiveFilingOrchestratorV2()
    await reactive_orchestrator.start()
    app.state.reactive_orchestrator = reactive_orchestrator
    logger.info("reactive_filing_orchestrator_initialized")

    # Bulk scoring: gradual background scorer for all tickers
    bulk_scorer = get_bulk_scoring_service()
    bulk_scorer.start()
    app.state.bulk_scorer = bulk_scorer
    logger.info("bulk_scoring_service_initialized")
    
    yield
    
    # Shutdown
    logger.info("dilution_tracker_shutting_down")
    
    # Detener listener de Pub/Sub
    await ws_manager.stop_pubsub_listener()

    # Stop reactive consumer if enabled
    reactive_consumer = getattr(app.state, "reactive_consumer", None)
    if reactive_consumer:
        await reactive_consumer.stop()

    # Stop reactive orchestrator if enabled
    reactive_orchestrator = getattr(app.state, "reactive_orchestrator", None)
    if reactive_orchestrator:
        await reactive_orchestrator.stop()
    
    # Stop bulk scorer
    bulk_scorer = getattr(app.state, "bulk_scorer", None)
    if bulk_scorer:
        await bulk_scorer.stop()

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
app.include_router(instrument_context_router)
app.include_router(agent_actions_router)
app.include_router(ambiguous_review_router)
app.include_router(websocket_router)
app.include_router(extraction_router)        # Debug: /api/extraction/{ticker}/...
app.include_router(debug_router)             # Debug: /api/debug/{ticker}/...


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
