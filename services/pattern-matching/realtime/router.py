"""
Pattern Real-Time - FastAPI Router
==================================

HTTP endpoints and WebSocket for the Pattern Real-Time feature.

Endpoints:
- POST /api/pattern-realtime/run - Start a batch scan job
- GET  /api/pattern-realtime/job/{job_id} - Get job status and results
- GET  /api/pattern-realtime/job/{job_id}/results - Get just results (filtered)
- POST /api/pattern-realtime/job/{job_id}/cancel - Cancel a running job
- GET  /api/pattern-realtime/performance - Get performance statistics
- GET  /api/pattern-realtime/history - Get recent jobs
- WS   /ws/pattern-realtime - WebSocket for real-time updates
"""

import asyncio
from datetime import datetime
from typing import Optional
import uuid

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Query
import structlog

from .models import (
    RealtimeJobRequest,
    RealtimeJobResponse,
    RealtimeJobStatus,
    RealtimeResultsRequest,
    PerformanceStats,
    JobStatus,
    SortBy,
    Direction,
)
from .db import PredictionsDB, get_predictions_db
from .websocket_manager import WebSocketManager, ws_manager
from .engine import RealtimeEngine, ParallelRealtimeEngine
from .verification_worker import VerificationWorker
from .price_tracker import PriceTracker

logger = structlog.get_logger(__name__)

# Router
router = APIRouter(prefix="/api/pattern-realtime", tags=["Pattern Real-Time"])

# Global instances (initialized in setup)
_engine: Optional[RealtimeEngine] = None
_verification_worker: Optional[VerificationWorker] = None
_price_tracker: Optional[PriceTracker] = None


# ============================================================================
# Setup/Teardown
# ============================================================================

async def setup_realtime(matcher, use_parallel: bool = True):
    """
    Initialize the realtime module
    
    Called from main.py during startup.
    
    Args:
        matcher: PatternMatcher instance
        use_parallel: Use parallel scanning engine
    """
    global _engine, _verification_worker, _price_tracker
    
    # Get database
    db = await get_predictions_db()
    
    # Create engine
    if use_parallel:
        _engine = ParallelRealtimeEngine(
            matcher=matcher,
            db=db,
            ws_manager=ws_manager,
            max_concurrent=5
        )
    else:
        _engine = RealtimeEngine(
            matcher=matcher,
            db=db,
            ws_manager=ws_manager
        )
    
    # Create and start verification worker
    _verification_worker = VerificationWorker(
        db=db,
        ws_manager=ws_manager,
        check_interval=60,
        batch_size=50
    )
    await _verification_worker.start()
    
    # Create and start price tracker for real-time P&L updates
    _price_tracker = PriceTracker(
        db=db,
        ws_manager=ws_manager,
        update_interval_ms=500  # Throttle to 2 updates/sec per symbol
    )
    await _price_tracker.start()
    
    logger.info(
        "Realtime module initialized",
        engine_type="parallel" if use_parallel else "sequential",
        price_tracker="enabled"
    )


async def teardown_realtime():
    """
    Cleanup the realtime module
    
    Called from main.py during shutdown.
    """
    global _engine, _verification_worker, _price_tracker
    
    if _price_tracker:
        await _price_tracker.stop()
        _price_tracker = None
    
    if _verification_worker:
        await _verification_worker.stop()
        _verification_worker = None
    
    _engine = None
    
    logger.info("Realtime module cleaned up")


# ============================================================================
# HTTP Endpoints
# ============================================================================

@router.post("/run", response_model=RealtimeJobResponse)
async def run_job(
    request: RealtimeJobRequest,
):
    """
    Start a batch scan job
    
    Scans multiple symbols and returns predictions ranked by edge.
    Results are streamed via WebSocket if subscribed.
    """
    if not _engine:
        raise HTTPException(
            status_code=503,
            detail="Realtime engine not initialized"
        )
    
    job_id = str(uuid.uuid4())
    started_at = datetime.utcnow()
    
    # Run job in background using asyncio.create_task
    async def run_in_background():
        try:
            await _engine.run_job(request, job_id)
        except Exception as e:
            logger.error("Background job failed", job_id=job_id, error=str(e))
    
    # Create task in the current event loop
    asyncio.create_task(run_in_background())
    
    return RealtimeJobResponse(
        job_id=job_id,
        status=JobStatus.RUNNING,
        total_symbols=len(request.symbols),
        started_at=started_at,
        message=f"Job started with {len(request.symbols)} symbols"
    )


