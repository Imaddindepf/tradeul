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
            f"You have {len(specs)} alert(s). Open them in the AI Alerts panel (AIA command)."
            if specs else
            "You have no AI alerts yet. Create one with \"alert me when…\"."
        )
    else:
        target = _match_spec(query, specs)
        if target is None:
            result["error"] = (
                "I couldn't identify which alert you mean. Say the ticker or the name, "
                "or use the AI Alerts panel (AIA)."
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
                    f"Alert \"{target.get('name')}\" paused."
                    if updated else "I couldn't pause the alert."
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
                    f"Alert \"{target.get('name')}\" archived."
                    if updated else "I couldn't archive the alert."
                )
                result["new_status"] = "archived"

            elif action == "arm":
                try:
                    spec = AlertSpec(**target)
                except Exception as exc:
                    result["error"] = f"Invalid spec: {exc}"
                    spec = None
                if spec is not None:
                    if not spec.is_live_armable():
                        result["message"] = (
                            f"\"{spec.name}\" cannot be armed live "
                            "(it needs end-of-day context). Use dry-run."
                        )
                    elif eng is None:
                        result["message"] = (
                            f"Engine unavailable right now. Arm \"{spec.name}\" "
                            "from the AI Alerts panel (AIA)."
                        )
                        result["needs_panel"] = True
                    else:
                        try:
                            cfg = await eng.register_trigger(user_id, spec.to_trigger_config())
                            await store.set_status(
                                sid, user_id, AlertStatus.ARMED, trigger_id=cfg.id,
                            )
                            result["message"] = f"Alert \"{spec.name}\" armed on the live engine."
                            result["new_status"] = "armed"
                            result["live"] = True
                        except Exception as exc:
                            result["error"] = f"Couldn't arm it: {exc}"

    elapsed = int((time.time() - start) * 1000)
    return {
        "agent_results": {"alert_manager": result},
        "execution_metadata": {
            **(state.get("execution_metadata", {})),
            "alert_manager": {"elapsed_ms": elapsed, "action": action},
        },
    }
