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
            mode = message.get("mode", "auto")
            clarification_hint = message.get("clarification_hint", "")
            chart_context = message.get("chart_context", None)

            # ── Detect language from query ──
            language = _detect_language(query)

            # Acknowledge receipt
            await websocket.send_json({
                "type": "ack",
                "thread_id": thread_id,
            })

            # Build initial agent state (V5 parallel architecture)
            # If user chose a clarification option, prepend context
            effective_query = query
            if clarification_hint:
                effective_query = f"{query}\n[User clarified: {clarification_hint}]"

            initial_state: dict[str, Any] = {
                "messages": [{"role": "user", "content": effective_query}],
                "query": effective_query,
                "language": language,
                "mode": mode if mode in ("auto", "quick", "deep") else "auto",
                "intent": "",
                "tickers": [],
                "ticker_info": {},
                "plan": "",
                "active_agents": [],
                "agent_results": {},
                "charts": [],
                "tables": [],
                "market_context": market_context,
                "memory_context": [],
                "workflow_id": None,
                "trigger_context": None,
                "node_config": None,
                "final_response": "",
                "structured_response": None,
                "execution_metadata": {},
                "chart_context": chart_context,
                "clarification": None,
                "clarification_hint": clarification_hint,
                "error": None,
            }

            config = {"configurable": {"thread_id": thread_id}}

            # Stream graph execution events
            graph = get_graph()
            start_time = time.time()
            node_start_times: dict[str, float] = {}

            # Known graph node names for filtering astream_events
            _GRAPH_NODES = {
                "query_planner", "market_data",
                "news_events", "financial", "research", "code_exec",
                "screener", "backtest", "synthesizer",
                "dilution", "context_enricher",
            }

            try:
                async for event in graph.astream_events(initial_state, config=config, version="v2"):
                    kind = event.get("event", "")
                    node_name = event.get("name", "")

                    # Forward custom progress events (from adispatch_custom_event)
                    if kind == "on_custom_event":
                        evt_data = event.get("data", {})
                        if isinstance(evt_data, dict) and "message" in evt_data:
                            await websocket.send_json({
                                "type": "agent_progress",
                                "node": event.get("name", ""),
                                "message": evt_data["message"],
                                "timestamp": time.time(),
                            })
                        continue

                    # Only process events for our actual graph nodes
                    if node_name not in _GRAPH_NODES:
                        continue

                    if kind == "on_chain_start":
                        node_start_times[node_name] = time.time()
                        await websocket.send_json({
                            "type": "node_started",
                            "node": node_name,
                            "timestamp": time.time(),
                        })

                    elif kind == "on_chain_end":
                        node_start = node_start_times.pop(node_name, start_time)
                        node_elapsed_ms = int((time.time() - node_start) * 1000)

                        node_output = event.get("data", {}).get("output", {})
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

                        await websocket.send_json({
                            "type": "node_completed",
                            "node": node_name,
                            "elapsed_ms": node_elapsed_ms,
                            "preview": preview[:300],
                        })

                total_ms = int((time.time() - start_time) * 1000)

                # Get the final state to extract the response
                final_state = graph.get_state(config)
                clarification_data = None
                final_response = ""
                if hasattr(final_state, "values"):
                    clarification_data = final_state.values.get("clarification")
                    final_response = final_state.values.get("final_response", "")

                # If the planner requested clarification, send it instead
                if clarification_data and isinstance(clarification_data, dict):
                    await websocket.send_json({
                        "type": "clarification",
                        "message": clarification_data.get("message", ""),
                        "options": clarification_data.get("options", []),
                        "original_query": query,
                        "thread_id": thread_id,
                        "metadata": {
                            "total_elapsed_ms": total_ms,
                        },
                    })
                    continue

                # Check for structured outputs (backtest results, etc.)
                structured_outputs = []
                agent_results = {}
                structured_response = None
                if hasattr(final_state, "values"):
                    agent_results = final_state.values.get("agent_results", {})
                    structured_response = final_state.values.get("structured_response")

                bt_result = agent_results.get("backtest", {})
                if isinstance(bt_result, dict) and bt_result.get("status") == "success":
                    structured_outputs.append({
                        "type": "backtest",
                        "title": "Backtest Results",
                        "backtest_result": bt_result.get("backtest_result", {}),
                    })

                response_payload: dict[str, Any] = {
                    "type": "final_response",
                    "response": final_response,
                    "thread_id": thread_id,
                    "metadata": {
                        "total_elapsed_ms": total_ms,
                        "client_id": client_id,
                        "language": language,
                    },
                }

                if structured_response:
                    response_payload["structured_response"] = structured_response

                if structured_outputs:
                    response_payload["outputs"] = structured_outputs

                await websocket.send_json(response_payload)

                # ── Persist conversation to memory ──
                try:
                    memory = websocket.app.state.memory
                    # Build a brief summary of agent results for context
                    results_summary = {}
                    for agent_name, result in agent_results.items():
                        if isinstance(result, dict):
                            results_summary[agent_name] = {
                                k: v for k, v in result.items()
                                if k in ("status", "error", "tickers_found", "total_results")
                            }

                    await memory.store_conversation(
                        user_id="default",
                        thread_id=thread_id,
                        query=query,
                        response=final_response[:2000],
                        agent_results_summary=results_summary or None,
                        structured_response=structured_response,
                    )
                except Exception as mem_exc:
                    logger.warning(
                        "Failed to persist conversation for client %s: %s",
                        client_id, mem_exc,
                    )

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
