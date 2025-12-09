"""
Chat Service - FastAPI Application
Separate microservice for community chat features.
Port: 8016
"""

import os
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from http_clients import http_clients
from auth.middleware import PassiveAuthMiddleware
from routers import channels_router, groups_router, messages_router, invites_router, users_router

# Configure logging
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ]
)

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle management
    """
    logger.info("chat_service_starting")
    
    # Initialize clients
    try:
        await http_clients.initialize()
        logger.info("chat_service_started")
    except Exception as e:
        logger.error("chat_service_startup_error", error=str(e))
        raise
    
    yield
    
    # Cleanup
    await http_clients.close()
    logger.info("chat_service_stopped")


# Create app
app = FastAPI(
    title="Tradeul Chat Service",
    description="Community chat with real-time messaging and ticker integration",
    version="1.0.0",
    lifespan=lifespan
)

# CORS - Allow frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "https://tradeul.com",
        "https://www.tradeul.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Passive Auth (sets request.state.user if valid token)
app.add_middleware(PassiveAuthMiddleware)

# Routers
app.include_router(channels_router, prefix="/api/chat")
app.include_router(groups_router, prefix="/api/chat")
app.include_router(messages_router, prefix="/api/chat")
app.include_router(invites_router, prefix="/api/chat")
app.include_router(users_router, prefix="/api/chat")


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "ok", "service": "chat"}


@app.get("/")
async def root():
    """Root endpoint"""
    return {"service": "tradeul-chat", "version": "1.0.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("CHAT_PORT", "8016")),
        reload=os.getenv("ENV", "development") == "development"
    )

