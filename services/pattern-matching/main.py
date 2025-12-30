"""
Pattern Matching Service - Main FastAPI Application
Ultra-fast pattern similarity search using FAISS
"""

import os
import asyncio
from datetime import datetime
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import structlog

from config import settings
from pattern_matcher import PatternMatcher, get_matcher
from pattern_indexer import PatternIndexer
from data_processor import DataProcessor
from flat_files_downloader import FlatFilesDownloader
from r2_downloader import ensure_index_files
from cache import pattern_cache

# Configure logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


# ============================================================================
# Pydantic Models
# ============================================================================

class SearchRequest(BaseModel):
    """Request to search for similar patterns"""
    symbol: str = Field(..., description="Ticker symbol")
    prices: Optional[List[float]] = Field(None, description="Price array (optional, fetches real-time if not provided)")
    k: int = Field(default=50, ge=1, le=200, description="Number of neighbors to return")
    cross_asset: bool = Field(default=True, description="Search across all tickers")
    window_minutes: Optional[int] = Field(None, description="Override default window size")


class SearchByPricesRequest(BaseModel):
    """Request to search with raw prices"""
    prices: List[float] = Field(..., min_length=30, description="Price array")
    k: int = Field(default=50, ge=1, le=200, description="Number of neighbors")


class HistoricalSearchRequest(BaseModel):
    """Request to search using historical data"""
    symbol: str = Field(..., description="Ticker symbol")
    date: str = Field(..., description="Date (YYYY-MM-DD)")
    time: str = Field(..., description="Time (HH:MM) in market hours ET")
    k: int = Field(default=50, ge=1, le=200, description="Number of neighbors")
    cross_asset: bool = Field(default=True, description="Search across all tickers")
    window_minutes: int = Field(default=45, ge=15, le=120, description="Pattern window size")


class BuildIndexRequest(BaseModel):
    """Request to build/rebuild index"""
    start_date: str = Field(..., description="Start date (YYYY-MM-DD)")
    end_date: str = Field(..., description="End date (YYYY-MM-DD)")
    symbols_filter: Optional[List[str]] = Field(None, description="Only include these symbols")
    download_first: bool = Field(default=True, description="Download data from Polygon first")


class DownloadRequest(BaseModel):
    """Request to download flat files"""
    start_date: str = Field(..., description="Start date (YYYY-MM-DD)")
    end_date: str = Field(..., description="End date (YYYY-MM-DD)")
    force: bool = Field(default=False, description="Force re-download existing files")


# ============================================================================
# Global State
# ============================================================================

matcher: Optional[PatternMatcher] = None
build_task: Optional[asyncio.Task] = None


