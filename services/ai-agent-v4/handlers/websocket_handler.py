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
import uuid
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from handlers.node_summary import summarize_node_output
from runs.artifacts import blocks_to_artifacts, build_artifacts
from runs.store import get_run_store

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


async def _heartbeat(
    websocket: WebSocket,
    interval: float = _HEARTBEAT_INTERVAL_S,
    client_id: str | None = None,
) -> None:
    """Keepalive frames so long silent nodes don't trip proxy idle timeouts.

    When client_id is set, deliver to the client's newest socket (reconnect-safe).
    """
    try:
        while True:
            await asyncio.sleep(interval)
            payload = {"type": "keepalive", "timestamp": time.time()}
            if client_id:
                # A failed tick may just be the 1-5s reconnect window; keep
                # trying — the next tick lands on the client's new socket.
                await _deliver(websocket, client_id, payload)
            elif not await _safe_send(websocket, payload):
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


# Etapas mostradas en vivo mientras Opus trabaja (no son medibles, son guía UX).
_BRIEF_STAGES = [
    "Reading the news we already have…",
    "Querying Tradeul internal data…",
    "Searching the web for context and background…",
    "Assessing what changes in the fundamentals…",
    "Writing the brief…",
]
_FOLLOWUP_STAGES = [
    "Reviewing the thread context…",
    "Fetching whatever is missing…",
    "Writing the response…",
]


async def _progress_pump(
    websocket: WebSocket, client_id: str, stages: list[str], interval: float = 9.0,
) -> None:
    """Emite progreso escalonado; usa _deliver para seguir al socket reconectado."""
    i = 0
    try:
        while True:
            msg = stages[min(i, len(stages) - 1)]
            if not await _deliver(websocket, client_id, {
                "type": "agent_progress",
                "node": "context_brief",
                "message": msg,
                "timestamp": time.time(),
            }):
                # Socket muerto Y sin reconexión — no abortamos el brief
                # (sigue en background); solo paramos de spamear progreso.
                return
            i += 1
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        return
    except Exception:  # noqa: BLE001
        return


async def _deliver_with_retry(
    websocket: WebSocket, client_id: str, payload: dict,
    attempts: int = 8, delay_s: float = 2.0,
) -> bool:
    """Entrega con reintentos: el cliente suele reconectar en 1–5s tras un drop."""
    for i in range(attempts):
        if await _deliver(websocket, client_id, payload):
            if i > 0:
                logger.info(
                    "Delivered %s to client %s on retry %d",
                    payload.get("type"), client_id, i,
                )
            return True
        await asyncio.sleep(delay_s)
    return False


