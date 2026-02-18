"""
Benzinga News Service

Real-time news streaming and historical news API
"""

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime, date
from typing import Optional, List

from fastapi import FastAPI, Query as QueryParam, HTTPException
from fastapi.responses import JSONResponse
import structlog
import redis.asyncio as aioredis

from config import settings
from tasks.news_stream_manager import BenzingaNewsStreamManager
from models.news import BenzingaArticle, NewsFilterParams

# Configurar logging para que structlog escriba a stdout
logging.basicConfig(
    format="%(message)s",
    stream=sys.stdout,
    level=logging.INFO,
    force=True  # Forzar reconfiguración
)

# Logger estructurado - configuración simplificada que siempre escribe a stdout
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),  # Usar PrintLogger que escribe directo a stdout
    cache_logger_on_first_use=False,  # No cachear para que tome la nueva config
)

logger = structlog.get_logger(__name__)

# Global instances
redis_client: Optional[aioredis.Redis] = None
stream_manager: Optional[BenzingaNewsStreamManager] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifecycle manager for FastAPI app
    """
    global redis_client, stream_manager
    
    logger.info("🚀 Starting Benzinga News Service...")
    
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
        
        # Test connection
        await redis_client.ping()
        logger.info("✅ Connected to Redis")
        
    except Exception as e:
        logger.error("❌ Failed to connect to Redis", error=str(e))
        raise
    
    # Start stream manager
    try:
        stream_manager = BenzingaNewsStreamManager(
            api_key=settings.polygon_api_key,
            redis_client=redis_client,
            poll_interval=settings.poll_interval_seconds
        )
        
        await stream_manager.start()
        logger.info("✅ Stream manager started")
        
    except Exception as e:
        logger.error("❌ Failed to start stream manager", error=str(e))
        raise
    
    logger.info("🎉 Benzinga News Service ready!")
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down Benzinga News Service...")
    
    if stream_manager:
        await stream_manager.stop()
    
    if redis_client:
        await redis_client.close()
    
    logger.info("✅ Shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Benzinga News Service",
    description="Real-time Benzinga news streaming and API",
    version="1.0.0",
    lifespan=lifespan
)


# =============================================
# HEALTH & STATUS ENDPOINTS
# =============================================

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy", "service": "benzinga-news"}


@app.get("/status")
async def status():
    """Full status with stats"""
    redis_ok = False
    try:
        if redis_client:
            await redis_client.ping()
            redis_ok = True
    except:
        pass
    
    stream_stats = stream_manager.get_stats() if stream_manager else {}
    
    return {
        "status": "ok" if redis_ok and stream_manager else "degraded",
        "redis": "connected" if redis_ok else "disconnected",
        "stream_manager": "running" if stream_manager and stream_manager._running else "stopped",
        "stats": stream_stats,
        "timestamp": datetime.now().isoformat()
    }


@app.get("/stream/status")
async def stream_status():
    """Stream manager status"""
    if not stream_manager:
        return {"status": "not_started"}
    
    return {
        "status": "running" if stream_manager._running else "stopped",
        "stats": stream_manager.get_stats()
    }


# =============================================
# NEWS API ENDPOINTS
# =============================================

@app.get("/api/v1/news")
async def get_news(
    ticker: Optional[str] = QueryParam(None, description="Filter by ticker symbol"),
    channels: Optional[str] = QueryParam(None, description="Filter by channels (comma-separated)"),
    tags: Optional[str] = QueryParam(None, description="Filter by tags"),
    author: Optional[str] = QueryParam(None, description="Filter by author"),
    date_from: Optional[str] = QueryParam(None, description="Start date (YYYY-MM-DD or ISO 8601)"),
    date_to: Optional[str] = QueryParam(None, description="End date (YYYY-MM-DD or ISO 8601)"),
    limit: int = QueryParam(50, ge=1, le=2000, description="Limit results"),
    offset: int = QueryParam(0, ge=0, le=5000, description="Offset for pagination")
):
    """
    Get news articles with optional filters
    
    - **ticker**: Filter by stock ticker (e.g., TSLA, AAPL)
    - **channels**: Filter by news channels/categories
    - **date_from/date_to**: Date range filters
    - **limit**: Maximum articles to return
    - **offset**: Offset for pagination (skip first N results)
    """
    try:
        # Si hay ticker específico, buscar en cache por ticker
        if ticker:
            articles = await stream_manager.get_news_by_ticker(ticker.upper(), limit)
        else:
            # Obtener últimas noticias del cache (con offset para paginación)
            articles = await stream_manager.get_latest_news(limit, offset=offset)
        
        # Aplicar filtros adicionales en memoria si es necesario
        if channels:
            channel_list = [c.strip().lower() for c in channels.split(",")]
            articles = [
                a for a in articles
                if any(c.lower() in channel_list for c in (a.get("channels") or []))
            ]
        
        if tags:
            tag_list = [t.strip().lower() for t in tags.split(",")]
            articles = [
                a for a in articles
                if any(t.lower() in tag_list for t in (a.get("tags") or []))
            ]
        
        if author:
            author_lower = author.lower()
            articles = [
                a for a in articles
                if author_lower in (a.get("author") or "").lower()
            ]
        
        return {
            "status": "OK",
            "count": len(articles),
            "results": articles[:limit]
        }
        
    except Exception as e:
        logger.error("get_news_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/news/latest")
async def get_latest_news(
    limit: int = QueryParam(50, ge=1, le=2000, description="Limit results")
):
    """Get the latest news articles from cache"""
    try:
        articles = await stream_manager.get_latest_news(limit)
        
        return {
            "status": "OK",
            "count": len(articles),
            "results": articles
        }
        
    except Exception as e:
        logger.error("get_latest_news_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/news/ticker/{ticker}")
async def get_news_by_ticker(
    ticker: str,
    limit: int = QueryParam(50, ge=1, le=2000, description="Limit results")
):
    """Get news for a specific ticker"""
    try:
        articles = await stream_manager.get_news_by_ticker(ticker.upper(), limit)
        
        return {
            "status": "OK",
            "ticker": ticker.upper(),
            "count": len(articles),
            "results": articles
        }
        
    except Exception as e:
        logger.error("get_news_by_ticker_error", error=str(e), ticker=ticker)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/news/live")
async def get_news_live(
    ticker: Optional[str] = QueryParam(None, description="Filter by ticker"),
    limit: int = QueryParam(100, ge=1, le=500, description="Limit results")
):
    """
    Get news from Polygon API directly (bypassing cache)
    For fresher results but higher latency
    """
    try:
        if not stream_manager or not stream_manager.news_client:
            raise HTTPException(status_code=503, detail="News client not available")
        
        if ticker:
            articles = await stream_manager.news_client.fetch_news_for_ticker(
                ticker=ticker.upper(),
                limit=limit
            )
        else:
            articles = await stream_manager.news_client.fetch_latest_news(limit=limit)
        
        return {
            "status": "OK",
            "source": "live",
            "count": len(articles),
            "results": [a.model_dump() for a in articles]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_news_live_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/news/fill-cache")
async def fill_cache(
    limit: int = QueryParam(2000, ge=100, le=5000, description="Number of news to fetch (max 5000)")
):
    """
    Fill the news cache with the latest N news from Polygon API.
    
    This is the simplest way to populate the cache after a Redis flush.
    It fetches the latest news sorted by published date and adds them
    to both the latest cache and per-ticker caches.
    
    - **limit**: Number of news articles to fetch (default 2000, max 5000)
    
    Example: POST /api/v1/news/fill-cache?limit=2000
    """
    try:
        if not stream_manager:
            raise HTTPException(status_code=503, detail="Stream manager not available")
        
        logger.info("fill_cache_requested", limit=limit)
        
        # Fetch directly from Polygon
        result = await stream_manager.fill_cache(limit=limit)
        
        return {
            "status": "OK" if result.get("success") else "ERROR",
            "limit_requested": limit,
            **result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("fill_cache_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# =============================================
# MAIN
# =============================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.service_port,
        reload=False,
        log_level=settings.log_level.lower()
    )

