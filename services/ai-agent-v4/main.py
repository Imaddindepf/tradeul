"""
AI Agent V4 - FastAPI entry point.

Multi-agent LangGraph orchestrator with WebSocket streaming and REST API.
Port 8031.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from auth import (
    AgentAuthError,
    extract_bearer_token,
    extract_ws_token,
    verify_clerk_token,
)
from handlers.rest_handler import router as rest_router
from handlers.trigger_handler import router as trigger_router
from handlers.websocket_handler import handle_websocket

logger = logging.getLogger(__name__)

# Rutas HTTP que NO requieren autenticación (healthcheck del contenedor/LB).
_AUTH_EXEMPT_PATHS = {"/api/health"}

# ── Logging setup ────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


# ── Lifespan ─────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: build graph. Shutdown: clean up resources."""
    logger.info("AI Agent V4 starting up...")

    # Initialize the LangGraph orchestrator (eagerly, so errors surface early)
    from graph.orchestrator import init_graph
    graph = await init_graph()
    logger.info("LangGraph orchestrator initialized: %s", graph)

    # Store graph ref on app state for access from handlers
    app.state.graph = graph

    # Start the reactive trigger engine
    from triggers.engine import TriggerEngine
    from handlers.trigger_handler import set_engine
    trigger_engine = TriggerEngine()
    await trigger_engine.start()
    app.state.trigger_engine = trigger_engine
    set_engine(trigger_engine)
    logger.info("Reactive Trigger Engine started")

    # Initialize memory manager
    from memory.manager import MemoryManager
    memory_mgr = MemoryManager()
    app.state.memory = memory_mgr
    logger.info("Memory Manager initialized")

    # Validate the MCP tool catalog against the live gateway (non-fatal)
    from agents.mcp_catalog import validate_catalog
    await validate_catalog()

    yield  # ── app is running ──

    logger.info("AI Agent V4 shutting down...")

    # Stop trigger engine
    try:
        await trigger_engine.stop()
    except Exception:
        pass

    # Clean up memory manager (use the same instance, not a new one)
    try:
        await memory_mgr.close()
    except Exception:
        pass

    # Close shared httpx client for MCP tools
    try:
        from agents._mcp_tools import close_client
        await close_client()
    except Exception:
        pass

    # Close shared Redis client for ticker validation
    try:
        from agents._ticker_utils import close_redis
        await close_redis()
    except Exception:
        pass

    # Release the durable checkpointer connection
    try:
        from graph.orchestrator import close_graph
        await close_graph()
    except Exception:
        pass

    logger.info("AI Agent V4 shutdown complete.")


# ── App ──────────────────────────────────────────────────────────

app = FastAPI(
    title="Tradeul AI Agent V4",
    description="Multi-agent LangGraph orchestrator for financial intelligence",
    version="4.0.0",
    lifespan=lifespan,
    # Sin superficie de descubrimiento pública.
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


class ClerkAuthMiddleware(BaseHTTPMiddleware):
    """Exige un JWT de Clerk válido en todas las rutas HTTP salvo el healthcheck.

    El WebSocket se autentica aparte (query param ?token=) porque el middleware
    HTTP de Starlette no intercepta el scope 'websocket'.
    """

    async def dispatch(self, request, call_next):
        # Preflight CORS: los navegadores no envían Authorization en OPTIONS.
        if request.method == "OPTIONS":
            return await call_next(request)
        if request.url.path in _AUTH_EXEMPT_PATHS:
            return await call_next(request)

        token = extract_bearer_token(request.headers.get("Authorization"))
        try:
            verify_clerk_token(token or "")
        except AgentAuthError as exc:
            logger.info("agent_http_auth_denied path=%s reason=%s", request.url.path, exc)
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        return await call_next(request)

# ── CORS ─────────────────────────────────────────────────────────

ALLOWED_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,http://localhost:3001,http://localhost:8031,https://tradeul.com,https://agent.tradeul.com",
).split(",")

# Orden importante: ClerkAuth se añade ANTES que CORS para que CORS quede como
# middleware más externo y añada cabeceras también a las respuestas 401.
app.add_middleware(ClerkAuthMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── REST routes ──────────────────────────────────────────────────

app.include_router(rest_router)
app.include_router(trigger_router)

# ── WebSocket endpoint ───────────────────────────────────────────


@app.websocket("/ws/chat/{client_id}")
async def ws_chat(websocket: WebSocket, client_id: str):
    """WebSocket endpoint for real-time streaming chat.

    Requiere ?token=<jwt de Clerk> en la URL. Si falta o es inválido se rechaza
    el handshake (mismo patrón que ws.tradeul.com / wschat.tradeul.com).
    """
    token = extract_ws_token(websocket.scope.get("query_string", b"").decode("latin-1"))
    try:
        verify_clerk_token(token or "")
    except AgentAuthError as exc:
        logger.info("agent_ws_auth_denied client_id=%s reason=%s", client_id, exc)
        await websocket.close(code=4401)  # 4401 = app-level "unauthorized"
        return
    await handle_websocket(websocket, client_id)


# ── Run ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8031")),
        reload=os.getenv("ENV", "production") == "development",
        log_level="info",
    )
