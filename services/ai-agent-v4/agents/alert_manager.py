"""
Alert Manager Agent — list / pause / arm / archive existing LLM alerts via chat.

Unlike alert_compiler (creates NEW drafts), this operates on persisted specs.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any, Optional

from alerts.spec import AlertSpec, AlertStatus
from alerts.store import get_store

logger = logging.getLogger(__name__)


def _guess_action(query: str) -> str:
    q = query.lower()
    if any(k in q for k in ("pausa", "pause", "pausar")):
        return "pause"
    if any(k in q for k in ("arma", "armar", "activa", "activar", "arm ", "activate")):
        return "arm"
    if any(k in q for k in ("archiva", "archive", "borra", "delete", "elimina")):
        return "archive"
    return "list"


def _match_spec(query: str, specs: list[dict]) -> Optional[dict]:
    q = query.upper()
    tokens = set(re.findall(r"[A-Z]{1,5}", q))
    for s in specs:
        for sym in (s.get("universe") or {}).get("symbols_include") or []:
            if sym.upper() in tokens:
                return s
    for s in specs:
        name = (s.get("name") or "").upper()
        if name and name in q:
            return s
    for s in specs:
        for step in s.get("steps") or []:
            for et in step.get("event_types") or []:
                if et.upper() in q or et.upper().replace("_", " ") in q:
                    return s
    if len(specs) == 1:
        return specs[0]
    return None


def _engine():
    try:
        from handlers.trigger_handler import _engine as eng
        return eng
    except Exception:
        return None


async def alert_manager_node(state: dict) -> dict:
    start = time.time()
    query = state.get("agent_task") or state.get("query", "")
    user_id = state.get("user_id") or "default"
    action = _guess_action(query)

    store = get_store()
    specs = await store.list_specs(user_id, include_archived=False)

    result: dict[str, Any] = {
        "action": action,
        "query_interpreted": query,
        "alerts": [
            {
                "spec_id": s.get("id"),
                "name": s.get("name"),
                "status": s.get("status"),
                "tier": s.get("tier"),
                "paraphrase": (s.get("paraphrase") or "")[:200],
                "symbols": (s.get("universe") or {}).get("symbols_include") or [],
            }
            for s in specs
        ],
        "count": len(specs),
    }

    if action == "list":
        result["message"] = (
            f"Tienes {len(specs)} alerta(s). Ábrelas en el panel AI Alerts (comando AIA)."
            if specs else
            "No tienes alertas IA todavía. Crea una con «avísame cuando…»."
        )
    else:
        target = _match_spec(query, specs)
        if target is None:
            result["error"] = (
                "No identifiqué qué alerta quieres. Di el ticker o el nombre, "
                "o usa el panel AI Alerts (AIA)."
            )
        else:
            sid = target["id"]
            result["target"] = {
                "spec_id": sid,
                "name": target.get("name"),
                "status": target.get("status"),
            }
            eng = _engine()

            if action == "pause":
                if eng and target.get("trigger_id"):
                    try:
                        await eng.unregister_trigger(user_id, target["trigger_id"])
                    except Exception:
                        logger.exception("alert_manager pause unregister failed")
                updated = await store.set_status(sid, user_id, AlertStatus.PAUSED)
                result["message"] = (
                    f"Alerta «{target.get('name')}» pausada."
                    if updated else "No pude pausar la alerta."
                )
                result["new_status"] = "paused"

            elif action == "archive":
                if eng and target.get("trigger_id"):
                    try:
                        await eng.unregister_trigger(user_id, target["trigger_id"])
                    except Exception:
                        logger.exception("alert_manager archive unregister failed")
                updated = await store.set_status(sid, user_id, AlertStatus.ARCHIVED)
                result["message"] = (
                    f"Alerta «{target.get('name')}» archivada."
                    if updated else "No pude archivar la alerta."
                )
                result["new_status"] = "archived"

            elif action == "arm":
                try:
                    spec = AlertSpec(**target)
                except Exception as exc:
                    result["error"] = f"Spec inválida: {exc}"
                    spec = None
                if spec is not None:
                    if not spec.is_live_armable():
                        result["message"] = (
                            f"«{spec.name}» no se puede armar en vivo "
                            "(necesita contexto de fin de día). Usa dry-run."
                        )
                    elif eng is None:
                        result["message"] = (
                            f"Motor no disponible ahora. Activa «{spec.name}» "
                            "desde el panel AI Alerts (AIA)."
                        )
                        result["needs_panel"] = True
                    else:
                        try:
                            cfg = await eng.register_trigger(user_id, spec.to_trigger_config())
                            await store.set_status(
                                sid, user_id, AlertStatus.ARMED, trigger_id=cfg.id,
                            )
                            result["message"] = f"Alerta «{spec.name}» activada en el motor en vivo."
                            result["new_status"] = "armed"
                            result["live"] = True
                        except Exception as exc:
                            result["error"] = f"No pude activar: {exc}"

    elapsed = int((time.time() - start) * 1000)
    return {
        "agent_results": {"alert_manager": result},
        "execution_metadata": {
            **(state.get("execution_metadata", {})),
            "alert_manager": {"elapsed_ms": elapsed, "action": action},
        },
    }
