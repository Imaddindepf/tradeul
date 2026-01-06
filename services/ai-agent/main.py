"""
AI Agent Service
WebSocket-based conversational AI for financial market analysis

Integrates with:
- Redis (data cache, streams)
- Scanner API (categories, filtered tickers)
- TimescaleDB (historical data)
- EventBus (market session events)
"""

import asyncio
import os
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager
import json

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
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
from dsl.executor import DSLExecutor
from data.data_provider import DataProvider

# Configure logging
configure_logging(service_name="ai_agent")
logger = get_logger(__name__)


# ============================================================================
# Global State
# ============================================================================

redis_client: Optional[RedisClient] = None
data_provider: Optional[DataProvider] = None
gemini_client: Optional[GeminiClient] = None
event_bus: Optional[EventBus] = None

# Active WebSocket connections
active_connections: Dict[str, WebSocket] = {}

# Market context cache
market_context: Dict[str, Any] = {
    "session": "UNKNOWN",
    "time_et": "",
    "scanner_count": 0,
    "category_stats": {}
}


# ============================================================================
# Pydantic Models
# ============================================================================

class ChatMessage(BaseModel):
    """Mensaje de chat entrante"""
    content: str
    conversation_id: Optional[str] = None


class HealthResponse(BaseModel):
    """Respuesta de health check"""
    status: str
    service: str
    market_session: str