async def _handle_context_brief(
    websocket: WebSocket, client_id: str, message: dict[str, Any],
    thread_id: str, query: str, user_id: str, run_id: str = "",
) -> tuple[bool, dict[str, Any] | None]:
    """Route a 'context brief' FIRST TURN to the ai-news-brief service (Opus).

    First turn -> full fundamental brief of the news, handled here directly
    (generating the brief needs no planning; keeps the staged-progress UX).

    Follow-ups (thread already has history) are NOT handled here since Fase 3b:
    they enter the graph, where the planner sees the `news_brief` agent
    alongside the live agents and decides — brief engine alone, live data
    alone, or both in parallel (the hybrid the old binary LIVE/CHAT router
    in agents/brief_router.py could not express; that module is now obsolete).

    Returns (handled, brief_state):
      - (True, None): turn fully handled here.
      - (False, {"news_context", "brief_history"}): caller must run the graph
        with these fields in the initial state.

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
            past = await memory.get_conversation_history(user_id, thread_id, limit=8)
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

    # Fase 3b: TODO follow-up de brief entra al grafo — el planner decide
    # entre news_brief (conversacional), agentes live (datos de mercado) o
    # ambos en paralelo. Devolvemos la noticia + historial ya cargados para
    # que el caller los inyecte en el estado inicial del grafo.
    if is_followup:
        logger.info(
            "context_brief handoff → graph (follow-up on brief thread) "
            "thread=%s query=%r", thread_id, (clean_q or query)[:80],
        )
        return False, {"news_context": news_ctx, "brief_history": history}

    # Abre un "step" visible para que el usuario vea el progreso en vivo.
    await _deliver(websocket, client_id, {
        "type": "node_started",
        "node": "context_brief",
        "timestamp": time.time(),
    })

    stages = _FOLLOWUP_STAGES if is_followup else _BRIEF_STAGES
    # Keepalive + progress: Opus puede tardar 30–180s; sin frames el proxy
    # corta el socket y el frontend dispara "La solicitud tardó demasiado".
    heartbeat_task = asyncio.create_task(_heartbeat(websocket, client_id=client_id))
    pump = asyncio.create_task(_progress_pump(websocket, client_id, stages))

    start_time = time.time()
    try:
        if is_followup:
            result = await news_brief_client.followup(news_ctx, history, clean_q or query)
        else:
            result = await news_brief_client.generate_brief(news_ctx)
    except Exception as exc:  # noqa: BLE001
        logger.error("context_brief failed client=%s: %s", client_id, exc)
        pump.cancel()
        heartbeat_task.cancel()
        await asyncio.gather(pump, heartbeat_task, return_exceptions=True)
        await _deliver(websocket, client_id, {
            "type": "node_error",
            "node": "context_brief",
            "error": str(exc),
        })
        await _deliver(websocket, client_id, {
            "type": "error",
            "message": f"Context brief failed: {exc}",
        })
        if run_id:
            await get_run_store().finish_run(run_id, "error")
        return True, None

    pump.cancel()
    heartbeat_task.cancel()
    await asyncio.gather(pump, heartbeat_task, return_exceptions=True)

    brief_md = result.get("brief_markdown") or "(sin contenido)"
    total_ms = int((time.time() - start_time) * 1000)

    # Persistir ANTES de intentar entregar: si el cliente se fue (pestaña en
    # segundo plano, red móvil), el brief no se pierde — al reconectar y
    # repreguntar en el mismo hilo se responde como follow-up con este contexto.
    if memory:
        try:
            await memory.store_conversation(
                user_id=user_id,
                thread_id=thread_id,
                query=(clean_q or query)[:500],
                response=brief_md[:15000],
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("context_brief persist failed: %s", exc)

    if not _ws_alive(websocket):
        logger.info(
            "context_brief: client %s socket died mid-run (thread=%s); "
            "brief persisted (%d chars), retrying delivery to reconnected socket",
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

    await _deliver_with_retry(websocket, client_id, {
        "type": "node_completed",
        "node": "context_brief",
        "elapsed_ms": total_ms,
        "preview": completion_preview,
    })

    delivered = await _deliver_with_retry(websocket, client_id, {
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
            "context_brief: no live socket for client %s (thread=%s) after retries; "
            "brief remains in thread memory", client_id, thread_id,
        )

    # Cierre del run + artifact auditable (antes los runs de brief quedaban
    # en estado "running" para siempre y sin rastro inspeccionable).
    if run_id:
        store = get_run_store()
        await store.save_artifacts(run_id, "context_brief", [{
            "kind": "markdown",
            "title": "Brief follow-up" if is_followup else "Context brief",
            "markdown": brief_md[:20000],
            "sources": sources,
            "tools_used": tools_used,
            "elapsed_ms": total_ms,
            "engine": "ai-news-brief",
        }])
        await store.finish_run(run_id, "complete")

    return True, None


async def handle_websocket(
    websocket: WebSocket, client_id: str, user_id: str,
) -> None:
    """Handle a single WebSocket connection for real-time chat.

    ``user_id`` is the authenticated Clerk sub — every persisted artifact of
    the conversation (memory, runs, alert specs) is scoped to it.

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
    # SECURITY: the reconnect-delivery table is keyed by client_id, which comes
    # from the client-controlled URL path. Namespacing it with the authenticated
    # user_id ensures a colliding/forged client_id from user B can never resolve
    # to user A's socket (no cross-tenant response delivery). All helpers take
    # this composite as their opaque `client_id` key.
    client_id = f"{user_id}:{client_id}"
    logger.info("WebSocket connected: client_id=%s", client_id)
    # Register as the latest live socket for this client (reconnect delivery).
    _ACTIVE_SOCKETS[client_id] = websocket

    # Lazy import to avoid circular dependency at module level
    from graph.orchestrator import get_graph
    from limits import check_rate, clamp_query, RateLimitExceeded

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

            # ── Input bound + per-user throttle (expensive multi-LLM service) ──
            query, size_err = clamp_query(query)
            if size_err:
                await _safe_send(websocket, {"type": "error", "message": size_err})
                continue
            _memory = getattr(websocket.app.state, "memory", None)
            if _memory is not None:
                try:
                    await check_rate(await _memory._get_redis(), user_id)
                except RateLimitExceeded as rl:
                    await _safe_send(websocket, {
                        "type": "error",
                        "message": f"You're going too fast. Retry in {rl.retry_after}s.",
                        "retry_after": rl.retry_after,
                    })
                    continue

            thread_id = message.get("thread_id", f"{client_id}-{int(time.time())}")
            market_context = message.get("market_context", {})
            mode = message.get("mode", "auto")
            clarification_hint = message.get("clarification_hint", "")
            chart_context = message.get("chart_context", None)

            # ── Run persistido: cada query es un run con artifacts completos
            # (inspector de nodo). run_id viaja en ack y en cada node_completed.
            run_id = uuid.uuid4().hex[:16]
            run_store = get_run_store()
            asyncio.create_task(run_store.create_run(
                run_id, user_id=user_id, thread_id=thread_id, query=query,
            ))

            # Acknowledge receipt
            if not await _safe_send(websocket, {
                "type": "ack",
                "thread_id": thread_id,
                "run_id": run_id,
            }):
                continue

            # ── Context Brief mode ──
            # Primer turno: brief completo vía ai-news-brief (Opus), directo.
            # Follow-ups (Fase 3b): entran al grafo con news_context +
            # brief_history en el estado; el planner elige entre news_brief,
            # agentes live, o ambos en paralelo.
            brief_state: dict[str, Any] | None = None
            if mode == "context_brief" or query.startswith("/contexto"):
                handled, brief_state = await _handle_context_brief(
                    websocket, client_id, message, thread_id, query, user_id,
                    run_id=run_id,
                )
                if handled:
                    continue
                if query.startswith("/contexto"):
                    query = query[len("/contexto"):].strip() or query

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
                        user_id=user_id, thread_id=thread_id, query=query,
                    )
                except Exception as mem_exc:
                    logger.warning("memory_context load failed: %s", mem_exc)

            initial_state: dict[str, Any] = {
                "messages": [{"role": "user", "content": effective_query}],
                "user_id": user_id,
                "run_id": run_id,
                "query": effective_query,
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
                "news_context": (brief_state or {}).get("news_context"),
                "brief_history": (brief_state or {}).get("brief_history"),
                "final_response": "",
                "structured_response": None,
                "execution_metadata": {},
                "chart_context": chart_context,
                "clarification": None,
                "clarification_hint": clarification_hint,
                "error": None,
            }

            # Checkpoints namespaced por usuario: dos usuarios con el mismo
            # thread_id del cliente nunca comparten estado del grafo.
            config = {"configurable": {"thread_id": f"{user_id}:{thread_id}"}}

            # Stream graph execution events
            graph = get_graph()
            start_time = time.time()
            node_start_times: dict[str, float] = {}

            # Known graph node names for filtering astream_events
            _GRAPH_NODES = {
                "query_planner", "market_data",
                "news_events", "financial", "research", "code_exec",
                "screener", "backtest", "synthesizer",
                "dilution", "strategy_scanner", "alert_compiler", "alert_manager",
                "news_brief", "context_enricher",
            }

            # Keepalive runs alongside the stream so long silent nodes
            # (research/synthesizer can be 30-90s) never trip the proxy idle
            # timeout. client_id: if the browser drops+reconnects mid-run, the
            # keepalives (and every streamed event below) follow the NEW socket
            # — otherwise the reconnected tab sits silent for 90s and paints a
            # false "La solicitud tardó demasiado".
            heartbeat_task = asyncio.create_task(
                _heartbeat(websocket, client_id=client_id)
            )
            # Even if no socket is live right now, keep the graph running and
            # keep ATTEMPTING delivery per event: the client usually reconnects
            # in 1-5s and picks the stream back up seamlessly.
            client_gone = False
            try:
                async for event in graph.astream_events(initial_state, config=config, version="v2"):
                    kind = event.get("event", "")
                    node_name = event.get("name", "")

                    # Forward custom progress events (from adispatch_custom_event)
                    if kind == "on_custom_event":
                        evt_data = event.get("data", {})
                        # Nodos dinámicos que el agente monta en el canvas
                        # (agents/_canvas.py) — forward completo al frontend.
                        if node_name == "canvas_step" and isinstance(evt_data, dict):
                            parent = str(evt_data.get("node") or "")
                            step_id = str(evt_data.get("step_id") or "")
                            status = str(evt_data.get("status") or "running")
                            art_key = f"{parent}::{step_id}" if parent and step_id else ""
                            art_ref = None
                            # Al completar/errar: persistir blocks como artifacts
                            # inspeccionables (mismo shape que los nodos del grafo).
                            if art_key and status in ("complete", "error"):
                                step_arts = blocks_to_artifacts(
                                    evt_data.get("blocks") or [],
                                    title=str(evt_data.get("title") or ""),
                                    subtitle=str(evt_data.get("subtitle") or ""),
                                )
                                if step_arts:
                                    asyncio.create_task(
                                        run_store.save_artifacts(run_id, art_key, step_arts)
                                    )
                                    art_ref = {
                                        "run_id": run_id,
                                        "kinds": [a.get("kind", "json") for a in step_arts],
                                        "count": len(step_arts),
                                    }
                            step_payload: dict[str, Any] = {
                                "type": "canvas_step",
                                **evt_data,
                                "run_id": run_id,
                                "timestamp": time.time(),
                            }
                            if art_ref:
                                step_payload["artifacts"] = art_ref
                            if not await _deliver(websocket, client_id, step_payload):
                                client_gone = True
                            # Protocolo unificado (además del legacy canvas_step)
                            await _deliver(websocket, client_id, {
                                "type": "node_update",
                                "phase": status,
                                "node": parent,
                                "step_id": step_id,
                                "title": evt_data.get("title"),
                                "subtitle": evt_data.get("subtitle"),
                                "blocks": evt_data.get("blocks") or [],
                                "duration_ms": evt_data.get("duration_ms"),
                                "run_id": run_id,
                                "artifacts": art_ref,
                                "timestamp": time.time(),
                            })
                            continue
                        if isinstance(evt_data, dict) and "message" in evt_data:
                            progress_node = event.get("name", "")
                            if not await _deliver(websocket, client_id, {
                                "type": "agent_progress",
                                "node": progress_node,
                                "message": evt_data["message"],
                                "timestamp": time.time(),
                            }):
                                client_gone = True
                            await _deliver(websocket, client_id, {
                                "type": "node_update",
                                "phase": "progress",
                                "node": progress_node,
                                "preview": evt_data["message"],
                                "run_id": run_id,
                                "timestamp": time.time(),
                            })
                        continue

                    # Only process events for our actual graph nodes
                    if node_name not in _GRAPH_NODES:
                        continue

                    if kind == "on_chain_start":
                        node_start_times[node_name] = time.time()
                        if not await _deliver(websocket, client_id, {
                            "type": "node_started",
                            "node": node_name,
                            "timestamp": time.time(),
                        }):
                            client_gone = True
                        await _deliver(websocket, client_id, {
                            "type": "node_update",
                            "phase": "started",
                            "node": node_name,
                            "run_id": run_id,
                            "timestamp": time.time(),
                        })

                    elif kind == "on_chain_end":
                        node_start = node_start_times.pop(node_name, start_time)
                        node_elapsed_ms = int((time.time() - node_start) * 1000)

                        node_output = event.get("data", {}).get("output", {})
                        try:
                            preview, card_data = summarize_node_output(node_name, node_output)
                        except Exception as sum_exc:  # noqa: BLE001 — never break the stream
                            logger.warning("node summary failed for %s: %s", node_name, sum_exc)
                            preview, card_data = "", None

                        # Artifacts completos → Postgres (el WS solo lleva la
                        # referencia; el inspector los pide por REST).
                        artifacts = build_artifacts(node_name, node_output)
                        if artifacts:
                            asyncio.create_task(
                                run_store.save_artifacts(run_id, node_name, artifacts)
                            )

                        art_ref = None
                        if artifacts:
                            art_ref = {
                                "run_id": run_id,
                                "kinds": [a.get("kind", "json") for a in artifacts],
                                "count": len(artifacts),
                            }

                        payload: dict[str, Any] = {
                            "type": "node_completed",
                            "node": node_name,
                            "elapsed_ms": node_elapsed_ms,
                            "preview": preview[:300],
                            "run_id": run_id,
                        }
                        if card_data:
                            payload["data"] = card_data
                        if art_ref:
                            payload["artifacts"] = art_ref
                        if not await _deliver(websocket, client_id, payload):
                            client_gone = True
                        # Protocolo unificado (además del legacy node_completed)
                        await _deliver(websocket, client_id, {
                            "type": "node_update",
                            "phase": "complete",
                            "node": node_name,
                            "elapsed_ms": node_elapsed_ms,
                            "preview": preview[:300],
                            "data": card_data,
                            "run_id": run_id,
                            "artifacts": art_ref,
                            "timestamp": time.time(),
                        })
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
                    asyncio.create_task(run_store.finish_run(run_id, "clarification"))
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

                # Charts del sandbox de code_exec: el frontend (ResultBlock,
                # type 'code_exec') espera charts como {label: png_base64}.
                # Sin este bloque los PNG se quedan en agent_results y el chat
                # nunca los pinta.
                ce_result = agent_results.get("code_exec", {})
                ce_charts = ce_result.get("charts") if isinstance(ce_result, dict) else None
                if ce_charts:
                    structured_outputs.append({
                        "type": "code_exec",
                        "title": "Charts",
                        "charts": {
                            (c.get("label") or f"chart_{i}"): c.get("png_base64", "")
                            for i, c in enumerate(ce_charts)
                            if isinstance(c, dict) and c.get("png_base64")
                        },
                    })

                # Alert draft: typed payload so the UI renders an interactive
                # card (paraphrase contract + dry-run evidence + arm button)
                ac_result = agent_results.get("alert_compiler", {})
                if isinstance(ac_result, dict) and ac_result.get("spec_id"):
                    spec = ac_result.get("spec", {}) or {}
                    dry = ac_result.get("dry_run", {}) or {}
                    similar = ac_result.get("similar") or {}
                    structured_outputs.append({
                        "type": "alert_draft",
                        "title": "Borrador de alerta",
                        "alert": {
                            "spec_id": ac_result["spec_id"],
                            "name": spec.get("name", "") or (similar.get("exact") or [{}])[0].get("name", ""),
                            "status": (
                                (similar.get("exact") or [{}])[0].get("status", "draft")
                                if ac_result.get("duplicate")
                                else spec.get("status", "draft")
                            ),
                            "tier": spec.get("tier", ""),
                            "paraphrase": ac_result.get("paraphrase", ""),
                            "armable_now": bool(ac_result.get("armable_now")),
                            "persisted": bool(ac_result.get("persisted")),
                            "duplicate": bool(ac_result.get("duplicate")),
                            "similar": {
                                "recommendation": similar.get("recommendation", "create"),
                                "exact": similar.get("exact") or [],
                                "near": similar.get("near") or [],
                            },
                            "universe": spec.get("universe", {}),
                            "steps": spec.get("steps", []),
                            "day_conditions": spec.get("day_conditions", []),
                            "membership": spec.get("membership"),
                            "price_levels": spec.get("price_levels", []),
                            "lifecycle": spec.get("lifecycle", {}),
                            "dry_run": {
                                "total_fires": dry.get("total_fires", 0),
                                "days_scanned": dry.get("days_scanned", []),
                                "unique_symbols": (dry.get("unique_symbols") or [])[:30],
                                "per_day": [
                                    {
                                        "date": d.get("date"),
                                        "count": d.get("count", 0),
                                        "matches": (d.get("matches") or [])[:8],
                                    }
                                    for d in (dry.get("per_day") or [])
                                ],
                                "chart_evidence": dry.get("chart_evidence") or [],
                                "errors": dry.get("errors", []),
                                "note": dry.get("note"),
                            },
                        },
                    })

                response_payload: dict[str, Any] = {
                    "type": "final_response",
                    "response": final_response,
                    "thread_id": thread_id,
                    "metadata": {
                        "total_elapsed_ms": total_ms,
                        "client_id": client_id,
                    },
                }

                if structured_response:
                    response_payload["structured_response"] = structured_response

                if structured_outputs:
                    response_payload["outputs"] = structured_outputs

                # Retry delivery: after a mid-run drop the browser reconnects
                # in 1-5s; without retries the finished answer was lost and the
                # UI showed a timeout even though the run succeeded.
                await _deliver_with_retry(websocket, client_id, response_payload)

                asyncio.create_task(run_store.finish_run(run_id, "complete"))

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
                        user_id=user_id,
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
                asyncio.create_task(run_store.finish_run(run_id, "error"))
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
