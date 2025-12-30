"""
Pattern Real-Time - Pydantic Models
====================================

Request/Response schemas for the realtime pattern scanning API.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any, Literal
from enum import Enum
from pydantic import BaseModel, Field
import uuid


# ============================================================================
# Enums
# ============================================================================

class JobStatus(str, Enum):
    """Job execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Direction(str, Enum):
    """Predicted price direction"""
    UP = "UP"
    DOWN = "DOWN"


class SortBy(str, Enum):
    """Sort options for results"""
    EDGE = "edge"
    PROB_UP = "prob_up"
    MEAN_RETURN = "mean_return"
    SYMBOL = "symbol"


# ============================================================================
# Request Models
# ============================================================================

class RealtimeJobRequest(BaseModel):
    """Request to start a batch scan job"""
    
    symbols: List[str] = Field(
        ..., 
        min_length=1, 
        max_length=500,
        description="List of ticker symbols to scan"
    )
    k: int = Field(
        default=40, 
        ge=10, 
        le=200,
        description="Number of neighbors to search"
    )
    horizon: int = Field(
        default=10, 
        ge=5, 
        le=60,
        description="Forecast horizon in minutes"
    )
    alpha: float = Field(
        default=6.0, 
        ge=1.0, 
        le=20.0,
        description="Softmax temperature for neighbor weighting"
    )
    trim_lo: float = Field(
        default=0.0, 
        ge=0.0, 
        le=10.0,
        description="Lower percentile to trim from results"
    )
    trim_hi: float = Field(
        default=0.0, 
        ge=0.0, 
        le=10.0,
        description="Upper percentile to trim from results"
    )
    exclude_self: bool = Field(
        default=True,
        description="Exclude same-ticker patterns from neighbors"
    )
    min_edge: float = Field(
        default=0.0, 
        ge=0.0,
        description="Minimum edge threshold to include in results"
    )
    cross_asset: bool = Field(
        default=True,
        description="Search across all tickers (not just same ticker)"
    )


class RealtimeResultsRequest(BaseModel):
    """Request for filtering/sorting results"""
    
    sort_by: SortBy = Field(default=SortBy.EDGE)
    direction: Optional[Direction] = Field(default=None)
    limit: int = Field(default=50, ge=1, le=500)
    include_verified: bool = Field(default=True)
    include_pending: bool = Field(default=True)


# ============================================================================
# Response Models
# ============================================================================

class PredictionResult(BaseModel):
    """Single prediction result from batch scan"""
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    job_id: str
    symbol: str
    scan_time: datetime
    horizon: int
    
    # Prediction metrics
    prob_up: float
    prob_down: float
    mean_return: float
    edge: float  # prob_favorable * mean_return
    direction: Direction
    n_neighbors: int
    dist1: Optional[float] = None  # Distance to closest neighbor
    p10: Optional[float] = None    # 10th percentile return
    p90: Optional[float] = None    # 90th percentile return
    
    # Price at scan time
    price_at_scan: float
    
    # Verification (null until horizon passes)
    price_at_horizon: Optional[float] = None
    actual_return: Optional[float] = None
    was_correct: Optional[bool] = None
    pnl: Optional[float] = None
    verified_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class FailureResult(BaseModel):
    """Failure during batch scan"""
    
    symbol: str
    scan_time: datetime
    error_code: str
    reason: str
    bars_since_open: Optional[int] = None
    bars_until_close: Optional[int] = None


class RealtimeJobResponse(BaseModel):
    """Response for job creation"""
    
    job_id: str
    status: JobStatus
    total_symbols: int
    started_at: datetime
    message: str = "Job started successfully"


class RealtimeJobStatus(BaseModel):
    """Full job status with results"""
    
    job_id: str
    status: JobStatus
    progress: Dict[str, int]  # {"completed": N, "total": M, "failed": F}
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    
    # Results
    results: List[PredictionResult] = []
    failures: List[FailureResult] = []
    
    # Parameters used
    params: Dict[str, Any] = {}


class VerificationResult(BaseModel):
    """Result of verifying a prediction"""
    
    prediction_id: str
    symbol: str
    actual_return: float
    was_correct: bool
    pnl: float
    verified_at: datetime


class BucketStats(BaseModel):
    """Statistics for a performance bucket"""
    
    n: int
    long_count: int
    short_count: int
    win_rate: Optional[float] = None
    mean_pnl: Optional[float] = None
    median_pnl: Optional[float] = None


class PerformanceStats(BaseModel):
    """Performance statistics across predictions"""
    
    period: str  # "1h", "today", "week", "all"
    total_predictions: int
    verified: int
    pending: int
    
    # By bucket
    all_stats: Optional[BucketStats] = None
    top_1pct: Optional[BucketStats] = None
    top_5pct: Optional[BucketStats] = None
    top_10pct: Optional[BucketStats] = None
    
    # By direction
    long_stats: Optional[BucketStats] = None
    short_stats: Optional[BucketStats] = None


# ============================================================================
# WebSocket Models
# ============================================================================

class WSMessageType(str, Enum):
    """WebSocket message types"""
    
    # Client → Server
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"
    PING = "ping"
    
    # Server → Client
    PROGRESS = "progress"
    RESULT = "result"
    VERIFICATION = "verification"
    JOB_COMPLETE = "job_complete"
    ERROR = "error"
    PONG = "pong"


class WSMessage(BaseModel):
    """WebSocket message envelope"""
    
    type: WSMessageType
    job_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class WSSubscribeMessage(BaseModel):
    """Client subscription message"""
    type: Literal["subscribe"] = "subscribe"
    job_id: str


class WSProgressMessage(BaseModel):
    """Progress update message"""
    type: Literal["progress"] = "progress"
    job_id: str
    completed: int
    total: int
    failed: int


class WSResultMessage(BaseModel):
    """Individual result message"""
    type: Literal["result"] = "result"
    job_id: str
    data: PredictionResult


class WSVerificationMessage(BaseModel):
    """Verification result message"""
    type: Literal["verification"] = "verification"
    data: VerificationResult


class WSJobCompleteMessage(BaseModel):
    """Job completion message"""
    type: Literal["job_complete"] = "job_complete"
    job_id: str
    total_results: int
    total_failures: int
    duration_seconds: float


# ============================================================================
# Error Codes
# ============================================================================

class ErrorCode:
    """Error codes for failures"""
    
    E_WEEKEND = "E_WEEKEND"              # Saturday/Sunday
    E_MARKET_CLOSED = "E_MARKET_CLOSED"  # Outside 09:30-16:00 ET
    E_NO_DATA = "E_NO_DATA"              # No minute data for ticker
    E_WINDOW = "E_WINDOW"                # Can't form contiguous window
    E_FAISS = "E_FAISS"                  # FAISS search error
    E_PRICE = "E_PRICE"                  # Price fetch error
    E_UNKNOWN = "E_UNKNOWN"              # Unknown error
    
    @classmethod
    def describe(cls, code: str) -> str:
        """Get human-readable description"""
        descriptions = {
            cls.E_WEEKEND: "Saturday/Sunday - market closed",
            cls.E_MARKET_CLOSED: "Outside market hours 09:30-16:00 ET",
            cls.E_NO_DATA: "No minute data available for ticker",
            cls.E_WINDOW: "Could not form contiguous 30-bar window",
            cls.E_FAISS: "Error searching FAISS index",
            cls.E_PRICE: "Error fetching current price",
            cls.E_UNKNOWN: "Unknown error occurred",
        }
        return descriptions.get(code, "Unknown error")

