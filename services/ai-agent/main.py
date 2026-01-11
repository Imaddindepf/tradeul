"""
AI Agent Service v3
===================
Clean architecture with Function Calling.

Key improvements:
- Single LLM call with native tool selection
- Separated handlers (WebSocket, REST)
- Cleaner, more maintainable code (~200 lines vs ~600)
"""

import asyncio
import os
from datetime import datetime
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import pytz
import structlog

# Local imports
import sys
sys.path.insert(0, '/app')

from shared.config.settings import settings
from shared.utils.redis_client import RedisClient
from shared.utils.logger import configure_logging, get_logger
from shared.events import EventBus, EventType, Event

from agent import MarketAgent
from handlers import WebSocketHandler, create_rest_routes

# Configure logging
configure_logging(service_name="ai_agent")
logger = get_logger(__name__)

ET = pytz.timezone('America/New_York')


# =============================================================================
# GLOBAL STATE
# =============================================================================

redis_client: Optional[RedisClient] = None
agent: Optional[MarketAgent] = None
ws_handler: Optional[WebSocketHandler] = None
event_bus: Optional[EventBus] = None
rest_router = None

market_context: Dict[str, Any] = {
    "session": "UNKNOWN",
    "time_et": "",
}


# =============================================================================
# MARKET SESSION
# =============================================================================

def get_market_session() -> str:
    """Determine current market session."""
    now = datetime.now(ET)
    hour, minute = now.hour, now.minute
    time_mins = hour * 60 + minute
    
    if time_mins < 240:      # Before 4am
        return "CLOSED"
    elif time_mins < 570:    # 4am - 9:30am
        return "PREMARKET"
    elif time_mins < 960:    # 9:30am - 4pm
        return "REGULAR"
    elif time_mins < 1200:   # 4pm - 8pm
        return "POSTMARKET"
    else:
        return "CLOSED"


async def update_market_context():
    """Update market context periodically."""
    global market_context
    now = datetime.now(ET)
    market_context["time_et"] = now.strftime("%H:%M:%S")
    market_context["session"] = get_market_session()


async def market_context_updater():
    """Background task to update market context."""
    while True:
        try:
            await update_market_context()
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            break
        except:
            await asyncio.sleep(60)


# =============================================================================
# EVENT HANDLERS
# =============================================================================

async def handle_session_changed(event: Event):
    """Handle market session change events."""
    global market_context
    market_context["session"] = event.data.get("new_session", "UNKNOWN")
    
    if ws_handler:
        await ws_handler.broadcast({
            "type": "market_update",
            "session": market_context["session"],
            "timestamp": datetime.now().isoformat()
        })


# =============================================================================
# APP LIFECYCLE
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management."""
    global redis_client, agent, ws_handler, event_bus, rest_router
    
    logger.info("ai_agent_v3_starting")
    
    # Redis
    redis_client = RedisClient()
    await redis_client.connect()
    logger.info("redis_connected")
    
    # Agent
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY required")
    
    agent = MarketAgent(api_key=api_key)
    logger.info("agent_initialized")
    
    # WebSocket handler
    ws_handler = WebSocketHandler(agent, redis_client)
    
    # Register REST routes
    rest_router = create_rest_routes(agent, market_context, ws_handler.chart_cache)
    app.include_router(rest_router)
    logger.info("rest_routes_registered")
    
    # Event bus
    event_bus = EventBus(redis_client, "ai_agent")
    event_bus.subscribe(EventType.SESSION_CHANGED, handle_session_changed)
    await event_bus.start_listening()
    
    # Background tasks
    await update_market_context()
    bg_task = asyncio.create_task(market_context_updater())
    
    logger.info("ai_agent_v3_started", version="3.0")
    
    yield
    
    # Shutdown
    logger.info("ai_agent_stopping")
    bg_task.cancel()
    try:
        await bg_task
    except asyncio.CancelledError:
        pass
    
    await event_bus.stop_listening()
    await redis_client.disconnect()
    logger.info("ai_agent_stopped")


# =============================================================================
# APP SETUP
# =============================================================================

app = FastAPI(
    title="AI Agent Service",
    description="Financial market analysis AI with Function Calling",
    version="3.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# ROUTES
# =============================================================================

# WebSocket endpoint (defined statically, doesn't need dynamic initialization)
@app.websocket("/ws/chat/{client_id}")
async def websocket_chat(websocket: WebSocket, client_id: str):
    """WebSocket chat endpoint."""
    if not ws_handler:
        await websocket.close(code=1011, reason="Service not ready")
        return
    
    await ws_handler.connect(websocket, client_id, market_context)
    
    try:
        while True:
            data = await websocket.receive_json()
            await ws_handler.handle_message(websocket, client_id, data, market_context)
    
    except WebSocketDisconnect:
        ws_handler.disconnect(client_id)
    except Exception as e:
        logger.error("websocket_error", client_id=client_id, error=str(e))
        ws_handler.disconnect(client_id)


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8030, reload=True)
