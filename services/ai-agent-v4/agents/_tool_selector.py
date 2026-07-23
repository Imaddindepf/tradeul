"""
Selector nativo de herramientas (Fase 3c) — compartido por agentes y evals.

Un LLM fast (json_mode, temp 0) elige, del roster del agente
(agents/tool_rosters.py), el conjunto mínimo de tools para una sub-tarea.
Es la mecánica que los evals de evals/run_tool_selection.py validan: el gate
y el código de producción comparten este mismo prompt y parseo, así el eval
mide exactamente lo que corre en producción.

Rollout por agente vía env `AGENT_NATIVE_TOOLS` (lista separada por comas,
p.ej. "financial" o "financial,dilution"). Vacío (default) = ningún agente
usa selección nativa; cada agente conserva su ruta heurística como fallback
ante cualquier fallo del selector (fail-safe: nunca rompe el flujo).
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

NATIVE_TOOLS_ENV = "AGENT_NATIVE_TOOLS"

_AGENT_ROLES = {
    "market_data": "real-time market data specialist (prices, technicals, rankings, RVOL, historical bars, pattern forecasts)",
    "news_events": "news & market-events specialist (headlines, catalysts, live event stream, earnings calendar, SEC filings search)",
    "financial": "fundamentals specialist (financial statements, segments, ratios, key stats with analyst estimates, adjusted metrics, SEC filing contents)",
    "dilution": "dilution specialist (warrants, ATMs, shelfs, cash runway, offerings, dilution risk)",
    "screener": "stock screener specialist (custom numeric filters over the full universe)",
    "research": "deep research specialist (web/X search plus prediction-market probabilities)",
}

_SNAPSHOT = Path(__file__).resolve().parent.parent / "evals" / "gateway_tools_snapshot.json"
_snapshot_descs: dict[str, str] | None = None


def native_tools_enabled(agent: str) -> bool:
    """True si el agente está en el rollout de tool-calling nativo."""
    raw = os.getenv(NATIVE_TOOLS_ENV, "")
    enabled = {a.strip() for a in raw.split(",") if a.strip()}
    return agent in enabled or "all" in enabled


def _gateway_descs() -> dict[str, str]:
    """full_name (server_tool) -> descripción, del snapshot del gateway."""
    global _snapshot_descs
    if _snapshot_descs is None:
        try:
            data = json.loads(_SNAPSHOT.read_text())
            _snapshot_descs = {
                t["name"]: (t.get("desc") or t.get("description") or "").strip()
                for t in data
            }
        except Exception:  # noqa: BLE001
            _snapshot_descs = {}
    return _snapshot_descs


def _tool_desc(tool: str) -> str:
    from agents.tool_rosters import TOOL_DESCS
    d = TOOL_DESCS.get(tool)
    if d:
        return d
    return _gateway_descs().get(tool.replace(".", "_", 1), "")


def build_selector_prompt(agent: str, query: str) -> str:
    from agents.tool_rosters import roster_tools

    lines = []
    for t in roster_tools(agent):
        d = _tool_desc(t)
        lines.append(f'- "{t}"' + (f": {d}" if d else ""))
    toolbox = "\n".join(lines)
    role = _AGENT_ROLES.get(agent, agent)
    return f"""You are the {role} of a stock trading platform.

Given the task below, select the MINIMAL set of tools from YOUR toolbox needed
to answer it well. Rules:
- Select ONLY tools that are actually needed; do not pad the list.
- If a tool answers the question directly, prefer it over composing others.
- Answer in JSON ONLY: {{"tools": ["server.tool", ...], "reason": "<one short sentence>"}}

<toolbox>
{toolbox}
</toolbox>

<task>
{query}
</task>"""


async def select_tools(agent: str, query: str) -> list[str]:
    """Selección de tools para una sub-tarea. Lista vacía = selector falló
    (el caller decide su fallback; los agentes caen a su ruta heurística)."""
    from agents._make_llm import make_llm
    from agents._llm_retry import llm_invoke_with_retry
    from agents.supervisor import _salvage_json
    from agents.tool_rosters import roster_tools

    # Lección de la Fase 3a repetida aquí (visto en producción 2026-07-23,
    # "análisis completo de dilución de BBIG"): los thinking-tokens de Gemini
    # salen del presupuesto de salida y truncan el JSON en tareas amplias.
    # Seleccionar tools es mecánico: sin thinking + presupuesto holgado.
    llm = make_llm(tier="fast", temperature=0.0, max_tokens=2048,
                   json_mode=True, disable_thinking=True)
    prompt = build_selector_prompt(agent, query)
    try:
        resp = await llm_invoke_with_retry(llm, [{"role": "user", "content": prompt}])
        raw = (getattr(resp, "content", "") or "").strip()
        decision = _salvage_json(raw)
    except Exception as exc:  # noqa: BLE001
        logger.warning("tool selector failed for %s: %s", agent, exc)
        return []
    if not isinstance(decision, dict):
        logger.warning("tool selector unparseable output for %s", agent)
        return []
    picked = decision.get("tools") or []
    valid = set(roster_tools(agent))
    selected = [t for t in picked if isinstance(t, str) and t in valid]
    logger.info("tool selector [%s]: %s (reason=%s)", agent, selected,
                str(decision.get("reason", ""))[:100])
    return selected