@router.get("/job/{job_id}", response_model=RealtimeJobStatus)
async def get_job_status(job_id: str):
    """
    Get full job status including results
    """
    db = await get_predictions_db()
    status = await db.get_job_status(job_id)
    
    if not status:
        raise HTTPException(
            status_code=404,
            detail=f"Job {job_id} not found"
        )
    
    return status


@router.get("/job/{job_id}/results")
async def get_job_results(
    job_id: str,
    sort_by: SortBy = Query(default=SortBy.EDGE),
    direction: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    include_verified: bool = Query(default=True),
    include_pending: bool = Query(default=True)
):
    """
    Get job results with filtering and sorting
    """
    db = await get_predictions_db()
    
    # Verify job exists
    job = await db.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=404,
            detail=f"Job {job_id} not found"
        )
    
    # Parse direction filter
    dir_filter = None
    if direction and direction.upper() in ["UP", "DOWN"]:
        dir_filter = Direction(direction.upper())
    
    # Get predictions
    predictions = await db.get_predictions_for_job(
        job_id=job_id,
        sort_by=sort_by,
        direction=dir_filter,
        limit=limit
    )
    
    # Filter by verification status
    if not include_verified:
        predictions = [p for p in predictions if p.verified_at is None]
    if not include_pending:
        predictions = [p for p in predictions if p.verified_at is not None]
    
    return {
        "job_id": job_id,
        "count": len(predictions),
        "sort_by": sort_by.value,
        "direction_filter": direction,
        "results": [p.model_dump(mode="json") for p in predictions]
    }


@router.post("/job/{job_id}/cancel")
async def cancel_job(job_id: str):
    """
    Cancel a running job
    """
    if not _engine:
        raise HTTPException(
            status_code=503,
            detail="Realtime engine not initialized"
        )
    
    cancelled = _engine.cancel_job(job_id)
    
    if cancelled:
        return {"status": "cancelled", "job_id": job_id}
    else:
        return {"status": "not_found_or_completed", "job_id": job_id}


@router.get("/performance", response_model=PerformanceStats)
async def get_performance(
    period: str = Query(default="today", regex="^(1h|today|week|all)$")
):
    """
    Get performance statistics
    
    Periods:
    - 1h: Last hour
    - today: Since midnight UTC
    - week: Last 7 days
    - all: All time
    """
    db = await get_predictions_db()
    return await db.get_performance_stats(period)


@router.get("/history")
async def get_history(
    limit: int = Query(default=20, ge=1, le=100)
):
    """
    Get recent jobs
    """
    db = await get_predictions_db()
    jobs = await db.get_recent_jobs(limit)
    
    return {
        "count": len(jobs),
        "jobs": jobs
    }


@router.get("/active-jobs")
async def get_active_jobs():
    """
    Get currently active (running) jobs
    """
    if not _engine:
        return {"active_jobs": []}
    
    return {"active_jobs": _engine.get_active_jobs()}


@router.get("/stats")
async def get_stats():
    """
    Get module statistics
    """
    return {
        "websocket": ws_manager.get_stats(),
        "verification_worker": _verification_worker.get_stats() if _verification_worker else None,
        "price_tracker": _price_tracker.get_stats() if _price_tracker else None,
        "engine": {
            "active_jobs": _engine.get_active_jobs() if _engine else []
        }
    }


@router.delete("/cleanup")
async def cleanup_old_data(
    days: int = Query(default=30, ge=1, le=365)
):
    """
    Delete data older than N days
    """
    db = await get_predictions_db()
    deleted = await db.cleanup_old_data(days)
    
    return {
        "status": "success",
        "deleted_predictions": deleted,
        "older_than_days": days
    }


# ============================================================================
# WebSocket Endpoint
# ============================================================================

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket for real-time updates
    
    Connect to receive:
    - Job progress updates
    - Individual scan results
    - Verification results
    
    Send messages:
    - {"type": "subscribe", "job_id": "xxx"} - Subscribe to job updates
    - {"type": "unsubscribe", "job_id": "xxx"} - Unsubscribe from job
    - {"type": "ping"} - Heartbeat (responds with pong)
    """
    await ws_manager.connect(websocket)
    
    try:
        while True:
            # Receive message
            data = await websocket.receive_json()
            
            # Handle message
            await ws_manager.handle_message(websocket, data)
            
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error("WebSocket error", error=str(e))
    finally:
        ws_manager.disconnect(websocket)


# ============================================================================
# Alternative WebSocket at root level (for easier access)
# ============================================================================

# This will be mounted at /ws/pattern-realtime in main.py
ws_router = APIRouter()

@ws_router.websocket("/pattern-realtime")
async def ws_pattern_realtime(websocket: WebSocket):
    """Alternative WebSocket endpoint at /ws/pattern-realtime"""
    await websocket_endpoint(websocket)

