"""
Prediction Markets Service
FastAPI service for aggregating and serving prediction market data
"""

import asyncio
from contextlib import asynccontextmanager
from typing import Optional, List
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query as QueryParam, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import structlog

from config import settings
from clients.polymarket import polymarket_client
from services.classifier import CategoryClassifier
from services.processor import EventProcessor
from services.cache_manager import cache_manager
from services.config_manager import ConfigurationManager
from models.processed import (
    PredictionMarketsResponse,
    EventsListResponse,
    ProcessedEvent,
    SeriesResponse,
    SeriesItem,
    CommentsResponse,
    Comment,
    TopHoldersResponse,
    TopHolder,
    LiveVolume,
    SparklineData,
    EventDetail,
)
from routers.admin import router as admin_router, set_config_manager


# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

logger = structlog.get_logger(__name__)


# Global instances
config_manager: Optional[ConfigurationManager] = None
classifier: Optional[CategoryClassifier] = None
processor: Optional[EventProcessor] = None
background_task: Optional[asyncio.Task] = None
is_refreshing = False


async def refresh_data() -> Optional[PredictionMarketsResponse]:
    """Fetch and process fresh data from Polymarket"""
    global is_refreshing
    
    if is_refreshing:
        logger.warning("refresh_already_running")
        return None
    
    is_refreshing = True
    
    try:
        logger.info("refresh_started")
        
        # Fetch events from Polymarket
        events = await polymarket_client.get_all_events(
            active=True,
            closed=False,
            max_events=settings.max_events_fetch
        )
        
        if not events:
            logger.warning("no_events_fetched")
            return None
        
        # Process and categorize events
        response = await processor.process_events(
            events,
            fetch_price_history=True,
            max_history_markets=settings.max_markets_for_history
        )
        
        # Cache the response
        await cache_manager.set_full_response(response)
        
        logger.info(
            "refresh_completed",
            events=response.total_events,
            markets=response.total_markets,
            categories=len(response.categories)
        )
        
        return response
        
    except Exception as e:
        logger.error("refresh_error", error=str(e))
        return None
    finally:
        is_refreshing = False


