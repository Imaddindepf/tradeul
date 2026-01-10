"""
REST API Handlers
=================
HTTP endpoints for the AI Agent service.
"""

import uuid
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
import structlog

logger = structlog.get_logger(__name__)


class ChatMessage(BaseModel):
    """Chat request model."""
    content: str
    conversation_id: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    service: str
    market_session: str
    version: str


def create_rest_routes(agent, market_context: dict, chart_cache: dict) -> APIRouter:
    """
    Create REST API routes.
    
    Args:
        agent: MarketAgent instance
        market_context: Current market state
        chart_cache: Chart bytes cache
    
    Returns:
        FastAPI router with endpoints
    """
    router = APIRouter()
    
    @router.get("/health", response_model=HealthResponse)
    async def health_check():
        """Service health check."""
        return HealthResponse(
            status="healthy",
            service="ai_agent",
            market_session=market_context.get("session", "UNKNOWN"),
            version="3.0"
        )
    
    @router.get("/api/context")
    async def get_context():
        """Get current market context."""
        return market_context
    
    @router.post("/api/chat")
    async def chat(message: ChatMessage):
        """
        Process chat message via REST.
        
        Note: WebSocket is preferred for real-time step updates.
        """
        if not message.content.strip():
            raise HTTPException(status_code=400, detail="Message content required")
        
        try:
            result = await agent.process(
                query=message.content,
                market_context=market_context
            )
            
            return {
                "success": result.success,
                "response": result.response,
                "tools_used": result.tools_used,
                "execution_time_ms": int(result.execution_time * 1000),
                "error": result.error
            }
        except Exception as e:
            logger.error("chat_error", error=str(e))
            raise HTTPException(status_code=500, detail=str(e))
    
    @router.get("/api/charts/{chart_name}")
    async def get_chart(chart_name: str):
        """Retrieve cached chart image."""
        if chart_name in chart_cache:
            return Response(
                content=chart_cache[chart_name],
                media_type="image/png"
            )
        raise HTTPException(status_code=404, detail="Chart not found")
    
    return router
