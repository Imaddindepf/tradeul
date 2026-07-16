"""
WebSocket Handler - Real-time streaming chat interface.

Receives JSON messages from the client, invokes the LangGraph orchestrator,
and streams intermediate node events + the final response back via WebSocket.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import traceback
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

logger = logging.getLogger(__name__)

# Heartbeat cadence while a long node (research/synthesizer) runs with no
# streamed events. Must stay well under the proxy read/write timeout so the
# connection is never seen as idle. Caddy/LB timeouts are 120s → 15s is safe.
_HEARTBEAT_INTERVAL_S = 15.0


def _ws_alive(websocket: WebSocket) -> bool:
    """True only when the socket can still accept sends."""
    return (
        websocket.application_state == WebSocketState.CONNECTED
        and websocket.client_state == WebSocketState.CONNECTED
    )


async def _safe_send(websocket: WebSocket, payload: dict) -> bool:
    """Send JSON only if the connection is still open.

    Returns False when the peer/proxy already closed the socket, so callers can
    stop streaming instead of raising 'websocket.send after close'.
    """
    if not _ws_alive(websocket):
        return False
    try:
        await websocket.send_json(payload)
        return True
    except (WebSocketDisconnect, RuntimeError) as exc:
        logger.info("WS send skipped (connection closed): %s", exc)
        return False


async def _heartbeat(websocket: WebSocket, interval: float = _HEARTBEAT_INTERVAL_S) -> None:
    """Keepalive frames so long silent nodes don't trip proxy idle timeouts."""
    try:
        while True:
            await asyncio.sleep(interval)
            if not await _safe_send(websocket, {"type": "keepalive", "timestamp": time.time()}):
                return
    except asyncio.CancelledError:
        return
    except Exception:  # noqa: BLE001
        return


# Latest live socket per client_id. The frontend keeps its client_id across
# reconnects, so when a background tab drops the socket mid-run we can still
# deliver the finished result to the client's NEW socket.
_ACTIVE_SOCKETS: dict[str, WebSocket] = {}


async def _deliver(websocket: WebSocket, client_id: str, payload: dict) -> bool:
    """Send to the original socket, falling back to the client's newest one.

    Covers the background-tab scenario: browser drops the socket while the
    agent works, the tab reconnects with the same client_id, and the result
    arrives on the fresh connection instead of being lost.
    """
    if await _safe_send(websocket, payload):
        return True
    current = _ACTIVE_SOCKETS.get(client_id)
    if current is not None and current is not websocket:
        if await _safe_send(current, payload):
            logger.info("Delivered %s to reconnected socket (client_id=%s)",
                        payload.get("type"), client_id)
            return True
    return False


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


# Etapas mostradas en vivo mientras Opus trabaja (no son medibles, son guía UX).
_BRIEF_STAGES = [
    "Leyendo la noticia que ya tenemos…",
    "Consultando datos internos de Tradeul…",
    "Buscando contexto y antecedentes en la web…",
    "Evaluando qué cambia en el fundamento…",
    "Redactando el brief…",
]
_FOLLOWUP_STAGES = [
    "Repasando el contexto del hilo…",
    "Buscando lo que haga falta…",
    "Redactando la respuesta…",
]


async def _progress_pump(websocket: WebSocket, stages: list[str], interval: float = 9.0) -> None:
    """Emite mensajes de progreso escalonados sobre el step en curso."""
    i = 0
    try:
        while True:
            msg = stages[min(i, len(stages) - 1)]
            if not await _safe_send(websocket, {
                "type": "agent_progress",
                "node": "context_brief",
                "message": msg,
                "timestamp": time.time(),
            }):
                return
            i += 1
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        return
    except Exception:  # noqa: BLE001
        return


