"""
REST Handler - FastAPI endpoints for synchronous query execution.

Endpoints:
  POST /api/query              -> Run a query through the LangGraph orchestrator
  GET  /api/health             -> Service health check
  GET  /api/tools              -> List available MCP tools
  GET  /api/graph/state/{tid}  -> Inspect graph state for a thread (debugging)
  GET  /api/sessions           -> List recent conversation sessions
  GET  /api/sessions/{id}/messages -> Load messages for a session
  DELETE /api/sessions/{id}    -> Delete a session
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import request_user_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["agent-v4"])


# ── Request / Response models ────────────────────────────────────

class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=8000, description="User query text")
    thread_id: Optional[str] = Field(None, description="Conversation thread ID")
    mode: str = Field("auto", description="Execution mode: auto, quick, deep")
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


class BacktestSubmitNaturalRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=8000)
    tickers: list[str] = Field(..., min_length=1, max_length=3)
    # NOTE: identity is taken from the authenticated token, never from the body.
    # This field is ignored (kept for backward-compatible request shape).
    user_id: Optional[str] = None


class BacktestSubmitNaturalResponse(BaseModel):
    job_id: str


# ── Endpoints ────────────────────────────────────────────────────

@router.post("/query", response_model=QueryResponse)
async def run_query(
    request: QueryRequest,
    http_request: Request,
    user_id: str = Depends(request_user_id),
) -> QueryResponse:
    """Execute a query through the full LangGraph agent pipeline."""
    from graph.orchestrator import get_graph
    from limits import check_rate, RateLimitExceeded

    thread_id = request.thread_id or f"rest-{int(time.time() * 1000)}"

    # ── Conversational memory: recent turns + cross-thread recall ──
    memory = getattr(http_request.app.state, "memory", None)

    # Per-user throttle (same ceiling as the WS path).
    if memory is not None:
        try:
            await check_rate(await memory._get_redis(), user_id)
        except RateLimitExceeded as rl:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded; retry after {rl.retry_after}s",
                headers={"Retry-After": str(rl.retry_after)},
            )
    memory_context: list[dict[str, Any]] = []
    if memory:
        try:
            memory_context = await memory.build_memory_context(
                user_id=user_id, thread_id=thread_id, query=request.query,
            )
        except Exception as exc:
            logger.warning("memory_context load failed: %s", exc)

    # ── Persisted run (parity with the WS path: telemetry + traceability) ──
    import uuid as _uuid
    from runs.store import get_run_store
    run_id = _uuid.uuid4().hex[:16]
    run_store = get_run_store()
    try:
        await run_store.create_run(
            run_id, user_id=user_id, thread_id=thread_id, query=request.query,
        )
    except Exception as exc:
        logger.warning("REST create_run failed: %s", exc)

    initial_state: dict[str, Any] = {
        "messages": [{"role": "user", "content": request.query}],
        "user_id": user_id,
        "run_id": run_id,
        "query": request.query,
        "mode": request.mode if request.mode in ("auto", "quick", "deep") else "auto",
        "tickers": [],
        "ticker_info": {},
        "plan": "",
        "active_agents": [],
        "agent_results": {},
        "charts": [],
        "tables": [],
        "market_context": request.market_context,
        "memory_context": memory_context,
        "workflow_id": None,
        "trigger_context": None,
        "node_config": None,
        "final_response": "",
        "execution_metadata": {},
        "chart_context": None,
        "clarification": None,
        "clarification_hint": "",
        "error": None,
    }

    config = {"configurable": {"thread_id": f"{user_id}:{thread_id}"}}
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

    try:
        await run_store.finish_run(run_id, "complete")
    except Exception as exc:
        logger.warning("REST finish_run failed: %s", exc)

    # ── Persist the turn so follow-ups have context (parity with WS) ──
    if memory:
        try:
            await memory.store_conversation(
                user_id=user_id,
                thread_id=thread_id,
                query=request.query,
                response=(final_state.get("final_response") or "")[:15000],
                tickers=final_state.get("tickers", []) or [],
                intent=final_state.get("intent", "") or "",
            )
        except Exception as exc:
            logger.warning("REST conversation persist failed: %s", exc)

    return QueryResponse(
        response=final_state.get("final_response", ""),
        thread_id=thread_id,
        agent_results=final_state.get("agent_results", {}),
        charts=final_state.get("charts", []),
        tables=final_state.get("tables", []),
        execution_metadata=exec_meta,
    )


@router.post("/backtest/submit-natural", response_model=BacktestSubmitNaturalResponse)
async def submit_backtest_natural_endpoint(
    body: BacktestSubmitNaturalRequest,
    user_id: str = Depends(request_user_id),
) -> BacktestSubmitNaturalResponse:
    """Parse natural language strategy, enqueue on backtester, return job_id for polling.

    Identity comes from the verified Clerk token — the request body's user_id
    is ignored (previously it was trusted, allowing jobs to be attributed to
    another user).
    """
    from agents.backtest import submit_backtest_natural
    try:
        out = await submit_backtest_natural(
            prompt=body.prompt,
            tickers=body.tickers,
            user_id=user_id,
        )
        job_id = out.get("job_id") or ""
        if not job_id:
            raise HTTPException(status_code=502, detail="Backtester did not return job_id")
        return BacktestSubmitNaturalResponse(job_id=job_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("submit_backtest_natural failed")
        raise HTTPException(status_code=502, detail=str(e))


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
    """Inspect the graph state for a specific thread (debugging only).

    Disabled in production: it exposes full conversation state without auth.
    Enable with DEBUG_ENDPOINTS=true (e.g. local development).
    """
    import os
    if os.getenv("DEBUG_ENDPOINTS", "").lower() != "true":
        raise HTTPException(status_code=404, detail="Not found")

    from graph.orchestrator import get_graph

    graph = get_graph()
    config = {"configurable": {"thread_id": thread_id}}

    try:
        # aget_state works with both sync (MemorySaver) and async (Postgres) checkpointers
        state = await graph.aget_state(config)
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


# ── Session History Endpoints ────────────────────────────────────

@router.get("/sessions")
async def list_sessions(
    request: Request,
    user_id: str = Depends(request_user_id),
    limit: int = 30,
) -> dict[str, Any]:
    """List recent conversation sessions."""
    memory = request.app.state.memory
    threads = await memory.get_recent_threads(user_id, limit)
    return {"sessions": threads}


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    request: Request,
    user_id: str = Depends(request_user_id),
    limit: int = 100,
) -> dict[str, Any]:
    """Load messages for a specific session."""
    memory = request.app.state.memory
    history = await memory.get_conversation_history(user_id, session_id, limit)
    return {"messages": history, "session_id": session_id}


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    request: Request,
    user_id: str = Depends(request_user_id),
) -> dict[str, Any]:
    """Delete a session and its messages (Postgres + Redis cache)."""
    memory = request.app.state.memory
    await memory.delete_thread(user_id, session_id)
    return {"deleted": True}


# ── Cost / telemetry ─────────────────────────────────────────────

@router.get("/runs/{run_id}/cost")
async def run_cost(
    run_id: str,
    user_id: str = Depends(request_user_id),
) -> dict[str, Any]:
    """LLM token/cost/latency breakdown for a run (by node and model)."""
    from telemetry import get_telemetry
    return await get_telemetry().run_summary(run_id)


@router.get("/usage")
async def usage(
    user_id: str = Depends(request_user_id),
    days: int = 7,
) -> dict[str, Any]:
    """The caller's own LLM spend over the last `days` (by model)."""
    from telemetry import get_telemetry
    return await get_telemetry().user_summary(user_id, days=days)


@router.get("/tools/health")
async def tools_health(
    user_id: str = Depends(request_user_id),
    days: int = 7,
) -> dict[str, Any]:
    """Success/failure counters per MCP tool over the last `days` — answers
    "since when is tool X failing" (last_ok / first_error / last_error)."""
    from telemetry import get_telemetry
    return await get_telemetry().tool_summary(days=days)
