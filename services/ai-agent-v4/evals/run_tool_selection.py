"""
Runner de evals de SELECCIÓN DE HERRAMIENTA por agente (gate de la Fase 3c).

Mide, con el LLM real (tier fast, json_mode, temp 0), qué herramientas de su
roster elegiría cada agente para una sub-tarea dada — la mecánica exacta que
el tool-calling nativo de la Fase 3c formalizará. Correrlo ANTES del refactor
da el baseline; correrlo DESPUÉS (sustituyendo el selector por el del agente
nativo) es el gate de no-regresión.

Salidas:
  - Por caso: PASS/FAIL con la selección y el porqué.
  - Por agente: tasa de acierto.
  - Orphan unlock: cuántas tools hoy huérfanas se eligieron cuando tocaba
    (la capacidad que la Fase 3c recupera).

El selector bajo test es EL DE PRODUCCIÓN (agents/_tool_selector.select_tools):
prompt, parseo y validación idénticos a lo que corre en los agentes nativos.

Uso (dentro del contenedor, necesita GOOGLE_API_KEY):
    python -m evals.run_tool_selection
    python -m evals.run_tool_selection --agent dilution   # solo un agente
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

_REPORT = Path(os.getenv("EVAL_REPORT_PATH", "/tmp/eval_tool_selection_report.json"))

async def _select(agent: str, query: str) -> list[str]:
    """Delegado al selector DE PRODUCCIÓN — el gate mide el código real."""
    from agents._tool_selector import select_tools
    return await select_tools(agent, query)


async def run(only_agent: str | None = None) -> int:
    from evals.tool_cases import TOOL_CASES
    from evals.tool_rosters import ROSTERS

    cases = [c for c in TOOL_CASES if not only_agent or c["agent"] == only_agent]
    if not cases:
        print(f"[error] no cases for agent={only_agent}", file=sys.stderr)
        return 2

    results = []
    failed = 0
    per_agent: dict[str, list[bool]] = {}
    orphan_hits: list[str] = []
    orphan_misses: list[str] = []
    all_orphans = {t for r in ROSTERS.values() for t in r["orphans"]}

    for c in cases:
        picked = await _select(c["agent"], c["query"])
        pset = set(picked)
        ok = True
        reasons = []
        if "tools_all" in c and not set(c["tools_all"]) <= pset:
            ok = False
            reasons.append(f"missing {sorted(set(c['tools_all']) - pset)}")
        if "tools_any" in c and not (set(c["tools_any"]) & pset):
            ok = False
            reasons.append(f"picked {sorted(pset)} ∩ {c['tools_any']} = ∅")
        if "tools_none" in c and (set(c["tools_none"]) & pset):
            ok = False
            reasons.append(f"forbidden {sorted(set(c['tools_none']) & pset)}")

        unlock = c.get("orphan_unlock")
        if unlock:
            (orphan_hits if unlock in pset else orphan_misses).append(f"{c['id']}:{unlock}")

        failed += (not ok)
        per_agent.setdefault(c["agent"], []).append(ok)
        results.append({"id": c["id"], "agent": c["agent"], "ok": ok,
                        "picked": sorted(pset), "why": reasons})
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {c['id']:28} {c['agent']:12} -> {sorted(pset)}"
              + ("" if ok else f"  <- {'; '.join(reasons)}"))

    print(f"\n── Tool selection: {len(cases) - failed}/{len(cases)} pass ──")
    for agent, oks in sorted(per_agent.items()):
        print(f"   {agent:12} {sum(oks)}/{len(oks)}")
    n_unlock = len(orphan_hits) + len(orphan_misses)
    if n_unlock:
        print(f"── Orphan unlock: {len(orphan_hits)}/{n_unlock} huérfanas elegidas cuando tocaba ──")
        for m in orphan_misses:
            print(f"   MISS {m}")
    print(f"── Roster coverage: {len(all_orphans)} huérfanas asignadas a "
          f"{len(ROSTERS)} agentes ──")

    try:
        _REPORT.write_text(json.dumps({
            "total": len(cases), "failed": failed,
            "per_agent": {a: {"pass": sum(o), "total": len(o)} for a, o in per_agent.items()},
            "orphan_hits": orphan_hits, "orphan_misses": orphan_misses,
            "results": results,
        }, ensure_ascii=False, indent=2))
        print(f"[report] {_REPORT}")
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] report write failed: {exc}", file=sys.stderr)

    return 1 if failed else 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", default=None, help="correr solo los casos de un agente")
    args = ap.parse_args()
    sys.exit(asyncio.run(run(args.agent)))


if __name__ == "__main__":
    main()
