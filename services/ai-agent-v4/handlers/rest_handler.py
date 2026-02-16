"""
REST Handler - FastAPI endpoints for synchronous query execution.

Endpoints:
  POST /api/query              -> Run a query through the LangGraph orchestrator
  GET  /api/health             -> Service health check
  GET  /api/tools              -> List available MCP tools
  GET  /api/graph/state/{tid}  -> Inspect graph state for a thread (debugging)
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["agent-v4"])


# ── Request / Response models ────────────────────────────────────

class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, description="User query text")
    thread_id: Optional[str] = Field(None, description="Conversation thread ID")
    market_context: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional market context (session, time, etc.)",
    )


class QueryResponse(BaseModel):
    response: str
    thread_id: str
    agent_results: dict[str, Any] = {}
    charts: list[dict] = []
    tables: list[dict] = []
    execution_metadata: dict[str, Any] = {}


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    graph_ready: bool


class ToolInfo(BaseModel):
    name: str
    description: str
    agent: str


# ── Endpoints ────────────────────────────────────────────────────

@router.post("/query", response_model=QueryResponse)
async def run_query(request: QueryRequest) -> QueryResponse:
    """Execute a query through the full LangGraph agent pipeline."""
    from graph.orchestrator import get_graph

    thread_id = request.thread_id or f"rest-{int(time.time() * 1000)}"

    initial_state: dict[str, Any] = {
        "messages": [{"role": "user", "content": request.query}],
        "query": request.query,
        "language": "en",
        "tickers": [],
        "plan": "",
        "active_agents": [],
        "agent_results": {},
        "charts": [],
        "tables": [],
        "market_context": request.market_context,
        "memory_context": [],
        "workflow_id": None,
        "trigger_context": None,
        "node_config": None,
        "final_response": "",
        "execution_metadata": {},
        "error": None,
    }

    config = {"configurable": {"thread_id": thread_id}}
    graph = get_graph()

    start_time = time.time()

    try:
        # Run the full graph to completion
        final_state = await graph.ainvoke(initial_state, config=config)
    except Exception as exc:
        logger.error("Query execution failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Agent execution failed: {exc}")

    elapsed_ms = int((time.time() - start_time) * 1000)
    exec_meta = final_state.get("execution_metadata", {})
    exec_meta["total_elapsed_ms"] = elapsed_ms

    return QueryResponse(
        response=final_state.get("final_response", ""),
        thread_id=thread_id,
        agent_results=final_state.get("agent_results", {}),
        charts=final_state.get("charts", []),
        tables=final_state.get("tables", []),
        execution_metadata=exec_meta,
    )


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Service health check."""
    graph_ready = False
    try:
        from graph.orchestrator import get_graph
        g = get_graph()
        graph_ready = g is not None
    except Exception:
        pass

    return HealthResponse(
        status="healthy" if graph_ready else "degraded",
        service="ai-agent-v4",
        version="4.0.0",
        graph_ready=graph_ready,
    )


@router.get("/tools", response_model=list[ToolInfo])
async def list_tools() -> list[ToolInfo]:
    """List all available MCP tools grouped by agent."""
    from agents.supervisor import AVAILABLE_AGENTS

    tools: list[ToolInfo] = []
    for agent_name, description in AVAILABLE_AGENTS.items():
        tools.append(ToolInfo(
            name=agent_name,
            description=description,
            agent=agent_name,
        ))
    return tools


@router.get("/graph/state/{thread_id}")
async def get_graph_state(thread_id: str) -> dict[str, Any]:
    """Inspect the graph state for a specific thread (debugging)."""
    from graph.orchestrator import get_graph

    graph = get_graph()
    config = {"configurable": {"thread_id": thread_id}}

    try:
        state = graph.get_state(config)
        if state and hasattr(state, "values"):
            values = dict(state.values)
            # Sanitize messages for JSON serialization
            if "messages" in values:
                values["messages"] = [
                    {
                        "role": getattr(m, "type", "unknown"),
                        "content": getattr(m, "content", str(m)),
                    }
                    for m in values.get("messages", [])
                ]
            return {"thread_id": thread_id, "state": values}
        return {"thread_id": thread_id, "state": None, "note": "No state found for this thread."}
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve state: {exc}",
        )
