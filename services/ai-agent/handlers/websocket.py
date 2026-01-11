"""
WebSocket Handler
=================
Handles WebSocket connections and chat messages.
"""

import uuid
import base64
from datetime import datetime
from typing import Dict, Any, List, Optional, Set

import pandas as pd
from fastapi import WebSocket
import structlog

from agent import MarketAgent, AgentStep

logger = structlog.get_logger(__name__)


class WebSocketHandler:
    """
    Handles WebSocket chat connections.
    
    Responsibilities:
    - Connection management
    - Message routing
    - Step forwarding to frontend
    - Result formatting
    """
    
    def __init__(self, agent: MarketAgent, redis_client=None):
        """
        Initialize handler.
        
        Args:
            agent: MarketAgent instance
            redis_client: Optional Redis for conversation persistence
        """
        self.agent = agent
        self.redis = redis_client
        self.active_connections: Dict[str, WebSocket] = {}
        self.chart_cache: Dict[str, bytes] = {}
    
    async def connect(self, websocket: WebSocket, client_id: str, market_context: Dict):
        """Accept connection and send initial state."""
        await websocket.accept()
        self.active_connections[client_id] = websocket
        
        logger.info("ws_connected", client_id=client_id)
        
        await websocket.send_json({
            "type": "connected",
            "client_id": client_id,
            "market_context": market_context,
            "version": "3.0"
        })
    
    def disconnect(self, client_id: str):
        """Remove connection."""
        self.active_connections.pop(client_id, None)
        logger.info("ws_disconnected", client_id=client_id)
    
    async def handle_message(
        self,
        websocket: WebSocket,
        client_id: str,
        data: Dict[str, Any],
        market_context: Dict
    ):
        """
        Route incoming message to appropriate handler.
        
        Args:
            websocket: Client connection
            client_id: Client identifier
            data: Message data
            market_context: Current market state
        """
        msg_type = data.get("type")
        
        if msg_type == "chat_message":
            await self._handle_chat(websocket, client_id, data, market_context)
        elif msg_type == "execute_workflow":
            await self._handle_workflow(websocket, client_id, data, market_context)
        elif msg_type == "ping":
            await websocket.send_json({"type": "pong"})
        elif msg_type == "clear_history":
            await self._clear_history(websocket, client_id, data)
    
    async def _handle_workflow(
        self,
        websocket: WebSocket,
        client_id: str,
        data: Dict[str, Any],
        market_context: Dict
    ):
        """Execute a visual workflow."""
        from handlers.workflow import handle_workflow_execution
        
        workflow = data.get("workflow")
        if not workflow:
            await websocket.send_json({"type": "error", "message": "No workflow provided"})
            return
        
        logger.info("workflow_execution_requested", 
                    client_id=client_id, 
                    workflow_id=workflow.get('id'),
                    node_count=len(workflow.get('nodes', [])))
        
        async def send_update(update: Dict):
            await websocket.send_json(update)
        
        try:
            await handle_workflow_execution(workflow, self.agent, send_update)
        except Exception as e:
            logger.error("workflow_execution_error", error=str(e))
            await websocket.send_json({
                "type": "workflow_error",
                "error": str(e)
            })
    
    async def _handle_chat(
        self,
        websocket: WebSocket,
        client_id: str,
        data: Dict[str, Any],
        market_context: Dict
    ):
        """Process chat message through agent."""
        content = data.get("content", "").strip()
        conversation_id = data.get("conversation_id", client_id)
        message_id = str(uuid.uuid4())
        sent_step_ids: Set[str] = set()
        
        if not content:
            await websocket.send_json({"type": "error", "message": "Empty message"})
            return
        
        # Ignore UI commands that shouldn't be processed
        ui_commands = [
            "show workflow results", "mostrar resultados", "expand", "collapse",
            "hide results", "ver resultados", "show results"
        ]
        if content.lower() in ui_commands:
            logger.debug("ignored_ui_command", command=content)
            return
        
        logger.info("chat_received", client_id=client_id, query=content[:100])
        
        # Step callback for real-time updates
        async def on_step(step: AgentStep):
            step_id = f"{message_id}-{step.id}"
            is_update = step_id in sent_step_ids
            sent_step_ids.add(step_id)
            
            await websocket.send_json({
                "type": "agent_step_update" if is_update else "agent_step",
                "message_id": message_id,
                "step_id": step_id if is_update else None,
                "step": None if is_update else {
                    "id": step_id,
                    "type": step.type,
                    "title": step.title,
                    "description": step.description,
                    "status": step.status,
                    "expandable": bool(step.details),
                    "details": step.details
                },
                "status": step.status if is_update else None,
                "description": step.description if is_update else None
            })
        
        # Response start
        await websocket.send_json({
            "type": "response_start",
            "message_id": message_id
        })
        
        try:
            # Get conversation history
            history = await self._get_history(conversation_id)
            
            # Process through agent
            result = await self.agent.process(
                query=content,
                market_context=market_context,
                conversation_history=history,
                on_step=on_step
            )
            
            # Save to history
            await self._save_message(conversation_id, "user", content)
            await self._save_message(conversation_id, "assistant", result.response)
            
            # Build outputs
            outputs = self._build_outputs(result, message_id)
            
            # Generate code representation from tools used
            code_lines = []
            for tool_call in getattr(result, 'tool_calls', []) or []:
                tool_name = tool_call.get('name', '')
                tool_args = tool_call.get('args', {})
                
                if tool_name == 'execute_analysis' and 'code' in tool_args:
                    # Show actual Python code for execute_analysis
                    code_lines.append(f"# execute_analysis - {tool_args.get('description', 'Custom analysis')}")
                    code_lines.append(tool_args['code'])
                else:
                    # Show tool call with args
                    args_str = ', '.join(f'{k}={repr(v)}' for k, v in tool_args.items())
                    code_lines.append(f"{tool_name}({args_str})")
            
            code_repr = "\n".join(code_lines) if code_lines else "# Direct response"
            
            # Send result
            await websocket.send_json({
                "type": "result",
                "message_id": message_id,
                "block_id": 1,
                "status": "success" if result.success else "error",
                "success": result.success,
                "code": code_repr,
                "outputs": outputs,
                "error": result.error,
                "execution_time_ms": int(result.execution_time * 1000),
                "timestamp": datetime.now().isoformat()
            })
            
            # Send text response
            if result.response and not outputs:
                await websocket.send_json({
                    "type": "assistant_text",
                    "message_id": message_id,
                    "delta": result.response
                })
            
        except Exception as e:
            logger.error("chat_error", error=str(e))
            await websocket.send_json({
                "type": "error",
                "message_id": message_id,
                "error": str(e)
            })
        
        finally:
            await websocket.send_json({
                "type": "response_end",
                "message_id": message_id
            })
    
    def _build_outputs(self, result, message_id: str) -> List[Dict[str, Any]]:
        """Convert agent result to frontend outputs."""
        outputs = []
        
        # Process DataFrames and special outputs
        if result.data:
            for name, value in result.data.items():
                if isinstance(value, pd.DataFrame) and not value.empty:
                    outputs.append({
                        "type": "table",
                        "title": self._format_title(name),
                        "columns": value.columns.tolist(),
                        "rows": self._clean_rows(value.head(100)),
                        "total": len(value)
                    })
                elif isinstance(value, dict):
                    # Special case: research_ticker results
                    if name == "research_ticker" and value.get("content"):
                        outputs.append({
                            "type": "research",
                            "title": f"Research: {value.get('ticker', 'Ticker')}",
                            "content": value.get("content", ""),
                            "citations": value.get("citations", []),
                            "inline_citations": value.get("inline_citations", [])
                        })
                    # Could be Plotly config or other data
                    elif "data" in value and "layout" in value:
                        outputs.append({
                            "type": "plotly_chart",
                            "title": self._format_title(name),
                            "plotly_config": value
                        })
        
        # Process charts
        for chart_name, chart_bytes in result.charts.items():
            cache_key = f"{message_id}_{chart_name}"
            self.chart_cache[cache_key] = chart_bytes
            outputs.append({
                "type": "chart",
                "title": self._format_title(chart_name),
                "chart_type": "image",
                "image_base64": base64.b64encode(chart_bytes).decode('utf-8')
            })
        
        # Add response text if present
        if result.response and not outputs:
            outputs.append({
                "type": "stats",
                "title": "Response",
                "content": result.response
            })
        
        return outputs
    
    def _format_title(self, name: str) -> str:
        """Convert snake_case to Title Case."""
        return name.replace('_', ' ').replace('-', ' ').title()
    
    def _clean_rows(self, df: pd.DataFrame) -> List[Dict]:
        """Convert DataFrame to JSON-safe rows."""
        import math
        
        def clean_value(v):
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                return None
            if pd.isna(v):
                return None
            if hasattr(v, 'isoformat'):
                return v.isoformat()
            if hasattr(v, 'item'):
                return v.item()
            return v
        
        return [{k: clean_value(v) for k, v in row.items()} 
                for row in df.to_dict('records')]
    
    async def _get_history(self, conversation_id: str) -> List[Dict]:
        """Get conversation history from Redis or memory."""
        if not self.redis:
            return []
        
        try:
            import json
            key = f"ai_agent:conversation:{conversation_id}"
            data = await self.redis.get(key)
            return json.loads(data) if data else []
        except:
            return []
    
    async def _save_message(self, conversation_id: str, role: str, content: str):
        """Save message to conversation history."""
        if not self.redis:
            return
        
        try:
            import json
            key = f"ai_agent:conversation:{conversation_id}"
            history = await self._get_history(conversation_id)
            history.append({"role": role, "content": content})
            
            # Keep last 10
            if len(history) > 10:
                history = history[-10:]
            
            await self.redis.set(key, json.dumps(history), ttl=3600)
        except:
            pass
    
    async def _clear_history(self, websocket: WebSocket, client_id: str, data: Dict):
        """Clear conversation history."""
        conversation_id = data.get("conversation_id", client_id)
        
        if self.redis:
            try:
                key = f"ai_agent:conversation:{conversation_id}"
                await self.redis.delete(key)
            except:
                pass
        
        await websocket.send_json({"type": "history_cleared"})
    
    async def broadcast(self, message: Dict):
        """Send message to all connected clients."""
        for ws in self.active_connections.values():
            try:
                await ws.send_json(message)
            except:
                pass
