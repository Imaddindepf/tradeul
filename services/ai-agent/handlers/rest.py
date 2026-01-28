"""REST API Routes for AI Agent."""

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
from typing import Optional, Dict, Any
import structlog

logger = structlog.get_logger(__name__)


class QueryRequest(BaseModel):
    query: str
    context: Optional[Dict[str, Any]] = None


class QueryResponse(BaseModel):
    success: bool
    response: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


def create_rest_routes(agent, market_context: Dict, chart_cache: Dict) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["ai-agent"])

    @router.get("/health")
    async def health_check():
        return {"status": "healthy", "service": "ai-agent", "version": "3.0"}

    @router.get("/chart/{cache_key}")
    async def get_chart(cache_key: str):
        if cache_key in chart_cache:
            return Response(content=chart_cache[cache_key], media_type="image/png")
        raise HTTPException(status_code=404, detail="Chart not found")

    @router.post("/query", response_model=QueryResponse)
    async def query(request: QueryRequest):
        try:
            if not agent:
                raise HTTPException(status_code=503, detail="Agent not initialized")
            result = await agent.process(request.query)
            return QueryResponse(
                success=result.success,
                response=result.response,
                data=result.data if hasattr(result, "data") else None,
                error=result.error if hasattr(result, "error") else None
            )
        except Exception as e:
            logger.error("query_error", error=str(e))
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/status")
    async def get_status():
        return {
            "agent_ready": agent is not None,
            "market_session": market_context.get("session", "UNKNOWN")
        }

    return router