# ============================================================================
# Lifecycle
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle manager"""
    global matcher
    
    logger.info("Starting Pattern Matching Service", port=settings.service_port)
    
    # Connect to Redis cache
    cache_connected = await pattern_cache.connect()
    if cache_connected:
        logger.info("Redis cache connected")
    else:
        logger.warning("Redis cache not available - running without cache")
    
    # Download index files from R2 if not present
    logger.info("Checking for index files...")
    files_ready = ensure_index_files()
    
    if files_ready:
        logger.info("Index files ready")
    else:
        logger.warning("Index files not available - will need to build index")
    
    # Initialize matcher
    matcher = PatternMatcher()
    await matcher.initialize()
    
    if matcher.is_ready:
        logger.info("Service ready with loaded index", stats=matcher.get_stats())
    else:
        logger.warning("Service started without index - use /api/index/build to create one")
    
    yield
    
    # Cleanup
    logger.info("Shutting down Pattern Matching Service")
    await pattern_cache.close()
    if matcher:
        await matcher.close()


# ============================================================================
# FastAPI App
# ============================================================================

app = FastAPI(
    title="Pattern Matching Service",
    description="Ultra-fast pattern similarity search for financial time series using FAISS",
    version="1.0.0",
    lifespan=lifespan
)


# ============================================================================
# Health & Status Endpoints
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": settings.service_name,
        "timestamp": datetime.now().isoformat(),
        "index_ready": matcher.is_ready if matcher else False,
    }


@app.get("/stats")
async def get_stats():
    """Get service statistics"""
    if not matcher:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    return matcher.get_stats()


@app.get("/api/cache/stats")
async def get_cache_stats():
    """Get cache statistics (hits, misses, hit rate, memory usage)"""
    return await pattern_cache.get_stats()


@app.delete("/api/cache/invalidate")
async def invalidate_cache(pattern: str = Query(default="pm:hist:*", description="Redis key pattern to invalidate")):
    """
    Invalidate cache entries
    
    Use with caution. Default invalidates all historical search results.
    """
    deleted = await pattern_cache.invalidate_pattern(pattern)
    return {
        "status": "success",
        "pattern": pattern,
        "deleted_entries": deleted
    }


@app.get("/api/index/stats")
async def get_index_stats():
    """Get detailed index statistics"""
    if not matcher or not matcher.indexer:
        raise HTTPException(status_code=503, detail="Index not loaded")
    
    return matcher.indexer.get_stats()


# ============================================================================
# Search Endpoints
# ============================================================================

@app.post("/api/search")
async def search_patterns(request: SearchRequest):
    """
    Search for similar patterns
    
    Either provide prices array or let the service fetch real-time data.
    """
    if not matcher:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    if not matcher.is_ready:
        raise HTTPException(
            status_code=503, 
            detail="Index not loaded. Use /api/index/build to create one."
        )
    
    result = await matcher.search(
        symbol=request.symbol.upper(),
        prices=request.prices,
        k=request.k,
        cross_asset=request.cross_asset,
    )
    
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("error"))
    
    return result


@app.post("/api/search/prices")
async def search_by_prices(request: SearchByPricesRequest):
    """Search for similar patterns using raw prices"""
    if not matcher or not matcher.is_ready:
        raise HTTPException(status_code=503, detail="Index not ready")
    
    result = await matcher.search_with_prices(
        prices=request.prices,
        k=request.k,
    )
    
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("error"))
    
    return result


@app.get("/api/search/{symbol}")
async def search_symbol(
    symbol: str,
    k: int = Query(default=50, ge=1, le=200),
    cross_asset: bool = Query(default=True),
):
    """Quick search for a symbol using real-time prices"""
    if not matcher or not matcher.is_ready:
        raise HTTPException(status_code=503, detail="Index not ready")
    
    result = await matcher.search(
        symbol=symbol.upper(),
        k=k,
        cross_asset=cross_asset,
    )
    
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("error"))
    
    return result


@app.post("/api/search/historical")
async def search_historical(request: HistoricalSearchRequest):
    """
    Search for similar patterns using historical data
    
    Perfect for backtesting or when market is closed.
    Fetches historical minute bars from our downloaded flat files.
    
    Results are cached for 6 hours (historical data doesn't change).
    """
    if not matcher or not matcher.is_ready:
        raise HTTPException(status_code=503, detail="Index not ready")
    
    symbol = request.symbol.upper()
    
    # Check cache first
    cached = await pattern_cache.get_historical(
        symbol=symbol,
        date=request.date,
        time=request.time,
        k=request.k,
        cross_asset=request.cross_asset,
        window_minutes=request.window_minutes,
    )
    
    if cached:
        logger.info("cache_hit_historical", symbol=symbol, date=request.date, time=request.time)
        return cached
    
    # Cache miss - compute result
    result = await matcher.search_historical(
        symbol=symbol,
        date=request.date,
        time=request.time,
        k=request.k,
        cross_asset=request.cross_asset,
        window_minutes=request.window_minutes,
    )
    
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("error"))
    
    # Cache successful result
    await pattern_cache.set_historical(
        symbol=symbol,
        date=request.date,
        time=request.time,
        k=request.k,
        cross_asset=request.cross_asset,
        window_minutes=request.window_minutes,
        result=result,
    )
    
    return result


@app.get("/api/historical/prices/{symbol}")
async def get_historical_prices(
    symbol: str,
    date: str = Query(..., description="Date YYYY-MM-DD"),
    start_time: str = Query(default="09:30", description="Start time HH:MM"),
    end_time: str = Query(default="16:00", description="End time HH:MM"),
):
    """
    Get historical minute-bar prices for a symbol on a specific date
    
    Useful for the frontend to display chart data.
    """
    if not matcher:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    result = await matcher.get_historical_minute_data(
        symbol=symbol.upper(),
        date=date,
        start_time=start_time,
        end_time=end_time,
    )
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return result


# Cache for available dates (changes only once per day)
_dates_cache = {"dates": [], "timestamp": 0}

@app.get("/api/available-dates")
async def get_available_dates(limit: int = Query(60, ge=1, le=2000, description="Number of recent dates to return")):
    """Get list of dates with available historical data (cached, returns recent dates by default)"""
    import time
    from glob import glob
    import os
    
    global _dates_cache
    
    # Cache for 1 hour (dates don't change frequently)
    if time.time() - _dates_cache["timestamp"] > 3600 or not _dates_cache["dates"]:
        data_dir = f"{settings.data_dir}/minute_aggs"
        files = sorted(glob(f"{data_dir}/*.csv.gz"))
        _dates_cache["dates"] = [os.path.basename(f).replace('.csv.gz', '') for f in files]
        _dates_cache["timestamp"] = time.time()
    
    all_dates = _dates_cache["dates"]
    # Return only the last N dates (most recent)
    dates = all_dates[-limit:] if limit < len(all_dates) else all_dates
    
    return {
        "dates": dates,
        "count": len(dates),
        "total_available": len(all_dates),
        "first": all_dates[0] if all_dates else None,
        "last": all_dates[-1] if all_dates else None,
    }


# ============================================================================
# Index Management Endpoints
# ============================================================================

@app.post("/api/index/build")
async def build_index(request: BuildIndexRequest, background_tasks: BackgroundTasks):
    """
    Build or rebuild the FAISS index
    
    This is a long-running operation that runs in the background.
    """
    global build_task
    
    if build_task and not build_task.done():
        raise HTTPException(
            status_code=409,
            detail="Index build already in progress"
        )
    
    async def do_build():
        global matcher
        
        try:
            logger.info(
                "Starting index build",
                start_date=request.start_date,
                end_date=request.end_date
            )
            
            start_time = datetime.now()
            
            # Download data if requested
            if request.download_first:
                logger.info("Downloading flat files")
                downloader = FlatFilesDownloader()
                downloader.download_range(
                    datetime.strptime(request.start_date, "%Y-%m-%d"),
                    datetime.strptime(request.end_date, "%Y-%m-%d"),
                    max_workers=4
                )
            
            # Get list of files
            from glob import glob
            data_dir = f"{settings.data_dir}/minute_aggs"
            files = sorted(glob(f"{data_dir}/*.csv.gz"))
            
            # Filter by date range
            files = [
                f for f in files
                if request.start_date <= os.path.basename(f).replace('.csv.gz', '') <= request.end_date
            ]
            
            if not files:
                logger.error("No data files found")
                return
            
            logger.info(f"Processing {len(files)} files")
            
            # Process data
            processor = DataProcessor()
            vectors, metadata = processor.process_multiple_files(
                files,
                symbols_filter=request.symbols_filter
            )
            
            if len(vectors) == 0:
                logger.error("No patterns extracted")
                return
            
            # Build index
            indexer = PatternIndexer()
            indexer.build_index(vectors, metadata)
            
            # Save index
            indexer.save()
            
            # Reload matcher
            if matcher:
                await matcher.close()
            matcher = PatternMatcher()
            await matcher.initialize()
            
            duration = (datetime.now() - start_time).total_seconds()
            
            logger.info(
                "Index build complete",
                n_patterns=len(vectors),
                duration_minutes=round(duration / 60, 2),
                index_stats=matcher.get_stats()
            )
            
        except Exception as e:
            logger.error("Index build failed", error=str(e))
    
    build_task = asyncio.create_task(do_build())
    
    return {
        "status": "building",
        "message": "Index build started in background",
        "params": {
            "start_date": request.start_date,
            "end_date": request.end_date,
            "download_first": request.download_first,
        }
    }


@app.get("/api/index/build/status")
async def get_build_status():
    """Get current build status"""
    if build_task is None:
        return {"status": "idle", "message": "No build in progress"}
    
    if build_task.done():
        try:
            build_task.result()
            return {"status": "completed", "message": "Build completed successfully"}
        except Exception as e:
            return {"status": "failed", "error": str(e)}
    
    return {"status": "building", "message": "Build in progress"}


@app.post("/api/index/reload")
async def reload_index():
    """Reload index from disk"""
    global matcher
    
    if matcher:
        await matcher.close()
    
    matcher = PatternMatcher()
    success = await matcher.initialize()
    
    if success:
        return {
            "status": "success",
            "message": "Index reloaded",
            "stats": matcher.get_stats()
        }
    else:
        return {
            "status": "failed",
            "message": "No index found on disk"
        }


# ============================================================================
# Data Management Endpoints
# ============================================================================

@app.post("/api/data/download")
async def download_data(request: DownloadRequest, background_tasks: BackgroundTasks):
    """Download flat files from Polygon S3"""
    
    def do_download():
        downloader = FlatFilesDownloader()
        downloader.download_range(
            datetime.strptime(request.start_date, "%Y-%m-%d"),
            datetime.strptime(request.end_date, "%Y-%m-%d"),
            force=request.force
        )
    
    background_tasks.add_task(do_download)
    
    return {
        "status": "downloading",
        "message": "Download started in background",
        "params": {
            "start_date": request.start_date,
            "end_date": request.end_date,
        }
    }


@app.get("/api/data/stats")
async def get_data_stats():
    """Get statistics about downloaded data"""
    downloader = FlatFilesDownloader()
    return downloader.get_download_stats()


class DailyUpdateRequest(BaseModel):
    """Request for daily incremental update"""
    date: Optional[str] = Field(None, description="Specific date (YYYY-MM-DD) or None for auto")


@app.post("/api/data/update-daily")
async def update_daily(request: Optional[DailyUpdateRequest] = None):
    """
    Incremental daily update of the pattern index.
    Called by the data_maintenance service after market close.
    
    Process:
    1. Download new flat files if needed
    2. Extract patterns from new day(s)
    3. Add to existing FAISS index
    4. Update SQLite metadata
    5. Update trajectories file
    """
    global matcher
    
    from daily_updater import DailyUpdater
    
    start_time = datetime.now()
    updater = DailyUpdater()
    
    try:
        if request and request.date:
            # Update specific date
            logger.info("daily_update_started", date=request.date)
            added = updater.update_date(request.date)
            processed_dates = [request.date] if added > 0 else []
        else:
            # Auto update (download new flats and process missing dates)
            logger.info("daily_update_started", mode="auto")
            result = updater.run_daily_update()
            added = result.get("patterns_added", 0)
            processed_dates = result.get("processed_dates", [])
        
        # Reload matcher to use updated index
        if added > 0 and matcher:
            logger.info("reloading_matcher_after_update", patterns_added=added)
            await matcher.close()
            matcher = PatternMatcher()
            await matcher.initialize()
        
        duration = (datetime.now() - start_time).total_seconds()
        
        response = {
            "success": True,
            "patterns_added": added,
            "processed_dates": processed_dates,
            "duration_seconds": round(duration, 2),
            "new_total": matcher.get_stats().get("n_vectors", 0) if matcher else 0
        }
        
        logger.info("daily_update_completed", **response)
        return response
        
    except Exception as e:
        logger.error("daily_update_failed", error=str(e))
        return {
            "success": False,
            "error": str(e),
            "patterns_added": 0
        }


@app.get("/api/index/indexed-dates")
async def get_indexed_dates():
    """Get list of dates already in the index"""
    from daily_updater import DailyUpdater
    
    updater = DailyUpdater()
    indexed = updater.get_indexed_dates()
    
    return {
        "dates": sorted(list(indexed)),
        "count": len(indexed)
    }


# ============================================================================
# Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.service_port,
        reload=settings.debug,
        log_config=None  # Use structlog
    )

