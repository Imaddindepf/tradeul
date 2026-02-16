"""
WebSocket Handler - Real-time streaming chat interface.

Receives JSON messages from the client, invokes the LangGraph orchestrator,
and streams intermediate node events + the final response back via WebSocket.
"""
from __future__ import annotations

import json
import logging
import re
import time
import traceback
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


# ── Language detection ──────────────────────────────────────────────
_SPANISH_MARKERS = re.compile(
    r'\b(?:de|del|la|el|los|las|que|por|para|con|una|como|más|hoy|'
    r'dame|muestra|quiero|busca|analiza|cuáles|mejores|peores|'
    r'acciones|mercado|ganancias|perdedoras|ganadoras|volumen|'
    r'qué|cómo|cuánto|dónde|viernes|lunes|martes|miércoles|jueves|'
    r'sábado|domingo|ayer|semana|mes|año|últimos?|primeros?|'
    r'premarket|después|antes|cierre|apertura)\b',
    re.IGNORECASE,
)


def _detect_language(text: str) -> str:
    """Detect if the query is in Spanish or English.
    Returns 'es' or 'en'."""
    matches = _SPANISH_MARKERS.findall(text)
    # If 2+ Spanish markers found, it's Spanish
    return "es" if len(matches) >= 2 else "en"


async def handle_websocket(websocket: WebSocket, client_id: str) -> None:
    """Handle a single WebSocket connection for real-time chat.

    Protocol (client -> server):
        {
            "query": "What is happening with $AAPL?",
            "thread_id": "optional-thread-id",
            "market_context": { ... optional context ... }
        }

    Protocol (server -> client):
        {"type": "ack",            "thread_id": "..."}
        {"type": "node_started",   "node": "supervisor", "timestamp": ...}
        {"type": "node_completed", "node": "supervisor", "elapsed_ms": ..., "preview": "..."}
        ...
        {"type": "final_response", "response": "...", "metadata": {...}}
        {"type": "error",          "message": "..."}
    """
    await websocket.accept()
    logger.info("WebSocket connected: client_id=%s", client_id)

    # Lazy import to avoid circular dependency at module level
    from graph.orchestrator import get_graph

    try:
        while True:
            raw = await websocket.receive_text()

            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid JSON payload.",
                })
                continue

            query = message.get("query", "").strip()
            if not query:
                # Empty query = heartbeat/ping, ignore silently
                continue

            thread_id = message.get("thread_id", f"{client_id}-{int(time.time())}")
            market_context = message.get("market_context", {})

            # ── Detect language from query ──
            language = _detect_language(query)

            # Acknowledge receipt
            await websocket.send_json({
                "type": "ack",
                "thread_id": thread_id,
            })

            # Build initial agent state
            initial_state: dict[str, Any] = {
                "messages": [{"role": "user", "content": query}],
                "query": query,
                "language": language,
                "tickers": [],
                "plan": "",
                "active_agents": [],
                "current_agent": "",
                "agent_results": {},
                "charts": [],
                "tables": [],
                "market_context": market_context,
                "memory_context": [],
                "workflow_id": None,
                "trigger_context": None,
                "node_config": None,
                "final_response": "",
                "execution_metadata": {},
                "iteration_count": 0,
                "error": None,
            }

            config = {"configurable": {"thread_id": thread_id}}

            # Stream graph execution events
            graph = get_graph()
            start_time = time.time()

            try:
                async for event in graph.astream(initial_state, config=config):
                    # Each event is a dict with the node name as key
                    for node_name, node_output in event.items():
                        node_ts = time.time()

                        # Send node_started
                        await websocket.send_json({
                            "type": "node_started",
                            "node": node_name,
                            "timestamp": node_ts,
                        })

                        # Build a preview of the node output
                        preview = ""
                        if isinstance(node_output, dict):
                            ar = node_output.get("agent_results", {})
                            if ar:
                                first_key = next(iter(ar), None)
                                if first_key:
                                    result = ar[first_key]
                                    if isinstance(result, dict) and "error" in result:
                                        preview = f"Error: {result['error']}"
                                    elif isinstance(result, dict):
                                        preview = f"Keys: {list(result.keys())}"
                                    else:
                                        preview = str(result)[:200]

                        elapsed_node_ms = int((node_ts - start_time) * 1000)

                        # Send node_completed
                        await websocket.send_json({
                            "type": "node_completed",
                            "node": node_name,
                            "elapsed_ms": elapsed_node_ms,
                            "preview": preview[:300],
                        })

                total_ms = int((time.time() - start_time) * 1000)

                # Get the final state to extract the response
                final_state = graph.get_state(config)
                final_response = ""
                if hasattr(final_state, "values"):
                    final_response = final_state.values.get("final_response", "")

                await websocket.send_json({
                    "type": "final_response",
                    "response": final_response,
                    "thread_id": thread_id,
                    "metadata": {
                        "total_elapsed_ms": total_ms,
                        "client_id": client_id,
                        "language": language,
                    },
                })

            except Exception as exc:
                logger.error(
                    "Graph execution error for client %s: %s\n%s",
                    client_id, exc, traceback.format_exc(),
                )
                await websocket.send_json({
                    "type": "error",
                    "message": f"Graph execution failed: {exc}",
                })

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: client_id=%s", client_id)
    except Exception as exc:
        logger.error(
            "WebSocket error for client %s: %s\n%s",
            client_id, exc, traceback.format_exc(),
        )
