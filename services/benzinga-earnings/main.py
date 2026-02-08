"""
Benzinga Earnings Service

Real-time earnings data streaming and API service.

Features:
- Real-time polling of Benzinga Earnings API (every 30s)
- Redis caching for fast queries
- Redis stream for frontend real-time updates
- TimescaleDB persistence for historical data
- REST API for earnings queries
"""

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import FastAPI, Query as QueryParam, HTTPException
from fastapi.responses import JSONResponse
import structlog
import redis.asyncio as aioredis
import asyncpg

from config import settings
from tasks.earnings_stream_manager import EarningsStreamManager

# Configure logging
logging.basicConfig(
    format="%(message)s",
    stream=sys.stdout,
    level=logging.INFO,
    force=True
)

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=False,
)

logger = structlog.get_logger(__name__)

# Global instances
redis_client: Optional[aioredis.Redis] = None
db_pool: Optional[asyncpg.Pool] = None
stream_manager: Optional[EarningsStreamManager] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle manager."""
    global redis_client, db_pool, stream_manager
    
    logger.info("Starting Benzinga Earnings Service...")
    
    # Connect to Redis
    try:
        redis_url = f"redis://{settings.redis_host}:{settings.redis_port}"
        if settings.redis_password:
            redis_url = f"redis://:{settings.redis_password}@{settings.redis_host}:{settings.redis_port}"
        
        redis_client = await aioredis.from_url(
            redis_url,
            encoding="utf-8",
            decode_responses=True
        )
        await redis_client.ping()
        logger.info("Connected to Redis")
        
    except Exception as e:
        logger.error("Failed to connect to Redis", error=str(e))
        raise
    
    # Connect to TimescaleDB
    try:
        db_pool = await asyncpg.create_pool(
            host=settings.timescale_host,
            port=settings.timescale_port,
            user=settings.timescale_user,
            password=settings.timescale_password,
            database=settings.timescale_database,
            min_size=2,
            max_size=10,
            command_timeout=30
        )
        
        # Test connection
        async with db_pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        
        logger.info("Connected to TimescaleDB")
        
    except Exception as e:
        logger.warning("Failed to connect to TimescaleDB (optional)", error=str(e))
        db_pool = None
    
    # Start stream manager
    try:
        stream_manager = EarningsStreamManager(
            api_key=settings.polygon_api_key,
            redis_client=redis_client,
            db_pool=db_pool,
            poll_interval=settings.poll_interval_seconds,
            full_sync_interval=settings.full_sync_interval_minutes * 60
        )
        
        await stream_manager.start()
        logger.info("Stream manager started")
        
    except Exception as e:
        logger.error("Failed to start stream manager", error=str(e))
        raise
    
    logger.info("Benzinga Earnings Service ready!")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Benzinga Earnings Service...")
    
    if stream_manager:
        await stream_manager.stop()
    
    if db_pool:
        await db_pool.close()
    
    if redis_client:
        await redis_client.close()
    
    logger.info("Shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Benzinga Earnings Service",
    description="Real-time earnings data streaming and API",
    version="1.0.0",
    lifespan=lifespan
)


# =============================================================================
# HEALTH & STATUS
# =============================================================================

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "service": "benzinga-earnings"}


@app.get("/status")
async def status():
    """Detailed status with statistics."""
    redis_ok = False
    db_ok = False
    
    try:
        if redis_client:
            await redis_client.ping()
            redis_ok = True
    except:
        pass
    
    try:
        if db_pool:
            async with db_pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            db_ok = True
    except:
        pass
    
    manager_stats = stream_manager.get_stats() if stream_manager else {}
    
    return {
        "status": "ok" if redis_ok and stream_manager else "degraded",
        "redis": "connected" if redis_ok else "disconnected",
        "database": "connected" if db_ok else "disconnected",
        "stream_manager": "running" if stream_manager and stream_manager._running else "stopped",
        "stats": manager_stats,
        "config": {
            "poll_interval_seconds": settings.poll_interval_seconds,
            "full_sync_interval_minutes": settings.full_sync_interval_minutes
        },
        "timestamp": datetime.now().isoformat()
    }


# =============================================================================
# EARNINGS API
# =============================================================================

@app.get("/api/v1/earnings/today")
async def get_today_earnings():
    """
    Get today's earnings announcements.
    
    Returns earnings scheduled for today, sorted by importance and time.
    """
    try:
        if not stream_manager:
            raise HTTPException(status_code=503, detail="Service not ready")
        
        earnings = await stream_manager.get_today_earnings()
        
        # Sort by importance (desc) then by time
        def sort_key(e):
            importance = e.get("importance") or 0
            time_order = {"BMO": 0, "DURING": 1, "AMC": 2, "TBD": 3}
            time_slot = e.get("time_slot", "TBD")
            return (-importance, time_order.get(time_slot, 3))
        
        earnings.sort(key=sort_key)
        
        # Calculate stats
        total = len(earnings)
        bmo = sum(1 for e in earnings if e.get("time_slot") == "BMO")
        amc = sum(1 for e in earnings if e.get("time_slot") == "AMC")
        reported = sum(1 for e in earnings if e.get("actual_eps") is not None)
        
        return {
            "status": "OK",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "count": total,
            "stats": {
                "total": total,
                "bmo": bmo,
                "amc": amc,
                "reported": reported,
                "scheduled": total - reported
            },
            "results": earnings
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_today_earnings_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/earnings/upcoming")
async def get_upcoming_earnings(
    days: int = QueryParam(7, ge=1, le=30, description="Days to look ahead"),
    min_importance: Optional[int] = QueryParam(None, ge=0, le=5, description="Minimum importance"),
    limit: int = QueryParam(200, ge=1, le=1000, description="Max results")
):
    """
    Get upcoming earnings for the next N days.
    
    - **days**: Number of days ahead to fetch (default 7)
    - **min_importance**: Filter by minimum importance (0-5)
    - **limit**: Maximum results to return
    """
    try:
        if not stream_manager:
            raise HTTPException(status_code=503, detail="Service not ready")
        
        earnings = await stream_manager.get_upcoming_earnings(limit=limit)
        
        # Filter by importance if specified
        if min_importance is not None:
            earnings = [
                e for e in earnings 
                if (e.get("importance") or 0) >= min_importance
            ]
        
        # Filter by date range
        today = datetime.now()
        end_date = today + timedelta(days=days)
        end_str = end_date.strftime("%Y-%m-%d")
        
        earnings = [
            e for e in earnings
            if e.get("date", "") <= end_str
        ]
        
        # Group by date
        by_date = {}
        for e in earnings:
            date = e.get("date", "unknown")
            if date not in by_date:
                by_date[date] = 0
            by_date[date] += 1
        
        return {
            "status": "OK",
            "start_date": today.strftime("%Y-%m-%d"),
            "end_date": end_str,
            "count": len(earnings),
            "by_date": by_date,
            "results": earnings[:limit]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_upcoming_earnings_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/earnings/date/{date}")
async def get_earnings_by_date(
    date: str,
    min_importance: Optional[int] = QueryParam(None, ge=0, le=5),
    time_slot: Optional[str] = QueryParam(None, description="BMO, AMC, or DURING"),
    limit: int = QueryParam(200, ge=1, le=500)
):
    """
    Get earnings for a specific date.
    
    - **date**: Date in YYYY-MM-DD format
    - **min_importance**: Filter by minimum importance
    - **time_slot**: Filter by time slot (BMO, AMC, DURING)
    """
    try:
        if not stream_manager:
            raise HTTPException(status_code=503, detail="Service not ready")
        
        earnings = await stream_manager.get_earnings_by_date(date, limit=limit)
        
        # Apply filters
        if min_importance is not None:
            earnings = [
                e for e in earnings 
                if (e.get("importance") or 0) >= min_importance
            ]
        
        if time_slot:
            earnings = [
                e for e in earnings
                if e.get("time_slot", "").upper() == time_slot.upper()
            ]
        
        # Calculate stats
        total = len(earnings)
        bmo = sum(1 for e in earnings if e.get("time_slot") == "BMO")
        amc = sum(1 for e in earnings if e.get("time_slot") == "AMC")
        reported = sum(1 for e in earnings if e.get("actual_eps") is not None)
        
        return {
            "status": "OK",
            "date": date,
            "count": total,
            "stats": {
                "total": total,
                "bmo": bmo,
                "amc": amc,
                "reported": reported,
                "scheduled": total - reported
            },
            "results": earnings
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_earnings_by_date_error", error=str(e), date=date)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/earnings/ticker/{ticker}")
async def get_earnings_by_ticker(
    ticker: str,
    limit: int = QueryParam(20, ge=1, le=100)
):
    """
    Get earnings history for a specific ticker.
    
    - **ticker**: Stock ticker symbol
    - **limit**: Maximum results (default 20)
    """
    try:
        if not stream_manager:
            raise HTTPException(status_code=503, detail="Service not ready")
        
        earnings = await stream_manager.get_earnings_by_ticker(ticker, limit=limit)
        
        # Calculate beat stats
        reported = [e for e in earnings if e.get("actual_eps") is not None]
        beats = sum(1 for e in reported if e.get("beat_eps") is True)
        misses = sum(1 for e in reported if e.get("beat_eps") is False)
        
        beat_rate = None
        if reported:
            beat_rate = round((beats / len(reported)) * 100, 1)
        
        return {
            "status": "OK",
            "ticker": ticker.upper(),
            "count": len(earnings),
            "stats": {
                "total_reported": len(reported),
                "beats": beats,
                "misses": misses,
                "beat_rate": beat_rate
            },
            "results": earnings
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_earnings_by_ticker_error", error=str(e), ticker=ticker)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/earnings/sync")
async def trigger_sync():
    """
    Manually trigger a full sync.
    
    This is useful after a service restart or to force refresh data.
    """
    try:
        if not stream_manager:
            raise HTTPException(status_code=503, detail="Service not ready")
        
        logger.info("Manual sync triggered")
        await stream_manager._full_sync()
        
        return {
            "status": "OK",
            "message": "Full sync completed",
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("trigger_sync_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# STREAM INFO
# =============================================================================

@app.get("/api/v1/stream/info")
async def get_stream_info():
    """
    Get information about the Redis stream for frontend subscription.
    """
    stream_key = EarningsStreamManager.STREAM_KEY
    
    try:
        # Get stream info
        info = await redis_client.xinfo_stream(stream_key)
        
        return {
            "status": "OK",
            "stream_key": stream_key,
            "length": info.get("length", 0),
            "first_entry": info.get("first-entry"),
            "last_entry": info.get("last-entry"),
            "subscribe_url": f"/ws/earnings"
        }
    except Exception as e:
        return {
            "status": "OK",
            "stream_key": stream_key,
            "length": 0,
            "error": str(e)
        }


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.service_port,
        reload=False,
        log_level=settings.log_level.lower()
    )
