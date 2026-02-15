"""
AI Agent V4 - FastAPI entry point.

Multi-agent LangGraph orchestrator with WebSocket streaming and REST API.
Port 8031 (ai-agent v3 runs on 8030).
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from handlers.rest_handler import router as rest_router
from handlers.websocket_handler import handle_websocket

logger = logging.getLogger(__name__)

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
    from graph.orchestrator import get_graph
    graph = get_graph()
    logger.info("LangGraph orchestrator initialized: %s", graph)

    # Store graph ref on app state for access from handlers
    app.state.graph = graph

    yield  # ── app is running ──

    logger.info("AI Agent V4 shutting down...")

    # Clean up memory manager if initialized
    try:
        from memory.manager import MemoryManager
        mm = MemoryManager()
        await mm.close()
    except Exception:
        pass

    logger.info("AI Agent V4 shutdown complete.")


# ── App ──────────────────────────────────────────────────────────

app = FastAPI(
    title="TradeUL AI Agent V4",
    description="Multi-agent LangGraph orchestrator for financial intelligence",
    version="4.0.0",
    lifespan=lifespan,
)

# ── CORS ─────────────────────────────────────────────────────────

ALLOWED_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,http://localhost:3001,http://localhost:8031",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── REST routes ──────────────────────────────────────────────────

app.include_router(rest_router)

# ── WebSocket endpoint ───────────────────────────────────────────


@app.websocket("/ws/chat/{client_id}")
async def ws_chat(websocket: WebSocket, client_id: str):
    """WebSocket endpoint for real-time streaming chat."""
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
