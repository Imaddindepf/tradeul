"""
Market Session Service
Detects and manages market session states (PRE_MARKET, MARKET_OPEN, POST_MARKET, CLOSED)
"""

import asyncio
from datetime import datetime, time, date
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx

import sys
sys.path.append('/app')

from shared.config.settings import settings
from shared.models.market import MarketStatus, SessionChangeEvent, TradingDay
from shared.enums.market_session import MarketSession
from shared.utils.redis_client import RedisClient
from shared.utils.logger import get_logger, configure_logging
from shared.events import (
    EventBus,
    create_day_changed_event,
    create_session_changed_event
)

from session_detector import SessionDetector

# Configure logging
configure_logging(service_name="market_session")
logger = get_logger(__name__)


# =============================================
# GLOBALS
# =============================================

redis_client: Optional[RedisClient] = None
session_detector: Optional[SessionDetector] = None
event_bus: Optional[EventBus] = None
background_task: Optional[asyncio.Task] = None


# =============================================
# LIFECYCLE
# =============================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for the service"""
    global redis_client, session_detector, event_bus, background_task
    
    logger.info("Starting Market Session Service")
    
    # Initialize Redis client
    redis_client = RedisClient()
    await redis_client.connect()
    
    # Initialize Event Bus
    event_bus = EventBus(redis_client, "market_session")
    
    # Initialize session detector
    session_detector = SessionDetector(redis_client, event_bus)
    await session_detector.initialize()
    
    # Start background monitoring task
    background_task = asyncio.create_task(monitor_session_changes())
    
    logger.info("Market Session Service started")
    
    yield
    
    # Cleanup
    logger.info("Shutting down Market Session Service")
    
    if background_task:
        background_task.cancel()
        try:
            await background_task
        except asyncio.CancelledError:
            pass
    
    if redis_client:
        await redis_client.disconnect()
    
    logger.info("Market Session Service stopped")


app = FastAPI(
    title="Market Session Service",
    description="Detects and manages market session states",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permitir todos los orígenes para desarrollo
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================
# BACKGROUND TASKS
# =============================================

async def monitor_session_changes():
    """Background task to monitor session changes"""
    logger.info("Starting session monitor")
    
    while True:
        try:
            # Check for session changes every 30 seconds
            await session_detector.check_and_update_session()
            await asyncio.sleep(30)
        
        except asyncio.CancelledError:
            logger.info("Session monitor cancelled")
            break
        except Exception as e:
            logger.error("Error in session monitor", error=str(e))
            await asyncio.sleep(60)  # Wait longer on error


# =============================================
# API ENDPOINTS
# =============================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "market_session"}


@app.get("/api/session/current", response_model=MarketStatus)
async def get_current_session():
    """Get current market session status"""
    try:
        status = await session_detector.get_current_status()
        return status
    except Exception as e:
        logger.error("Error getting current session", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/session/is-trading")
async def is_market_trading():
    """Check if market is currently trading (MARKET_OPEN)"""
    try:
        status = await session_detector.get_current_status()
        return {
            "is_trading": status.current_session == MarketSession.MARKET_OPEN,
            "session": status.current_session,
            "is_trading_day": status.is_trading_day
        }
    except Exception as e:
        logger.error("Error checking trading status", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/session/is-market-active")
async def is_market_active():
    """Check if market is active (any session except CLOSED)"""
    try:
        status = await session_detector.get_current_status()
        is_active = status.current_session != MarketSession.CLOSED
        return {
            "is_active": is_active,
            "session": status.current_session,
            "is_trading_day": status.is_trading_day
        }
    except Exception as e:
        logger.error("Error checking market active", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/holidays")
async def get_market_holidays(days_ahead: int = 30):
    """Get upcoming market holidays"""
    try:
        holidays = await session_detector.get_upcoming_holidays(days_ahead)
        return {"holidays": holidays}
    except Exception as e:
        logger.error("Error getting holidays", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/trading-day")
async def get_trading_day_info(date_str: Optional[str] = None):
    """
    Get trading day information for a specific date
    
    Args:
        date_str: Date in YYYY-MM-DD format (defaults to today)
    """
    try:
        target_date = date.fromisoformat(date_str) if date_str else date.today()
        trading_day = await session_detector.get_trading_day(target_date)
        return trading_day
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    except Exception as e:
        logger.error("Error getting trading day", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/session/force-update")
async def force_session_update():
    """Force an immediate session update (admin only)"""
    try:
        old_session = await session_detector.get_current_status()
        await session_detector.check_and_update_session(force=True)
        new_session = await session_detector.get_current_status()
        
        return {
            "old_session": old_session.current_session,
            "new_session": new_session.current_session,
            "updated": True
        }
    except Exception as e:
        logger.error("Error forcing session update", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stats")
async def get_session_stats():
    """Get service statistics"""
    try:
        stats = await session_detector.get_stats()
        return stats
    except Exception as e:
        logger.error("Error getting stats", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# =============================================
# ENTRY POINT
# =============================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.market_session_port,
        reload=settings.debug
    )

