"""
Pattern Real-Time Module
========================

Batch scanning, ranking, prediction tracking and verification
for real-time pattern matching across multiple symbols.

Components:
- db: SQLite database for predictions storage
- models: Pydantic schemas for requests/responses
- engine: Batch scanning logic using existing PatternMatcher
- websocket_manager: WebSocket connections management
- verification_worker: Background task for verifying predictions
- router: FastAPI router with HTTP endpoints and WebSocket
"""

from .db import PredictionsDB, get_predictions_db
from .models import (
    RealtimeJobRequest,
    RealtimeJobResponse,
    RealtimeJobStatus,
    PredictionResult,
    VerificationResult,
    PerformanceStats,
    WSMessage,
)
from .websocket_manager import WebSocketManager, ws_manager
from .engine import RealtimeEngine
from .verification_worker import VerificationWorker
from .router import router as realtime_router

__all__ = [
    # Database
    "PredictionsDB",
    "get_predictions_db",
    # Models
    "RealtimeJobRequest",
    "RealtimeJobResponse",
    "RealtimeJobStatus",
    "PredictionResult",
    "VerificationResult",
    "PerformanceStats",
    "WSMessage",
    # WebSocket
    "WebSocketManager",
    "ws_manager",
    # Engine
    "RealtimeEngine",
    # Verification
    "VerificationWorker",
    # Router
    "realtime_router",
]

