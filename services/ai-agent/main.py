"""
AI Agent Service
================
WebSocket-based conversational AI for financial market analysis.

Architecture (v2 - Sandbox):
- LLM generates Python code for analysis
- Code executes in isolated Docker sandbox
- Orchestrator coordinates: data fetching → code generation → execution
"""

import asyncio
import os
import uuid
import base64
from datetime import datetime
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager

import pandas as pd
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
import structlog
import pytz

import sys
sys.path.append('/app')

from shared.config.settings import settings
from shared.utils.redis_client import RedisClient
from shared.utils.logger import configure_logging, get_logger
from shared.events import EventBus, EventType, Event

from llm.gemini_client import GeminiClient
from orchestrator.request_handler import RequestHandler, AnalysisRequest

# Configure logging
configure_logging(service_name="ai_agent")
logger = get_logger(__name__)


# ============================================================================
# Global State
# ============================================================================

redis_client: Optional[RedisClient] = None
gemini_client: Optional[GeminiClient] = None
request_handler: Optional[RequestHandler] = None
event_bus: Optional[EventBus] = None

active_connections: Dict[str, WebSocket] = {}

market_context: Dict[str, Any] = {
    "session": "UNKNOWN",
    "time_et": "",
    "scanner_count": 0,
}

chart_cache: Dict[str, bytes] = {}


# ============================================================================
# Models
# ============================================================================

class ChatMessage(BaseModel):
    content: str
    conversation_id: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    service: str
    market_session: str
    sandbox_healthy: bool


# ============================================================================
# Lifecycle
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client, gemini_client, request_handler, event_bus
    
    logger.info("ai_agent_starting")
    
    redis_client = RedisClient()
    await redis_client.connect()
    logger.info("redis_connected")
    
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY required")
    
    gemini_client = GeminiClient(api_key=api_key)
    logger.info("gemini_client_initialized")
    
    request_handler = RequestHandler(llm_client=gemini_client)
    await request_handler.initialize()
    logger.info("request_handler_initialized")
    
    event_bus = EventBus(redis_client, "ai_agent")
    event_bus.subscribe(EventType.SESSION_CHANGED, handle_session_changed)
    await event_bus.start_listening()
    
    await update_market_context()
    background_task = asyncio.create_task(market_context_updater())
    
    logger.info("ai_agent_started", version="2.0")
    
    yield
    
    logger.info("ai_agent_stopping")
    background_task.cancel()
    try:
        await background_task
    except asyncio.CancelledError:
        pass
    
    await event_bus.stop_listening()
    await request_handler.close()
    await redis_client.disconnect()
    logger.info("ai_agent_stopped")