async def _handle_context_brief(
    websocket: WebSocket, client_id: str, message: dict[str, Any],
    thread_id: str, query: str,
) -> None:
    """Route a 'context brief' request to the ai-news-brief service (Opus 4.8).

    First turn -> full fundamental brief of the news.
    Follow-up (thread already has history) -> conversational answer, same engine,
    keeping the original news as context.

    Persists each turn to the same Redis memory the normal agent uses, so it
    shows up in conversation history and supports follow-ups.
    """
    from clients import news_brief_client

    memory = getattr(websocket.app.state, "memory", None)

    clean_q = query
    if clean_q.startswith("/contexto"):
        clean_q = clean_q[len("/contexto"):].strip()

    # News context from the frontend, or build a minimal one from the text.
    news_ctx = message.get("news_context") or {}
    if not news_ctx.get("text"):
        tickers = re.findall(r"\$([A-Z]{1,5})", clean_q or query)
        news_ctx = {"text": clean_q or query, "tickers": tickers}

    # Prior turns of this thread (for follow-ups, same engine + context).
    history: list[dict[str, str]] = []
    if memory:
        try:
            past = await memory.get_conversation_history("default", thread_id, limit=8)
            for turn in past:
                q = turn.get("query")
                r = turn.get("response")
                if q:
                    history.append({"role": "user", "content": q})
                if r:
                    history.append({"role": "assistant", "content": r})
        except Exception as exc:  # noqa: BLE001
            logger.warning("context_brief history load failed: %s", exc)

    is_followup = len(history) > 0

    # Abre un "step" visible para que el usuario vea el progreso en vivo.
    await _safe_send(websocket, {
        "type": "node_started",
        "node": "context_brief",
        "timestamp": time.time(),
    })

    stages = _FOLLOWUP_STAGES if is_followup else _BRIEF_STAGES
    pump = asyncio.create_task(_progress_pump(websocket, stages))

    start_time = time.time()
    try:
        if is_followup:
            result = await news_brief_client.followup(news_ctx, history, clean_q or query)
        else:
            result = await news_brief_client.generate_brief(news_ctx)
    except Exception as exc:  # noqa: BLE001
        logger.error("context_brief failed client=%s: %s", client_id, exc)
        pump.cancel()
        await asyncio.gather(pump, return_exceptions=True)
        await _safe_send(websocket, {
            "type": "node_error",
            "node": "context_brief",
            "error": str(exc),
        })
        await _safe_send(websocket, {
            "type": "error",
            "message": f"El brief de contexto falló: {exc}",
        })
        return

    pump.cancel()
    await asyncio.gather(pump, return_exceptions=True)

    brief_md = result.get("brief_markdown") or "(sin contenido)"
    total_ms = int((time.time() - start_time) * 1000)

    # Persistir ANTES de intentar entregar: si el cliente se fue (pestaña en
    # segundo plano, red móvil), el brief no se pierde — al reconectar y
    # repreguntar en el mismo hilo se responde como follow-up con este contexto.
    if memory:
        try:
            await memory.store_conversation(
                user_id="default",
                thread_id=thread_id,
                query=(clean_q or query)[:500],
                response=brief_md[:15000],
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("context_brief persist failed: %s", exc)

    if not _ws_alive(websocket):
        logger.info(
            "context_brief: client %s socket died mid-run (thread=%s); "
            "brief persisted (%d chars), trying reconnected socket",
            client_id, thread_id, len(brief_md),
        )

    # Resumen legible de lo que se usó (sin revelar proveedores).
    tools_used = result.get("tools_used", []) or []
    sources = result.get("sources", []) or []
    _tool_labels = {
        "get_company_fundamentals": "fundamentales",
        "get_analyst_ratings": "analistas",
        "get_cash_and_dilution": "caja/dilución",
    }
    used_labels = [_tool_labels.get(t, t) for t in dict.fromkeys(tools_used)]
    summary_parts = []
    if used_labels:
        summary_parts.append("Datos internos: " + ", ".join(used_labels))
    summary_parts.append(f"{len(sources)} fuente(s) web")
    completion_preview = " · ".join(summary_parts)

    await _deliver(websocket, client_id, {
        "type": "node_completed",
        "node": "context_brief",
        "elapsed_ms": total_ms,
        "preview": completion_preview,
    })

    delivered = await _deliver(websocket, client_id, {
        "type": "final_response",
        "response": brief_md,
        "thread_id": thread_id,
        "metadata": {
            "total_elapsed_ms": total_ms,
            "client_id": client_id,
            "mode": "context_brief",
            "sources": sources,
            "tools_used": tools_used,
        },
    })
    if not delivered:
        logger.info(
            "context_brief: no live socket for client %s (thread=%s); "
            "brief remains in thread memory", client_id, thread_id,
        )


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
    # Register as the latest live socket for this client (reconnect delivery).
    _ACTIVE_SOCKETS[client_id] = websocket

    # Lazy import to avoid circular dependency at module level
    from graph.orchestrator import get_graph

    try:
        while True:
            if not _ws_alive(websocket):
                logger.info("WebSocket no longer connected: client_id=%s", client_id)
                break
            raw = await websocket.receive_text()

            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await _safe_send(websocket, {
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
            if not await _safe_send(websocket, {
                "type": "ack",
                "thread_id": thread_id,
            }):
                continue

            # ── Context Brief mode: route to ai-news-brief (Opus), bypass graph ──
            if mode == "context_brief" or query.startswith("/contexto"):
                await _handle_context_brief(websocket, client_id, message, thread_id, query)
                continue

            # Build initial agent state (V5 parallel architecture)
            # If user chose a clarification option, prepend context
            effective_query = query
            if clarification_hint:
                effective_query = f"{query}\n[User clarified: {clarification_hint}]"

            # ── Conversational memory: recent turns + cross-thread recall ──
            memory_context: list[dict[str, Any]] = []
            memory = getattr(websocket.app.state, "memory", None)
            if memory:
                try:
                    memory_context = await memory.build_memory_context(
                        user_id="default", thread_id=thread_id, query=query,
                    )
                except Exception as mem_exc:
                    logger.warning("memory_context load failed: %s", mem_exc)

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
                "memory_context": memory_context,
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
                "dilution", "strategy_scanner", "context_enricher",
            }

            # Keepalive runs alongside the stream so long silent nodes
            # (research/synthesizer can be 30-90s) never trip the proxy idle
            # timeout and drop the socket mid-answer.
            heartbeat_task = asyncio.create_task(_heartbeat(websocket))
            # When the socket drops mid-run (background tab), we keep the graph
            # running: stop streaming events, finish the work, then deliver the
            # final response to the client's reconnected socket via _deliver().
            client_gone = False
            try:
                async for event in graph.astream_events(initial_state, config=config, version="v2"):
                    if client_gone:
                        continue  # let the graph finish; skip event streaming

                    kind = event.get("event", "")
                    node_name = event.get("name", "")

                    # Forward custom progress events (from adispatch_custom_event)
                    if kind == "on_custom_event":
                        evt_data = event.get("data", {})
                        if isinstance(evt_data, dict) and "message" in evt_data:
                            if not await _safe_send(websocket, {
                                "type": "agent_progress",
                                "node": event.get("name", ""),
                                "message": evt_data["message"],
                                "timestamp": time.time(),
                            }):
                                client_gone = True
                        continue

                    # Only process events for our actual graph nodes
                    if node_name not in _GRAPH_NODES:
                        continue

                    if kind == "on_chain_start":
                        node_start_times[node_name] = time.time()
                        if not await _safe_send(websocket, {
                            "type": "node_started",
                            "node": node_name,
                            "timestamp": time.time(),
                        }):
                            client_gone = True

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

                        if not await _safe_send(websocket, {
                            "type": "node_completed",
                            "node": node_name,
                            "elapsed_ms": node_elapsed_ms,
                            "preview": preview[:300],
                        }):
                            client_gone = True
            finally:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass

            if client_gone:
                logger.info(
                    "WS client gone during graph exec (client_id=%s, thread=%s); "
                    "will deliver final response to reconnected socket if any.",
                    client_id, thread_id,
                )

            try:
                total_ms = int((time.time() - start_time) * 1000)

                # Get the final state to extract the response
                # (aget_state: required with the async Postgres checkpointer)
                final_state = await graph.aget_state(config)
                clarification_data = None
                final_response = ""
                if hasattr(final_state, "values"):
                    clarification_data = final_state.values.get("clarification")
                    final_response = final_state.values.get("final_response", "")

                # If the planner requested clarification, send it instead
                if clarification_data and isinstance(clarification_data, dict):
                    await _deliver(websocket, client_id, {
                        "type": "clarification",
                        "message": clarification_data.get("message", ""),
                        "options": clarification_data.get("options", []),
                        "original_query": query,
                        "thread_id": thread_id,
                        "metadata": {
                            "total_elapsed_ms": total_ms,
                        },
                    })
                    if client_gone:
                        break  # this handler's socket is dead; its loop is done
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

                await _deliver(websocket, client_id, response_payload)

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

                    turn_tickers: list[str] = []
                    turn_intent = ""
                    if hasattr(final_state, "values"):
                        turn_tickers = final_state.values.get("tickers", []) or []
                        turn_intent = final_state.values.get("intent", "") or ""

                    await memory.store_conversation(
                        user_id="default",
                        thread_id=thread_id,
                        query=query,
                        # Full response (final_response is already capped at
                        # ~15k). Truncating shorter broke tables/rows when the
                        # session history was reloaded in the UI.
                        response=final_response[:15000],
                        agent_results_summary=results_summary or None,
                        structured_response=structured_response,
                        tickers=turn_tickers,
                        intent=turn_intent,
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
                await _safe_send(websocket, {
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
    finally:
        # Deregister only if a newer connection hasn't replaced this one.
        if _ACTIVE_SOCKETS.get(client_id) is websocket:
            _ACTIVE_SOCKETS.pop(client_id, None)
