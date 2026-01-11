"""
REST API Handlers
=================
HTTP endpoints for the AI Agent service.
"""

import uuid
import json
from typing import Optional, Dict, Any, List
from datetime import datetime

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
import structlog

logger = structlog.get_logger(__name__)


class ChatMessage(BaseModel):
    """Chat request model."""
    content: str
    conversation_id: Optional[str] = None


class WorkflowNode(BaseModel):
    """Workflow node model."""
    id: str
    type: str
    position: Dict[str, float]
    data: Dict[str, Any]


class WorkflowEdge(BaseModel):
    """Workflow edge model."""
    id: str
    source: str
    target: str
    sourceHandle: Optional[str] = None
    targetHandle: Optional[str] = None


class Workflow(BaseModel):
    """Workflow model."""
    id: Optional[str] = None
    name: str
    description: Optional[str] = ""
    nodes: List[WorkflowNode]
    edges: List[WorkflowEdge]


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
    
    # Workflow endpoints
    workflows_store: Dict[str, Dict] = {}  # In-memory store (use Redis in production)
    
    @router.post("/api/workflows")
    async def create_workflow(workflow: Workflow):
        """Save a new workflow."""
        workflow_id = workflow.id or str(uuid.uuid4())
        now = datetime.now().isoformat()
        
        workflow_data = {
            "id": workflow_id,
            "name": workflow.name,
            "description": workflow.description,
            "nodes": [n.model_dump() for n in workflow.nodes],
            "edges": [e.model_dump() for e in workflow.edges],
            "createdAt": now,
            "updatedAt": now
        }
        
        workflows_store[workflow_id] = workflow_data
        logger.info("workflow_created", workflow_id=workflow_id, name=workflow.name)
        
        return workflow_data
    
    @router.get("/api/workflows")
    async def list_workflows():
        """List all saved workflows."""
        return list(workflows_store.values())
    
    @router.get("/api/workflows/{workflow_id}")
    async def get_workflow(workflow_id: str):
        """Get a specific workflow."""
        if workflow_id not in workflows_store:
            raise HTTPException(status_code=404, detail="Workflow not found")
        return workflows_store[workflow_id]
    
    @router.put("/api/workflows/{workflow_id}")
    async def update_workflow(workflow_id: str, workflow: Workflow):
        """Update an existing workflow."""
        if workflow_id not in workflows_store:
            raise HTTPException(status_code=404, detail="Workflow not found")
        
        existing = workflows_store[workflow_id]
        existing.update({
            "name": workflow.name,
            "description": workflow.description,
            "nodes": [n.model_dump() for n in workflow.nodes],
            "edges": [e.model_dump() for e in workflow.edges],
            "updatedAt": datetime.now().isoformat()
        })
        
        logger.info("workflow_updated", workflow_id=workflow_id)
        return existing
    
    @router.delete("/api/workflows/{workflow_id}")
    async def delete_workflow(workflow_id: str):
        """Delete a workflow."""
        if workflow_id not in workflows_store:
            raise HTTPException(status_code=404, detail="Workflow not found")
        
        del workflows_store[workflow_id]
        logger.info("workflow_deleted", workflow_id=workflow_id)
        return {"deleted": True}
    
    @router.post("/api/workflows/{workflow_id}/execute")
    async def execute_workflow(workflow_id: str):
        """Execute a saved workflow (HTTP, non-streaming)."""
        from handlers.workflow import WorkflowExecutor
        
        if workflow_id not in workflows_store:
            raise HTTPException(status_code=404, detail="Workflow not found")
        
        workflow = workflows_store[workflow_id]
        executor = WorkflowExecutor(agent, market_context)
        
        try:
            result = await executor.execute(workflow)
            return result
        except Exception as e:
            logger.error("workflow_execution_error", error=str(e))
            raise HTTPException(status_code=500, detail=str(e))
    
    @router.post("/api/workflow-execute")
    async def execute_adhoc_workflow(workflow: Workflow):
        """Execute a workflow directly without saving (ad-hoc)."""
        from handlers.workflow import WorkflowExecutor
        
        workflow_data = {
            "id": workflow.id or f"adhoc-{uuid.uuid4()}",
            "name": workflow.name,
            "nodes": [n.model_dump() for n in workflow.nodes],
            "edges": [e.model_dump() for e in workflow.edges]
        }
        
        executor = WorkflowExecutor(agent, market_context)
        
        try:
            result = await executor.execute(workflow_data)
            return result
        except Exception as e:
            logger.error("adhoc_workflow_error", error=str(e))
            raise HTTPException(status_code=500, detail=str(e))
    
    @router.get("/api/workflow-templates")
    async def get_workflow_templates():
        """Get predefined workflow templates."""
        return [
            {
                "id": "insider-activity-scan",
                "name": "Insider Activity Scan",
                "description": "Track large unusual activity and insider transactions",
                "category": "screening",
                "nodes": [
                    {"id": "scanner-1", "type": "scanner", "position": {"x": 50, "y": 200},
                     "data": {"label": "Market Scanner", "category": "scanner",
                              "config": {"category": "all"}}},
                    {"id": "screener-1", "type": "screener", "position": {"x": 300, "y": 200},
                     "data": {"label": "Volume Filter", "category": "filter",
                              "config": {"min_volume": 1000000}}},
                    {"id": "insiders-1", "type": "insiders", "position": {"x": 550, "y": 200},
                     "data": {"label": "Insider Filings", "category": "insider",
                              "config": {"min_value": 100000}}},
                    {"id": "display-1", "type": "display", "position": {"x": 800, "y": 200},
                     "data": {"label": "Display Results", "category": "output",
                              "config": {"title": "Insider Activity"}}}
                ],
                "edges": [
                    {"id": "e1", "source": "scanner-1", "target": "screener-1"},
                    {"id": "e2", "source": "screener-1", "target": "insiders-1"},
                    {"id": "e3", "source": "insiders-1", "target": "display-1"}
                ]
            },
            {
                "id": "synthetic-sector-analysis",
                "name": "Synthetic Sector Analysis",
                "description": "Classify tickers into thematic sectors and analyze top performers",
                "category": "analysis",
                "nodes": [
                    {"id": "scanner-1", "type": "scanner", "position": {"x": 50, "y": 200},
                     "data": {"label": "Market Scanner", "category": "scanner",
                              "config": {"category": "winners"}}},
                    {"id": "synthetic-1", "type": "synthetic_sectors", "position": {"x": 300, "y": 200},
                     "data": {"label": "Synthetic ETFs", "category": "ai",
                              "config": {"date": "today"}}},
                    {"id": "research-1", "type": "ai_research", "position": {"x": 550, "y": 200},
                     "data": {"label": "AI Research", "category": "research",
                              "config": {}}},
                    {"id": "display-1", "type": "display", "position": {"x": 800, "y": 200},
                     "data": {"label": "Sector Report", "category": "output",
                              "config": {"title": "Sector Analysis"}}}
                ],
                "edges": [
                    {"id": "e1", "source": "scanner-1", "target": "synthetic-1"},
                    {"id": "e2", "source": "synthetic-1", "target": "research-1"},
                    {"id": "e3", "source": "research-1", "target": "display-1"}
                ]
            },
            {
                "id": "sec-catalyst-detector",
                "name": "SEC Catalyst Detector",
                "description": "Find stocks with recent SEC filings and related news",
                "category": "research",
                "nodes": [
                    {"id": "scanner-1", "type": "scanner", "position": {"x": 50, "y": 200},
                     "data": {"label": "Market Scanner", "category": "scanner",
                              "config": {"category": "gappers"}}},
                    {"id": "sec-1", "type": "sec_filings", "position": {"x": 300, "y": 100},
                     "data": {"label": "SEC Filings", "category": "sec",
                              "config": {"form_type": ["8-K", "4"], "days_back": 3}}},
                    {"id": "news-1", "type": "news", "position": {"x": 300, "y": 300},
                     "data": {"label": "News Feed", "category": "news",
                              "config": {"hours_back": 24}}},
                    {"id": "display-1", "type": "display", "position": {"x": 600, "y": 200},
                     "data": {"label": "Catalyst Report", "category": "output",
                              "config": {"title": "Catalysts Found"}}}
                ],
                "edges": [
                    {"id": "e1", "source": "scanner-1", "target": "sec-1"},
                    {"id": "e2", "source": "scanner-1", "target": "news-1"},
                    {"id": "e3", "source": "sec-1", "target": "display-1"},
                    {"id": "e4", "source": "news-1", "target": "display-1"}
                ]
            },
            {
                "id": "momentum-breakout",
                "name": "Momentum Breakout Scanner",
                "description": "Find high-momentum stocks with pattern recognition",
                "category": "screening",
                "nodes": [
                    {"id": "scanner-1", "type": "scanner", "position": {"x": 50, "y": 200},
                     "data": {"label": "Market Scanner", "category": "scanner",
                              "config": {"category": "winners"}}},
                    {"id": "top-movers-1", "type": "top_movers", "position": {"x": 300, "y": 200},
                     "data": {"label": "Top Movers", "category": "scanner",
                              "config": {"direction": "gainers", "limit": 50}}},
                    {"id": "analysis-1", "type": "ai_analysis", "position": {"x": 550, "y": 200},
                     "data": {"label": "AI Analysis", "category": "ai",
                              "config": {"prompt": "Analyze momentum patterns"}}},
                    {"id": "display-1", "type": "display", "position": {"x": 800, "y": 200},
                     "data": {"label": "Breakout Alerts", "category": "output",
                              "config": {"title": "Momentum Breakouts"}}}
                ],
                "edges": [
                    {"id": "e1", "source": "scanner-1", "target": "top-movers-1"},
                    {"id": "e2", "source": "top-movers-1", "target": "analysis-1"},
                    {"id": "e3", "source": "analysis-1", "target": "display-1"}
                ]
            }
        ]
    
    return router