# ============================================================================
# Lifecycle
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestión del ciclo de vida"""
    global redis_client, data_provider, gemini_client, event_bus
    
    logger.info("ai_agent_starting")
    
    # Initialize Redis
    redis_client = RedisClient()
    await redis_client.connect()
    logger.info("redis_connected")
    
    # Initialize Data Provider
    data_provider = DataProvider(redis_client)
    await data_provider.initialize()
    logger.info("data_provider_initialized")
    
    # Initialize Gemini Client
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.error("GOOGLE_API_KEY not set")
        raise ValueError("GOOGLE_API_KEY environment variable is required")
    
    gemini_client = GeminiClient(api_key=api_key)
    logger.info("gemini_client_initialized")
    
    # Initialize EventBus
    event_bus = EventBus(redis_client, "ai_agent")
    event_bus.subscribe(EventType.SESSION_CHANGED, handle_session_changed)
    await event_bus.start_listening()
    logger.info("event_bus_started")
    
    # Initial market context
    await update_market_context()
    
    # Start background tasks
    background_task = asyncio.create_task(market_context_updater())
    
    logger.info("ai_agent_started")
    
    yield
    
    # Cleanup
    logger.info("ai_agent_stopping")
    
    background_task.cancel()
    try:
        await background_task
    except asyncio.CancelledError:
        pass
    
    await event_bus.stop_listening()
    await data_provider.close()
    await redis_client.disconnect()
    
    logger.info("ai_agent_stopped")


app = FastAPI(
    title="AI Agent Service",
    description="Conversational AI for financial market analysis",
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


# ============================================================================
# Event Handlers
# ============================================================================

async def handle_session_changed(event: Event):
    """Maneja cambios de sesión del mercado"""
    global market_context
    
    new_session = event.data.get('new_session', 'UNKNOWN')
    market_context['session'] = new_session
    
    logger.info("market_session_changed", new_session=new_session)
    
    # Notificar a todos los clientes conectados
    notification = {
        "type": "market_update",
        "session": new_session,
        "timestamp": datetime.now().isoformat()
    }
    
    for conn_id, ws in active_connections.items():
        try:
            await ws.send_json(notification)
        except Exception as e:
            logger.warning("failed_to_notify_client", conn_id=conn_id, error=str(e))


async def update_market_context():
    """Actualiza el contexto del mercado"""
    global market_context
    
    try:
        # Get market status
        status = await data_provider.get_market_status()
        market_context['session'] = status.get('session', 'UNKNOWN')
        
        # Get current time ET
        et_tz = pytz.timezone('US/Eastern')
        market_context['time_et'] = datetime.now(et_tz).strftime('%H:%M:%S')
        
        # Get scanner count
        scanner_data = await data_provider.get_source_data('scanner')
        market_context['scanner_count'] = len(scanner_data)
        
        # Get category stats
        market_context['category_stats'] = await data_provider.get_category_stats()
        
    except Exception as e:
        logger.error("error_updating_market_context", error=str(e))


async def market_context_updater():
    """Background task para actualizar contexto del mercado"""
    while True:
        try:
            await update_market_context()
            await asyncio.sleep(30)  # Actualizar cada 30 segundos
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("market_context_updater_error", error=str(e))
            await asyncio.sleep(60)


# ============================================================================
# REST Endpoints
# ============================================================================

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy",
        service="ai_agent",
        market_session=market_context.get('session', 'UNKNOWN')
    )


@app.get("/api/context")
async def get_context():
    """Obtiene el contexto actual del mercado"""
    return market_context


@app.post("/api/chat")
async def chat(message: ChatMessage):
    """
    Endpoint REST para chat (alternativa al WebSocket).
    Útil para testing y clientes que no soportan WebSocket.
    """
    if not message.content.strip():
        raise HTTPException(status_code=400, detail="Message content is required")
    
    conversation_id = message.conversation_id or str(uuid.uuid4())
    
    try:
        # Generate response
        response = await gemini_client.generate_response(
            user_message=message.content,
            conversation_id=conversation_id,
            market_context=market_context
        )
        
        result = {
            "conversation_id": conversation_id,
            "text": response.text,
            "has_code": response.has_code,
            "outputs": []
        }
        
        # Execute code if present
        if response.has_code and response.code_blocks:
            executor = DSLExecutor(data_provider)
            
            for code in response.code_blocks:
                execution_result = await executor.execute(code)
                result["outputs"].append(execution_result.to_dict())
        
        return result
    
    except Exception as e:
        logger.error("chat_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# WebSocket Handler
# ============================================================================

@app.websocket("/ws/chat/{client_id}")
async def websocket_chat(websocket: WebSocket, client_id: str):
    """
    WebSocket para chat en tiempo real.
    
    Protocol:
    - Client sends: {"type": "chat_message", "content": "...", "conversation_id": "..."}
    - Server sends: {"type": "response_start", "message_id": "..."}
    - Server sends: {"type": "assistant_text", "message_id": "...", "delta": "..."}
    - Server sends: {"type": "code_execution", "block_id": 1, "status": "running", "code": "..."}
    - Server sends: {"type": "result", "block_id": 1, "status": "success", "data": {...}}
    - Server sends: {"type": "response_end", "message_id": "..."}
    """
    await websocket.accept()
    active_connections[client_id] = websocket
    
    logger.info("websocket_connected", client_id=client_id)
    
    # Send initial context
    await websocket.send_json({
        "type": "connected",
        "client_id": client_id,
        "market_context": market_context
    })
    
    try:
        while True:
            # Receive message
            data = await websocket.receive_json()
            
            if data.get("type") == "chat_message":
                await handle_chat_message(websocket, client_id, data)
            
            elif data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
            
            elif data.get("type") == "clear_history":
                conversation_id = data.get("conversation_id", client_id)
                gemini_client.clear_conversation(conversation_id)
                await websocket.send_json({
                    "type": "history_cleared",
                    "conversation_id": conversation_id
                })
    
    except WebSocketDisconnect:
        logger.info("websocket_disconnected", client_id=client_id)
    except Exception as e:
        logger.error("websocket_error", client_id=client_id, error=str(e))
    finally:
        if client_id in active_connections:
            del active_connections[client_id]


async def handle_chat_message(
    websocket: WebSocket,
    client_id: str,
    data: Dict[str, Any]
):
    """Procesa un mensaje de chat"""
    content = data.get("content", "").strip()
    conversation_id = data.get("conversation_id", client_id)
    message_id = str(uuid.uuid4())
    
    logger.info("chat_message_received", client_id=client_id, content_len=len(content), content_preview=content[:100])
    
    if not content:
        await websocket.send_json({
            "type": "error",
            "message": "Empty message"
        })
        return
    
    # Response start
    await websocket.send_json({
        "type": "response_start",
        "message_id": message_id
    })
    
    try:
        # Stream response from Gemini
        full_response = ""
        async for chunk in gemini_client.generate_response_stream(
            user_message=content,
            conversation_id=conversation_id,
            market_context=market_context
        ):
            full_response += chunk
            await websocket.send_json({
                "type": "assistant_text",
                "message_id": message_id,
                "delta": chunk
            })
        
        # Extract and execute code blocks
        code_blocks = gemini_client._extract_code_blocks(full_response)
        
        if code_blocks:
            executor = DSLExecutor(data_provider)
            
            for idx, code in enumerate(code_blocks, 1):
                # Notify code execution start
                await websocket.send_json({
                    "type": "code_execution",
                    "message_id": message_id,
                    "block_id": idx,
                    "status": "running",
                    "code": code
                })
                
                # Execute with Auto-Heal retry
                result = await executor.execute(code)
                
                # AUTO-HEAL: Si falla, intentar corregir el código
                if not result.success and "no attribute" in (result.error or ""):
                    logger.info("auto_heal_attempting", error=result.error)
                    
                    await websocket.send_json({
                        "type": "code_execution",
                        "message_id": message_id,
                        "block_id": idx,
                        "status": "fixing",
                        "code": code
                    })
                    
                    # Pedir al LLM que corrija
                    fixed_code = await gemini_client.fix_code(code, result.error)
                    
                    if fixed_code != code:
                        # Reintentar con código corregido
                        result = await executor.execute(fixed_code)
                        code = fixed_code  # Actualizar para mostrar el código corregido
                
                # Send result
                await websocket.send_json({
                    "type": "result",
                    "message_id": message_id,
                    "block_id": idx,
                    "status": "success" if result.success else "error",
                    **result.to_dict()
                })
                
                # REFINAMIENTO: Guardar último resultado para contexto
                if result.success and result.outputs:
                    for output in result.outputs:
                        if hasattr(output, 'rows') and hasattr(output, 'columns'):
                            # Es una tabla
                            symbols = [
                                row.get('symbol', '') 
                                for row in output.rows[:5] 
                                if row.get('symbol')
                            ]
                            gemini_client.set_last_result(
                                conversation_id=conversation_id,
                                title=output.title,
                                row_count=len(output.rows),
                                columns=output.columns,
                                sample_symbols=symbols,
                                code=code
                            )
                            break  # Solo guardar la primera tabla
        
        # Response end
        await websocket.send_json({
            "type": "response_end",
            "message_id": message_id
        })
    
    except Exception as e:
        import traceback
        logger.error("chat_message_error", error=str(e), traceback=traceback.format_exc())
        await websocket.send_json({
            "type": "error",
            "message_id": message_id,
            "error": str(e)
        })


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8030,
        reload=True
    )

