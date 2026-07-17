"""
Canvas steps — nodos que el agente MONTA en vivo en el Execution Canvas.

Cualquier agente puede publicar los pasos internos de su trabajo (catálogo
cargado, spec compilada, cada día de un dry-run con sus disparos…) y el
frontend los añade como nodos nuevos del workflow en tiempo real, con los
datos reales dentro (tablas, código, métricas).

Los `blocks` siguen el modelo NodeBlock del frontend
(frontend/components/ai-agent/workflow/types.ts):
    {"kind": "metrics", "items": [{"label": "...", "value": ...}]}
    {"kind": "chips",   "style": "primary"|"neutral"|"mono", "items": [...]}
    {"kind": "text",    "text": "..."}
    {"kind": "table",   "columns": [...], "rows": [[...]], "total": N,
     "title": "...", "cascade": True}
    {"kind": "code",    "content": "...", "language": "json",
     "typewriter": True}

Emitir un step con el mismo step_id actualiza el nodo existente (upsert),
así un paso puede nacer "running" y completarse con sus datos después.
"""
from __future__ import annotations

from typing import Any

from langchain_core.callbacks import adispatch_custom_event


async def canvas_step(
    node: str,
    step_id: str,
    title: str,
    status: str = "running",
    *,
    subtitle: str = "",
    blocks: list[dict[str, Any]] | None = None,
    duration_ms: int | None = None,
) -> None:
    """Publica/actualiza un nodo dinámico del canvas. Nunca rompe al agente."""
    try:
        await adispatch_custom_event("canvas_step", {
            "node": node,
            "step_id": step_id,
            "title": title,
            "status": status,          # running | complete | error
            "subtitle": subtitle,
            "blocks": blocks or [],
            "duration_ms": duration_ms,
        })
    except Exception:  # noqa: BLE001 — fuera de un run streaming no hay callback
        pass