app = FastAPI(
    title="AI Agent Service",
    description="Financial market analysis AI",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Event Handlers
# ============================================================================

async def handle_session_changed(event: Event):
    global market_context
    new_session = event.data.get('new_session', 'UNKNOWN')
    market_context['session'] = new_session
    
    for conn_id, ws in active_connections.items():
        try:
            await ws.send_json({
                "type": "market_update",
                "session": new_session,
                "timestamp": datetime.now().isoformat()
            })
        except:
            pass


async def update_market_context():
    global market_context
    try:
        et_tz = pytz.timezone('US/Eastern')
        now = datetime.now(et_tz)
        market_context['time_et'] = now.strftime('%H:%M:%S')
        
        hour, minute = now.hour, now.minute
        time_mins = hour * 60 + minute
        
        if time_mins < 240:
            market_context['session'] = 'CLOSED'
        elif time_mins < 570:
            market_context['session'] = 'PREMARKET'
        elif time_mins < 960:
            market_context['session'] = 'REGULAR'
        elif time_mins < 1200:
            market_context['session'] = 'POSTMARKET'
        else:
            market_context['session'] = 'CLOSED'
    except Exception as e:
        logger.error("market_context_error", error=str(e))


async def market_context_updater():
    while True:
        try:
            await update_market_context()
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            break
        except:
            await asyncio.sleep(60)


# ============================================================================
# REST Endpoints
# ============================================================================

@app.get("/health", response_model=HealthResponse)
async def health_check():
    sandbox_health = request_handler.health_check() if request_handler else {"healthy": False}
    return HealthResponse(
        status="healthy" if sandbox_health.get("healthy") else "degraded",
        service="ai_agent",
        market_session=market_context.get('session', 'UNKNOWN'),
        sandbox_healthy=sandbox_health.get("healthy", False)
    )


@app.get("/api/context")
async def get_context():
    return market_context


@app.post("/api/chat")
async def chat(message: ChatMessage):
    if not message.content.strip():
        raise HTTPException(status_code=400, detail="Message content required")
    
    try:
        result = await request_handler.process(
            AnalysisRequest(
                query=message.content,
                session_id=message.conversation_id or str(uuid.uuid4()),
                market_context=market_context
            )
        )
        return result.to_dict()
    except Exception as e:
        logger.error("chat_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/charts/{chart_name}")
async def get_chart(chart_name: str):
    if chart_name in chart_cache:
        return Response(content=chart_cache[chart_name], media_type="image/png")
    raise HTTPException(status_code=404, detail="Chart not found")


# ============================================================================
# WebSocket Handler
# ============================================================================

@app.websocket("/ws/chat/{client_id}")
async def websocket_chat(websocket: WebSocket, client_id: str):
    await websocket.accept()
    active_connections[client_id] = websocket
    
    logger.info("websocket_connected", client_id=client_id)
    
    await websocket.send_json({
        "type": "connected",
        "client_id": client_id,
        "market_context": market_context,
        "version": "2.0"
    })
    
    try:
        while True:
            data = await websocket.receive_json()
            
            if data.get("type") == "chat_message":
                await handle_chat_message(websocket, client_id, data)
            elif data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
            elif data.get("type") == "clear_history":
                gemini_client.clear_conversation(data.get("conversation_id", client_id))
                await websocket.send_json({"type": "history_cleared"})
    
    except WebSocketDisconnect:
        logger.info("websocket_disconnected", client_id=client_id)
    except Exception as e:
        logger.error("websocket_error", client_id=client_id, error=str(e))
    finally:
        active_connections.pop(client_id, None)


async def handle_chat_message(
    websocket: WebSocket,
    client_id: str,
    data: Dict[str, Any]
):
    """
    Process chat message with step-by-step feedback:
    1. Send response_start
    2. Send agent_step events (reasoning, tool, code)
    3. Send result with outputs
    4. Send response_end
    """
    content = data.get("content", "").strip()
    conversation_id = data.get("conversation_id", client_id)
    message_id = str(uuid.uuid4())
    block_id = 1
    step_id = 0
    
    logger.info("chat_received", client_id=client_id, query=content[:100])
    
    if not content:
        await websocket.send_json({"type": "error", "message": "Empty message"})
        return
    
    # Helper to send step updates
    async def send_step(step_type: str, title: str, description: str = None, status: str = "running", details: str = None):
        nonlocal step_id
        step_id += 1
        await websocket.send_json({
            "type": "agent_step",
            "message_id": message_id,
            "step": {
                "id": f"{message_id}-step-{step_id}",
                "type": step_type,
                "title": title,
                "description": description,
                "status": status,
                "expandable": step_type == "code",
                "details": details
            }
        })
        return f"{message_id}-step-{step_id}"
    
    # 1. Response start
    await websocket.send_json({
        "type": "response_start",
        "message_id": message_id
    })
    
    try:
        # Step 1: Reasoning
        reasoning_step = await send_step(
            "reasoning", 
            "Analyzing request",
            f"Understanding: {content[:60]}..."
        )
        
        # Step 2: Data loading
        await send_step(
            "tool",
            "Market Scanner",
            "Loading real-time market data",
            "running"
        )
        
        # Process with orchestrator
        result = await request_handler.process(
            AnalysisRequest(
                query=content,
                session_id=conversation_id,
                market_context=market_context
            )
        )
        
        # Update data step to complete
        await websocket.send_json({
            "type": "agent_step_update",
            "message_id": message_id,
            "step_id": f"{message_id}-step-2",
            "status": "complete",
            "description": f"Loaded {len(result.data_sources)} data sources"
        })
        
        # Step 3: Code generation
        if result.code:
            code_step = await send_step(
                "code",
                "Analysis Code",
                f"Executing {len(result.code.split(chr(10)))} lines of analysis",
                "running",
                result.code
            )
            
            # Build outputs
            outputs = build_outputs(result, message_id)
            
            # Update code step based on result
            await websocket.send_json({
                "type": "agent_step_update",
                "message_id": message_id,
                "step_id": code_step,
                "status": "complete" if result.success else "error",
                "description": f"Analysis completed in {result.execution_time:.1f}s"
            })
            
            logger.info("outputs_built", 
                count=len(outputs),
                data_keys=list(result.data.keys()) if result.data else [],
                chart_count=len(result.charts)
            )
            
            # Send result
            await websocket.send_json({
                "type": "result",
                "message_id": message_id,
                "block_id": block_id,
                "status": "success" if result.success else "error",
                "success": result.success,
                "code": result.code,
                "outputs": outputs,
                "error": result.error,
                "execution_time_ms": int(result.execution_time * 1000),
                "timestamp": datetime.now().isoformat()
            })
        
        # Send explanation text
        if result.explanation:
            await websocket.send_json({
                "type": "assistant_text",
                "message_id": message_id,
                "delta": result.explanation
            })
        
        # 7. Response end
        await websocket.send_json({
            "type": "response_end",
            "message_id": message_id
        })
    
    except Exception as e:
        import traceback
        logger.error("chat_error", error=str(e), tb=traceback.format_exc())
        await websocket.send_json({
            "type": "error",
            "message_id": message_id,
            "error": str(e)
        })
        await websocket.send_json({
            "type": "response_end",
            "message_id": message_id
        })


def build_outputs(result, message_id: str) -> List[Dict[str, Any]]:
    """
    Build frontend-compatible outputs from analysis result.
    
    Handles:
    - DataFrames → table outputs
    - Chart bytes → chart outputs with base64
    - Stdout → stats output
    """
    outputs = []
    
    # Process DataFrames
    has_data = False
    if result.data:
        for name, value in result.data.items():
            # Handle actual DataFrame objects
            if isinstance(value, pd.DataFrame):
                if not value.empty:
                    has_data = True
                    outputs.append({
                        "type": "table",
                        "title": format_title(name),
                        "columns": value.columns.tolist(),
                        "rows": clean_rows(value.head(100)),
                        "total": len(value)
                    })
            # Handle serialized dict format (from to_dict())
            elif isinstance(value, dict):
                rows = value.get("rows", [])
                if rows:
                    has_data = True
                    outputs.append({
                        "type": "table",
                        "title": format_title(name),
                        "columns": value.get("columns", []),
                        "rows": rows[:100],
                        "total": value.get("row_count", len(rows))
                    })
    
    # Process charts
    for chart_name, chart_bytes in result.charts.items():
        cache_key = f"{message_id}_{chart_name}"
        chart_cache[cache_key] = chart_bytes
        outputs.append({
            "type": "chart",
            "title": format_title(chart_name),
            "chart_type": "image",
            "image_base64": base64.b64encode(chart_bytes).decode('utf-8')
        })
    
    # Show stdout if no data outputs OR if there's an important message
    if result.stdout:
        stdout_clean = result.stdout.strip()
        if stdout_clean and (not has_data or "error" in stdout_clean.lower() or "no " in stdout_clean.lower()):
            outputs.append({
                "type": "stats",
                "title": "Mensaje",
                "stats": {},
                "content": stdout_clean
            })
    
    # If no outputs at all, show a message
    if len(outputs) == 0:
        outputs.append({
            "type": "stats",
            "title": "Resultado",
            "stats": {},
            "content": "Sin resultados. Los datos del scanner son en tiempo real (no historicos)."
        })
    
    return outputs


def format_title(name: str) -> str:
    """Convert snake_case to Title Case."""
    return name.replace('_', ' ').replace('-', ' ').title()


def clean_rows(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Convert DataFrame rows to JSON-safe dicts."""
    import math
    from datetime import datetime as dt
    
    def clean_value(v):
        # Handle NaN/Inf
        if isinstance(v, float):
            if math.isnan(v) or math.isinf(v):
                return None
        if pd.isna(v):
            return None
        # Handle Timestamps
        if isinstance(v, (pd.Timestamp, dt)):
            return v.isoformat()
        # Handle numpy types
        if hasattr(v, 'item'):
            return v.item()
        return v
    
    rows = df.to_dict('records')
    return [{k: clean_value(v) for k, v in row.items()} for row in rows]


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8030, reload=True)
