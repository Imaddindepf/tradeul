"""
Routing eval runner — regresión del planner + casos curados.

Dos modos de valor:

  1. CURATED: aserciones must-pass (evals/cases.py). Fallan si el planner
     enruta mal un caso conocido (p.ej. el híbrido de farma sin market_data).

  2. REGRESIÓN POR SNAPSHOT: toma una muestra diversa de queries reales del
     historial (agent_conv_messages) y compara la decisión actual del planner
     contra un baseline guardado (evals/baseline_routing.json). Reporta cada
     query cuyo routing CAMBIÓ — imprescindible para el refactor de routing de
     la Fase 3: antes/después, ves exactamente qué se movió y lo juzgas.

Uso (dentro del contenedor):
    python -m evals.run_routing                 # corre curated + regresión
    python -m evals.run_routing --update-baseline
    python -m evals.run_routing --sample 60

Cada query = 1 llamada al planner (Gemini Flash), barata. La telemetría de la
Fase 2a captura su coste automáticamente (node=query_planner).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

_BASELINE = Path(__file__).with_name("baseline_routing.json")
_REPORT = Path(os.getenv("EVAL_REPORT_PATH", "/tmp/eval_routing_report.json"))


def _screen_specs(out: dict) -> list[dict]:
    """Normaliza "screen" (None | dict legacy | list[dict]) a lista de specs."""
    screen = out.get("screen")
    if isinstance(screen, dict):
        screen = [screen]
    return [s for s in (screen or []) if isinstance(s, dict)]


async def _plan(query: str, extra_state: dict | None = None) -> dict:
    """Corre el planner sobre una query y devuelve su decisión de routing.

    `extra_state` permite simular contexto adicional (p.ej. `news_context`
    para brief threads de la Fase 3b, o `memory_context` con turnos previos).
    """
    from agents.supervisor import query_planner_node

    state = {
        "messages": [{"role": "user", "content": query}],
        "user_id": "eval_user",
        "run_id": "eval",
        "query": query,
        "mode": "auto",
        "tickers": [],
        "ticker_info": {},
        "memory_context": [],
        "market_context": {},
        "clarification_hint": "",
        "intent": "",
        "active_agents": [],
    }
    if extra_state:
        state.update(extra_state)
    try:
        out = await query_planner_node(state)
    except Exception as exc:  # noqa: BLE001
        return {"intent": "ERROR", "active_agents": [], "error": str(exc)[:200]}
    return {
        "intent": out.get("intent", "UNKNOWN"),
        "active_agents": sorted(out.get("active_agents", []) or []),
        "tickers": sorted(out.get("tickers", []) or []),
        "confidence": out.get("confidence", None),
        "clarification": bool(out.get("clarification")),
        "plan": (out.get("plan") or "")[:200],
        "theme_tags": sorted(out.get("theme_tags") or []),
        "screens_count": len(_screen_specs(out)),
        "screen_fields": sorted({
            f.get("field", "")
            for spec in _screen_specs(out)
            for f in (spec.get("filters") or [])
            if isinstance(f, dict)
        }),
        "screen_sorts": sorted({
            str(spec.get("sort_by"))
            for spec in _screen_specs(out)
            if spec.get("sort_by")
        }),
    }


async def _load_real_queries(sample: int) -> list[str]:
    """Muestra diversa de queries reales (no legacy), repartida por longitud."""
    db_url = os.getenv("CHECKPOINT_DB_URL", "").strip()
    if not db_url:
        return []
    try:
        from psycopg_pool import AsyncConnectionPool
        async with AsyncConnectionPool(db_url, min_size=1, max_size=1, open=False,
                                       kwargs={"autocommit": True}) as pool:
            await pool.open(wait=True, timeout=15)
            async with pool.connection() as conn:
                cur = await conn.execute(
                    """
                    SELECT DISTINCT query FROM agent_conv_messages
                    WHERE length(query) BETWEEN 8 AND 400
                    ORDER BY query
                    """
                )
                rows = [r[0] for r in await cur.fetchall()]
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] could not load real queries: {exc}", file=sys.stderr)
        return []
    # Reparto determinista por longitud para diversidad sin aleatoriedad.
    rows = [q.strip() for q in rows if q and q.strip()]
    rows.sort(key=lambda q: (len(q), q))
    if len(rows) <= sample:
        return rows
    step = len(rows) / sample
    return [rows[int(i * step)] for i in range(sample)]


async def run(sample: int, update_baseline: bool) -> int:
    from evals.cases import CURATED

    # ── 1) Curated must-pass ─────────────────────────────────────
    curated_results = []
    curated_failed = 0
    for c in CURATED:
        d = await _plan(c["query"], c.get("state"))
        agents = set(d["active_agents"])
        ok = True
        reasons = []
        if "intent_in" in c and d["intent"] not in c["intent_in"]:
            ok = False
            reasons.append(f"intent={d['intent']} ∉ {sorted(c['intent_in'])}")
        if "agents_any" in c and not (set(c["agents_any"]) & agents):
            ok = False
            reasons.append(f"agents={sorted(agents)} ∩ {c['agents_any']} = ∅")
        if "agents_all" in c and not set(c["agents_all"]) <= agents:
            ok = False
            reasons.append(f"missing {sorted(set(c['agents_all']) - agents)}")
        if "agents_none" in c and (set(c["agents_none"]) & agents):
            ok = False
            reasons.append(f"forbidden {sorted(set(c['agents_none']) & agents)}")
        if c.get("expect_clarification") and not d.get("clarification"):
            ok = False
            reasons.append("expected clarification, got a confident route")
        if "plan_not_contains" in c:
            plan_low = d.get("plan", "").lower()
            bad = [w for w in c["plan_not_contains"] if w.lower() in plan_low]
            if bad:
                ok = False
                reasons.append(f"plan adopted forbidden referent {bad}")
        if "screen_fields_any" in c and not (set(c["screen_fields_any"]) & set(d.get("screen_fields", []))):
            ok = False
            reasons.append(f"screen_fields={d.get('screen_fields')} ∩ {c['screen_fields_any']} = ∅")
        if "screens_min" in c and d.get("screens_count", 0) < c["screens_min"]:
            ok = False
            reasons.append(f"screens_count={d.get('screens_count', 0)} < min {c['screens_min']}")
        if "screen_sorts_any" in c and not (set(c["screen_sorts_any"]) & set(d.get("screen_sorts", []))):
            ok = False
            reasons.append(f"screen_sorts={d.get('screen_sorts')} ∩ {c['screen_sorts_any']} = ∅")
        if "themes_max" in c and len(d.get("theme_tags", [])) > c["themes_max"]:
            ok = False
            reasons.append(f"{len(d['theme_tags'])} theme_tags > max {c['themes_max']}: {d['theme_tags'][:5]}")
        curated_failed += (not ok)
        curated_results.append({"id": c["id"], "ok": ok, "got": d, "why": reasons})
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {c['id']:22} intent={d['intent']:16} agents={d['active_agents']}"
              + ("" if ok else f"  <- {'; '.join(reasons)}"))

    # ── 2) Regresión por snapshot ────────────────────────────────
    real = await _load_real_queries(sample)
    current = {}
    for q in real:
        d = await _plan(q)
        current[q] = {"intent": d["intent"], "active_agents": d["active_agents"]}

    baseline = {}
    if _BASELINE.exists():
        baseline = json.loads(_BASELINE.read_text())

    drift = []
    for q, cur in current.items():
        base = baseline.get(q)
        if base is None:
            continue
        if base != cur:
            drift.append({"query": q, "was": base, "now": cur})

    print(f"\n── Curated: {len(CURATED) - curated_failed}/{len(CURATED)} pass ──")
    print(f"── Regression: {len(current)} real queries, "
          f"{len(baseline)} in baseline, {len(drift)} drifted ──")
    for d in drift[:25]:
        print(f"  DRIFT: {d['query'][:60]!r}")
        print(f"         was {d['was']}  ->  now {d['now']}")

    if update_baseline or not _BASELINE.exists():
        _BASELINE.write_text(json.dumps(current, ensure_ascii=False, indent=2, sort_keys=True))
        print(f"\n[baseline] wrote {len(current)} entries -> {_BASELINE}")

    report = {
        "curated": {"total": len(CURATED), "failed": curated_failed, "results": curated_results},
        "regression": {"sampled": len(current), "baseline": len(baseline), "drift": drift},
    }
    _REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"[report] {_REPORT}")

    # Exit non-zero if any curated case failed (CI gate).
    return 1 if curated_failed else 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=int(os.getenv("EVAL_SAMPLE", "40")))
    ap.add_argument("--update-baseline", action="store_true")
    args = ap.parse_args()
    sys.exit(asyncio.run(run(args.sample, args.update_baseline)))


if __name__ == "__main__":
    main()
