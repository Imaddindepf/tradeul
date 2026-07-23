"""
News-brief agent node (Fase 3b): el motor de briefs como nodo del grafo.

Los threads que nacen de un "Contexto de noticia" mantienen su primer turno
en la ruta directa del websocket handler (generar el brief no requiere
planificación). Los FOLLOW-UPS, en cambio, entran al grafo: el planner ve
este agente solo cuando el estado trae `news_context` y decide si el turno
se responde con el motor de briefs (conversacional/analítico sobre la
noticia), con agentes live (datos de mercado en tiempo real), o con AMBOS
en paralelo — el caso híbrido que el antiguo router binario LIVE/CHAT de
`agents/brief_router.py` no podía cubrir.

El nodo delega en el servicio ai-news-brief (Opus) vía clients.news_brief_client,
pasándole la noticia original y el historial del hilo (`brief_history`,
cargado por el websocket handler desde la memoria Redis del thread).
"""
from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


async def _progress(msg: str) -> None:
    """Emit a custom progress event visible in the chat UI step indicator."""
    try:
        from langchain_core.callbacks.manager import adispatch_custom_event
        await adispatch_custom_event("news_brief_progress", {"message": msg})
    except Exception:  # noqa: BLE001
        pass  # Never block the agent if progress dispatch fails


async def news_brief_node(state: dict) -> dict:
    """Answer a brief-thread follow-up with the ai-news-brief engine (Opus).

    Reads from state:
      - news_context: the original news dict this thread was born from
      - brief_history: prior turns as [{role, content}] (loaded by the handler)
      - agent_task / query: the follow-up question

    Returns the polished markdown answer in agent_results["news_brief"].
    The synthesizer passes it through verbatim when it is the only result,
    and merges it with live-data results otherwise.
    """
    from clients import news_brief_client

    start_time = time.time()

    query = state.get("agent_task") or state.get("query", "")
    news_ctx: dict[str, Any] = state.get("news_context") or {}
    history: list[dict[str, str]] = state.get("brief_history") or []

    if not news_ctx.get("text"):
        # Sin noticia no hay contexto que mantener — construye uno mínimo con
        # la propia pregunta para no romper el contrato del servicio.
        news_ctx = {"text": query, "tickers": state.get("tickers", [])}

    await _progress("Repasando el contexto de la noticia…")

    try:
        result = await news_brief_client.followup(news_ctx, history, query)
    except Exception as exc:  # noqa: BLE001
        elapsed_ms = int((time.time() - start_time) * 1000)
        logger.error("news_brief node failed: %s", exc)
        return {
            "agent_results": {
                "news_brief": {
                    "status": "tool_error",
                    "error": f"news_brief engine failed: {type(exc).__name__}: {exc}",
                },
            },
            "execution_metadata": {
                **(state.get("execution_metadata", {})),
                "news_brief": {"elapsed_ms": elapsed_ms, "status": "tool_error"},
            },
        }

    elapsed_ms = int((time.time() - start_time) * 1000)
    brief_md = (result.get("brief_markdown") or "").strip()
    sources = result.get("sources", []) or []
    tools_used = result.get("tools_used", []) or []

    logger.info(
        "news_brief node: answered follow-up in %dms (%d chars, %d sources)",
        elapsed_ms, len(brief_md), len(sources),
    )

    return {
        "agent_results": {
            "news_brief": {
                "status": "success" if brief_md else "empty",
                "brief_markdown": brief_md,
                "sources": sources,
                "tools_used": tools_used,
                "engine": "ai-news-brief",
            },
        },
        "execution_metadata": {
            **(state.get("execution_metadata", {})),
            "news_brief": {
                "elapsed_ms": elapsed_ms,
                "status": "success" if brief_md else "empty",
                "sources": len(sources),
            },
        },
    }