async def background_refresh_loop() -> None:
    """Background task to periodically refresh data"""
    while True:
        try:
            await refresh_data()
        except Exception as e:
            logger.error("background_refresh_error", error=str(e))
        
        await asyncio.sleep(settings.refresh_interval_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management"""
    global config_manager, classifier, processor, background_task
    
    logger.info("service_starting", service=settings.service_name)
    
    # Connect to services
    await polymarket_client.connect()
    await cache_manager.connect()
    
    # Initialize configuration manager (connects to database)
    config_manager = ConfigurationManager(
        database_url=settings.database_url,
        cache_ttl_seconds=300,
    )
    await config_manager.connect()
    set_config_manager(config_manager)  # Inject into admin router
    
    # Load configuration and initialize classifier
    loaded_config = await config_manager.get_config()
    classifier = CategoryClassifier.from_loaded_config(loaded_config)
    processor = EventProcessor(polymarket_client, classifier)
    
    logger.info(
        "config_loaded",
        from_db=loaded_config.is_from_db,
        categories=len(loaded_config.categories),
    )
    
    # Initial data fetch
    await refresh_data()
    
    # Start background refresh task
    background_task = asyncio.create_task(background_refresh_loop())
    
    logger.info("service_ready", service=settings.service_name)
    
    yield
    
    # Shutdown
    logger.info("service_stopping", service=settings.service_name)
    
    # Cancel background task
    if background_task:
        background_task.cancel()
        try:
            await background_task
        except asyncio.CancelledError:
            pass
    
    # Disconnect from services
    await config_manager.disconnect()
    await cache_manager.disconnect()
    await polymarket_client.disconnect()
    
    logger.info("service_stopped", service=settings.service_name)


# FastAPI Application
app = FastAPI(
    title="Prediction Markets Service",
    description="Aggregates and serves prediction market data from Polymarket",
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

# Include admin router
app.include_router(admin_router, prefix="/api/v1/predictions")


# =============================================================================
# Health & Status Endpoints
# =============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": settings.service_name}


@app.get("/status")
async def get_status():
    """Get service status and statistics"""
    cache_stats = await cache_manager.get_cache_stats()
    api_health = await polymarket_client.health_check()
    
    return {
        "service": settings.service_name,
        "is_refreshing": is_refreshing,
        "cache": cache_stats,
        "polymarket_api": api_health,
        "config": {
            "refresh_interval_seconds": settings.refresh_interval_seconds,
            "events_cache_ttl": settings.events_cache_ttl,
            "max_events_fetch": settings.max_events_fetch,
        }
    }


# =============================================================================
# Main API Endpoints
# =============================================================================

@app.get("/api/v1/predictions", response_model=PredictionMarketsResponse)
async def get_predictions(
    category: Optional[str] = QueryParam(None, description="Filter by category"),
    refresh: bool = QueryParam(False, description="Force refresh from source"),
):
    """
    Get all prediction markets data, categorized and processed
    
    Returns events organized by category with:
    - Current probabilities
    - Price changes (1D, 5D, 1M)
    - 30-day high/low
    - Volume metrics
    
    Examples:
    - `/api/v1/predictions` - All predictions
    - `/api/v1/predictions?category=Geopolitics` - Filter by category
    - `/api/v1/predictions?refresh=true` - Force refresh
    """
    # Force refresh if requested
    if refresh:
        response = await refresh_data()
        if response:
            if category:
                response.categories = [
                    c for c in response.categories
                    if c.category.lower() == category.lower()
                ]
            return response
    
    # Try cache first
    cached = await cache_manager.get_full_response()
    
    if cached:
        if category:
            category_lower = category.lower()
            cached.categories = [
                c for c in cached.categories
                if category_lower in c.category.lower()
            ]
        return cached
    
    # No cache, fetch fresh
    response = await refresh_data()
    
    if not response:
        raise HTTPException(
            status_code=503,
            detail="Unable to fetch prediction markets data"
        )
    
    if category:
        response.categories = [
            c for c in response.categories
            if c.category.lower() == category.lower()
        ]
    
    return response


@app.get("/api/v1/predictions/events", response_model=EventsListResponse)
async def get_events_list(
    category: Optional[str] = QueryParam(None, description="Filter by category"),
    subcategory: Optional[str] = QueryParam(None, description="Filter by subcategory"),
    min_volume: Optional[float] = QueryParam(None, description="Minimum total volume"),
    page: int = QueryParam(1, ge=1, description="Page number"),
    page_size: int = QueryParam(50, ge=1, le=200, description="Page size"),
):
    """
    Get flat list of prediction events with filtering
    
    Examples:
    - `/api/v1/predictions/events?category=Macro` 
    - `/api/v1/predictions/events?min_volume=100000`
    """
    cached = await cache_manager.get_full_response()
    
    if not cached:
        cached = await refresh_data()
    
    if not cached:
        raise HTTPException(status_code=503, detail="Data unavailable")
    
    # Flatten events from all categories
    all_events: List[ProcessedEvent] = []
    
    for cat_group in cached.categories:
        # Apply category filter (partial match)
        if category and category.lower() not in cat_group.category.lower():
            continue
        
        # Apply subcategory filter
        if subcategory and cat_group.subcategory:
            if cat_group.subcategory.lower() != subcategory.lower():
                continue
        
        all_events.extend(cat_group.events)
    
    # Apply volume filter
    if min_volume:
        all_events = [
            e for e in all_events
            if e.total_volume and e.total_volume >= min_volume
        ]
    
    # Sort by relevance score
    all_events.sort(key=lambda e: e.relevance_score, reverse=True)
    
    # Paginate
    total = len(all_events)
    start = (page - 1) * page_size
    end = start + page_size
    
    return EventsListResponse(
        events=all_events[start:end],
        total=total,
        page=page,
        page_size=page_size,
    )


@app.get("/api/v1/predictions/categories")
async def get_categories():
    """Get list of available categories with event counts"""
    cached = await cache_manager.get_full_response()
    
    if not cached:
        cached = await refresh_data()
    
    if not cached:
        raise HTTPException(status_code=503, detail="Data unavailable")
    
    categories = []
    
    for cat_group in cached.categories:
        categories.append({
            "category": cat_group.category,
            "subcategory": cat_group.subcategory,
            "display_name": cat_group.display_name,
            "event_count": cat_group.total_events,
            "total_volume": cat_group.total_volume,
        })
    
    return {"categories": categories}


@app.get("/api/v1/predictions/event/{event_id}")
async def get_event_by_id(event_id: str):
    """Get single event by ID with full details"""
    cached = await cache_manager.get_full_response()
    
    if not cached:
        cached = await refresh_data()
    
    if not cached:
        raise HTTPException(status_code=503, detail="Data unavailable")
    
    # Search for event
    for cat_group in cached.categories:
        for event in cat_group.events:
            if event.id == event_id:
                return {"event": event}
    
    raise HTTPException(status_code=404, detail=f"Event {event_id} not found")


# =============================================================================
# Discovery Endpoints
# =============================================================================

@app.get("/api/v1/predictions/series", response_model=SeriesResponse)
async def get_series(
    limit: int = QueryParam(30, ge=1, le=100),
    offset: int = QueryParam(0, ge=0),
):
    """
    Get series (grouped related events like "2026 Elections")
    """
    raw_series = await polymarket_client.get_series(limit=limit, offset=offset)
    
    items = []
    for s in raw_series:
        items.append(SeriesItem(
            id=s.get("id", ""),
            title=s.get("title", ""),
            slug=s.get("slug"),
            description=s.get("description"),
            image=s.get("image"),
            event_count=len(s.get("events", [])),
            total_volume=s.get("volume", 0) or 0,
        ))
    
    return SeriesResponse(series=items, total=len(items))


@app.get("/api/v1/predictions/series/{series_id}")
async def get_series_by_id(series_id: str):
    """Get single series with its events"""
    series = await polymarket_client.get_series_by_id(series_id)
    
    if not series:
        raise HTTPException(status_code=404, detail=f"Series {series_id} not found")
    
    return {"series": series}


@app.get("/api/v1/predictions/comments/{event_id}", response_model=CommentsResponse)
async def get_comments(
    event_id: str,
    limit: int = QueryParam(30, ge=1, le=100),
):
    """
    Get comments for an event
    """
    raw_comments = await polymarket_client.get_comments(asset_id=event_id, limit=limit)
    
    comments = []
    for c in raw_comments:
        created_at = None
        if c.get("createdAt"):
            try:
                created_at = datetime.fromisoformat(c["createdAt"].replace("Z", "+00:00"))
            except:
                pass
        
        comments.append(Comment(
            id=c.get("id", ""),
            content=c.get("content", ""),
            author_address=c.get("userAddress"),
            author_name=c.get("userName"),
            created_at=created_at,
            likes=c.get("likes", 0) or 0,
        ))
    
    return CommentsResponse(
        comments=comments,
        total=len(comments),
        asset_id=event_id,
    )


@app.get("/api/v1/predictions/top-holders/{market_id}", response_model=TopHoldersResponse)
async def get_top_holders(
    market_id: str,
    limit: int = QueryParam(10, ge=1, le=50),
):
    """
    Get top holders for a market
    """
    raw_holders = await polymarket_client.get_top_holders(market_id=market_id, limit=limit)
    
    holders = []
    for h in raw_holders:
        holders.append(TopHolder(
            address=h.get("address", ""),
            display_name=h.get("displayName"),
            position_value=h.get("value", 0) or 0,
            shares=h.get("shares", 0) or 0,
            side=h.get("side", "YES"),
        ))
    
    return TopHoldersResponse(market_id=market_id, holders=holders)


@app.get("/api/v1/predictions/volume/{event_id}", response_model=LiveVolume)
async def get_live_volume(event_id: str):
    """
    Get live trading volume for an event
    """
    raw_volume = await polymarket_client.get_live_volume(event_id)
    
    if not raw_volume:
        return LiveVolume(event_id=event_id)
    
    return LiveVolume(
        event_id=event_id,
        volume_24h=raw_volume.get("volume24h", 0) or 0,
        volume_1h=raw_volume.get("volume1h", 0) or 0,
        trades_24h=raw_volume.get("trades24h", 0) or 0,
    )


@app.get("/api/v1/predictions/event/{event_id}/detail", response_model=EventDetail)
async def get_event_detail(event_id: str):
    """
    Get extended event detail with comments and sparklines
    """
    cached = await cache_manager.get_full_response()
    
    if not cached:
        cached = await refresh_data()
    
    if not cached:
        raise HTTPException(status_code=503, detail="Data unavailable")
    
    # Find event
    event = None
    for cat_group in cached.categories:
        for e in cat_group.events:
            if e.id == event_id:
                event = e
                break
        if event:
            break
    
    if not event:
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")
    
    # Fetch comments
    raw_comments = await polymarket_client.get_comments(asset_id=event_id, limit=20)
    comments = []
    for c in raw_comments:
        created_at = None
        if c.get("createdAt"):
            try:
                created_at = datetime.fromisoformat(c["createdAt"].replace("Z", "+00:00"))
            except:
                pass
        comments.append(Comment(
            id=c.get("id", ""),
            content=c.get("content", ""),
            author_address=c.get("userAddress"),
            author_name=c.get("userName"),
            created_at=created_at,
            likes=c.get("likes", 0) or 0,
        ))
    
    # Build sparklines from existing price history
    sparklines = {}
    for market in event.markets:
        if market.clob_token_id:
            history = await polymarket_client.get_price_history(
                market.clob_token_id,
                interval="1w",
                fidelity=60
            )
            if history and history.history:
                prices = [p.p * 100 for p in history.history]
                timestamps = [p.t for p in history.history]
                if prices:
                    sparklines[market.id] = SparklineData(
                        prices=prices,
                        timestamps=timestamps,
                        min_price=min(prices),
                        max_price=max(prices),
                        change_pct=prices[-1] - prices[0] if len(prices) > 1 else 0,
                    )
    
    return EventDetail(
        event=event,
        comments=comments,
        sparklines=sparklines,
        related_events=[],
    )


# =============================================================================
# Admin Endpoints
# =============================================================================

@app.post("/api/v1/predictions/refresh")
async def trigger_refresh(background_tasks: BackgroundTasks):
    """Manually trigger a data refresh"""
    if is_refreshing:
        return {"status": "already_refreshing"}
    
    background_tasks.add_task(refresh_data)
    
    return {
        "status": "refresh_started",
        "message": "Data refresh initiated in background"
    }


@app.post("/api/v1/predictions/cache/invalidate")
async def invalidate_cache():
    """Invalidate all cached data"""
    success = await cache_manager.invalidate_all()
    
    return {
        "status": "success" if success else "error",
        "message": "Cache invalidated" if success else "Failed to invalidate cache"
    }


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.service_port,
        reload=True,
        log_level=settings.log_level.lower()
    )
