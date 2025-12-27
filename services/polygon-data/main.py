"""
Polygon Data Service

Centralized service for downloading and maintaining Polygon flat files.
Provides minute_aggs and day_aggs data for other services.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import structlog

from config import settings
from downloaders import MinuteAggsDownloader, DayAggsDownloader
from schedulers import DailyUpdateScheduler

# Configure logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer() if settings.debug else structlog.processors.JSONRenderer()
    ],
)

logger = structlog.get_logger(__name__)

# Global instances
minute_downloader: MinuteAggsDownloader = None
day_downloader: DayAggsDownloader = None
scheduler: DailyUpdateScheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan"""
    global minute_downloader, day_downloader, scheduler
    
    logger.info("Starting Polygon Data Service", data_dir=str(settings.data_dir))
    
    # Initialize downloaders
    minute_downloader = MinuteAggsDownloader()
    day_downloader = DayAggsDownloader()
    
    # Initialize and start scheduler
    scheduler = DailyUpdateScheduler()
    scheduler.start()
    
    # Log initial stats
    logger.info("Minute aggs stats", **minute_downloader.get_stats())
    logger.info("Day aggs stats", **day_downloader.get_stats())
    
    yield
    
    # Cleanup
    if scheduler:
        scheduler.stop()
    
    logger.info("Polygon Data Service stopped")


# Create app
app = FastAPI(
    title="Polygon Data Service",
    description="Centralized Polygon flat files management",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Models
# ============================================================================

class DownloadRequest(BaseModel):
    start_date: str  # YYYY-MM-DD
    end_date: Optional[str] = None  # YYYY-MM-DD, defaults to start_date
    data_types: list[str] = ["day_aggs"]  # minute_aggs, day_aggs
    force: bool = False


class StatsResponse(BaseModel):
    minute_aggs: dict
    day_aggs: dict
    scheduler: dict


# ============================================================================
# Endpoints
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check"""
    return {
        "status": "healthy",
        "service": settings.service_name,
        "version": "1.0.0",
    }


@app.get("/stats", response_model=StatsResponse)
async def get_stats():
    """Get download statistics"""
    return {
        "minute_aggs": minute_downloader.get_stats(),
        "day_aggs": day_downloader.get_stats(),
        "scheduler": {
            "next_run": scheduler.get_next_run() if scheduler else None,
        }
    }


@app.post("/download")
async def download_data(request: DownloadRequest, background_tasks: BackgroundTasks):
    """
    Download data for a date range
    
    Runs in background to avoid timeout.
    """
    try:
        start = datetime.strptime(request.start_date, "%Y-%m-%d")
        end = datetime.strptime(request.end_date, "%Y-%m-%d") if request.end_date else start
    except ValueError as e:
        raise HTTPException(400, f"Invalid date format: {e}")
    
    if end < start:
        raise HTTPException(400, "end_date must be >= start_date")
    
    # Queue download in background
    def run_download():
        results = {}
        if "minute_aggs" in request.data_types:
            files = minute_downloader.download_range(start, end, force=request.force)
            results["minute_aggs"] = len(files)
        if "day_aggs" in request.data_types:
            files = day_downloader.download_range(start, end, force=request.force)
            results["day_aggs"] = len(files)
        logger.info("Download complete", **results)
    
    background_tasks.add_task(run_download)
    
    return {
        "status": "queued",
        "start_date": request.start_date,
        "end_date": request.end_date or request.start_date,
        "data_types": request.data_types,
    }


@app.post("/download/last-n-days")
async def download_last_n_days(
    days: int = Query(30, ge=1, le=365),
    data_types: str = Query("day_aggs"),  # comma-separated
    force: bool = False,
    background_tasks: BackgroundTasks = None
):
    """Download the last N days of data"""
    types = [t.strip() for t in data_types.split(",")]
    
    def run_download():
        results = {}
        if "minute_aggs" in types:
            files = minute_downloader.download_last_n_days(days, force=force)
            results["minute_aggs"] = len(files)
        if "day_aggs" in types:
            files = day_downloader.download_last_n_days(days, force=force)
            results["day_aggs"] = len(files)
        logger.info("Download complete", days=days, **results)
    
    background_tasks.add_task(run_download)
    
    return {
        "status": "queued",
        "days": days,
        "data_types": types,
    }


@app.post("/scheduler/run-now")
async def trigger_update():
    """Trigger immediate scheduler update"""
    if scheduler:
        scheduler.run_now()
        return {"status": "triggered"}
    raise HTTPException(503, "Scheduler not running")


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Polygon Data Service",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "stats": "/stats",
            "download": "POST /download",
            "download_last": "POST /download/last-n-days",
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

