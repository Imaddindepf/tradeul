"""
Artifact builder — convierte el output completo de un nodo en artifacts tipados.

A diferencia de node_summary.py (previews de 6x5 para la tarjeta del canvas),
aquí NO se trunca de forma agresiva: tablas completas (hasta 500 filas x 14
columnas), código/spec entero, evidencia de charts del dry-run y el JSON raw
del resultado. Es lo que alimenta el inspector de nodo del frontend.

Shape compartido con frontend (components/ai-agent/types.ts → Artifact):
    {"kind": "summary", "title": "...", "text": "..."}
    {"kind": "metrics", "title": "...", "items": [{"label": "...", "value": ...}]}
    {"kind": "chips",   "title": "...", "items": ["..."]}
    {"kind": "table",   "title": "...", "columns": [...], "rows": [[...]], "total": N}
    {"kind": "code",    "title": "...", "language": "...", "content": "..."}
    {"kind": "chart",   "title": "...", "chart": {...}}   # chart_evidence entry
    {"kind": "json",    "title": "...", "data": {...}}
"""
from __future__ import annotations

import json
from typing import Any

_MAX_TABLE_ROWS = 500
_MAX_TABLE_COLS = 14
_MAX_TABLES = 6
_MAX_CODE_CHARS = 30_000
_MAX_RAW_CHARS = 80_000
_MAX_CHARTS = 8

# (título, ruta) de tablas conocidas por agente — se emiten TODAS las que existan.
_TABLE_PATHS: dict[str, list[tuple[str, tuple[str, ...]]]] = {
    "screener": [("Resultados del screen", ("screen_results", "results"))],
    "strategy_scanner": [("Setups encontrados", ("scan_results", "matches"))],
    "market_data": [
        ("Scanner", ("scanner_results",)),
        ("Resolución temática", ("thematic_resolution", "results")),
    ],
    "news_events": [
        ("Noticias", ("news",)),
        ("Earnings hoy", ("today_earnings",)),
        ("Eventos", ("events",)),
    ],
    "dilution": [("Filings", ("filings",))],
}

_PRIORITY_COLS = [
    "symbol", "ticker", "title", "name", "company_name",
    "price", "close", "open", "change_percent", "change_pct", "close_vs_open_pct",
    "rvol", "volume", "market_cap", "sector", "event_type", "date", "created",
]


def _dig(obj: Any, path: tuple[str, ...]) -> Any:
    for key in path:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def _is_row_list(v: Any) -> bool:
    return (
        isinstance(v, list)
        and len(v) >= 1
        and all(isinstance(item, dict) for item in v[:3])
    )


def _rows_to_table(rows: list[dict], title: str) -> dict | None:
    """Tabla completa con valores crudos (el frontend formatea)."""
    scalar_keys: list[str] = []
    for key, val in rows[0].items():
        if isinstance(val, (str, int, float, bool)) or val is None:
            scalar_keys.append(key)
    if not scalar_keys:
        return None
    cols = sorted(
        scalar_keys,
        key=lambda k: (_PRIORITY_COLS.index(k) if k in _PRIORITY_COLS else 99),
    )[:_MAX_TABLE_COLS]
    table_rows = [
        [row.get(c) for c in cols]
        for row in rows[:_MAX_TABLE_ROWS]
    ]
    return {
        "kind": "table",
        "title": title,
        "columns": cols,
        "rows": table_rows,
        "total": len(rows),
    }


def _find_all_row_lists(obj: Any, prefix: str = "", depth: int = 0) -> list[tuple[str, list[dict]]]:
    """Todas las listas-de-dicts del resultado con su ruta como etiqueta."""
    found: list[tuple[str, list[dict]]] = []
    if depth > 3 or not isinstance(obj, dict):
        return found
    for key, v in obj.items():
        label = f"{prefix}.{key}" if prefix else key
        if _is_row_list(v):
            found.append((label, v))
        elif isinstance(v, dict):
            found.extend(_find_all_row_lists(v, label, depth + 1))
    return found


def _code_artifact(title: str, language: str, content: Any) -> dict:
    if not isinstance(content, str):
        content = json.dumps(content, indent=2, ensure_ascii=False, default=str)
    return {
        "kind": "code",
        "title": title,
        "language": language,
        "content": content[:_MAX_CODE_CHARS],
    }


def _metrics_artifact(result: dict) -> dict | None:
    items: list[dict[str, Any]] = []
    for key, val in result.items():
        if key.startswith("_") or key in ("error", "code", "raw_output", "query_interpreted"):
            continue
        if isinstance(val, bool):
            continue
        if isinstance(val, (int, float)):
            items.append({"label": key, "value": val})
        elif isinstance(val, str) and 0 < len(val) <= 40:
            items.append({"label": key, "value": val})
        if len(items) >= 12:
            break
    for path, label in (
        (("scan_results", "count"), "matches"),
        (("screen_results", "total_matched"), "matched"),
        (("dry_run", "total_fires"), "disparos dry-run"),
    ):
        v = _dig(result, path)
        if isinstance(v, (int, float)):
            items.append({"label": label, "value": v})
    if not items:
        return None
    return {"kind": "metrics", "title": "Métricas", "items": items}


def _raw_artifact(result: dict) -> dict | None:
    """JSON crudo del resultado, para transparencia total (si cabe).

    Excluye los PNG base64 del sandbox (`charts`): pesan demasiado y ya se
    muestran como artifacts `image` propios.
    """
    slim = {k: v for k, v in result.items() if k != "charts"}
    try:
        s = json.dumps(slim, ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001
        return None
    if len(s) > _MAX_RAW_CHARS:
        return None
    return {"kind": "json", "title": "Resultado completo (raw)", "data": slim}


def _sandbox_artifacts(result: dict) -> list[dict[str, Any]]:
    """Artifacts de la ejecución real en el sandbox (Fase 4b):
      - cada `output` → tabla (si es DataFrame) o métricas/JSON (escalares)
      - cada `chart` PNG → artifact `image`
    """
    arts: list[dict[str, Any]] = []
    for out in (result.get("outputs") or [])[:8]:
        if not isinstance(out, dict):
            continue
        label = str(out.get("label") or "output")
        data = out.get("data")
        if isinstance(data, dict) and data.get("type") == "dataframe":
            recs = data.get("records") or []
            if _is_row_list(recs):
                t = _rows_to_table(recs, label)
                if t:
                    n_total = data.get("rows", len(recs))
                    if n_total > len(recs):
                        t["title"] = f"{label} ({len(recs)} de {n_total} filas)"
                    arts.append(t)
                    continue
        if isinstance(data, dict) and all(
            isinstance(v, (int, float, str)) for v in data.values()
        ) and data:
            arts.append({
                "kind": "metrics", "title": label,
                "items": [{"label": k, "value": v} for k, v in list(data.items())[:12]],
            })
        else:
            arts.append({"kind": "json", "title": label, "data": data})

    for ch in (result.get("charts") or [])[:_MAX_CHARTS]:
        if isinstance(ch, dict) and ch.get("png_base64"):
            arts.append({
                "kind": "image",
                "title": str(ch.get("label") or "chart"),
                "mime": "image/png",
                "data_base64": ch["png_base64"],
            })
    return arts


def build_artifacts(node_name: str, node_output: Any) -> list[dict[str, Any]]:
    """Artifacts completos de un nodo terminado. Nunca lanza."""
    try:
        return _build(node_name, node_output)
    except Exception:  # noqa: BLE001
        return []


def blocks_to_artifacts(
    blocks: list[dict[str, Any]] | None,
    *,
    title: str = "",
    subtitle: str = "",
) -> list[dict[str, Any]]:
    """Convierte NodeBlocks de un canvas_step en artifacts del inspector.

    Los substeps dinámicos (catálogo, dry-run día, captura…) ya llegan con
    tablas/código/métricas; aquí los persistimos con el mismo shape Artifact
    para que el clic en el sub-nodo abra el mini-notebook.
    """
    arts: list[dict[str, Any]] = []
    if title or subtitle:
        text = title
        if subtitle:
            text = f"{title}\n{subtitle}" if title else subtitle
        arts.append({"kind": "summary", "title": "Paso", "text": text})
    for b in blocks or []:
        if not isinstance(b, dict):
            continue
        kind = b.get("kind")
        if kind == "metrics" and b.get("items"):
            arts.append({
                "kind": "metrics",
                "title": b.get("title") or "Métricas",
                "items": list(b["items"])[:12],
            })
        elif kind == "chips" and b.get("items"):
            arts.append({
                "kind": "chips",
                "title": b.get("title") or "Tags",
                "items": [str(x) for x in b["items"][:40]],
            })
        elif kind == "text" and b.get("text"):
            arts.append({"kind": "summary", "title": "Nota", "text": str(b["text"])})
        elif kind == "error" and b.get("text"):
            arts.append({"kind": "summary", "title": "Error", "text": str(b["text"])})
        elif kind == "table" and b.get("columns") is not None:
            rows = b.get("rows") or []
            arts.append({
                "kind": "table",
                "title": b.get("title") or "Datos",
                "columns": list(b["columns"])[:_MAX_TABLE_COLS],
                "rows": [list(r)[:_MAX_TABLE_COLS] for r in rows[:_MAX_TABLE_ROWS]],
                "total": b.get("total", len(rows)),
            })
        elif kind == "code" and b.get("content"):
            arts.append(_code_artifact(
                b.get("title") or "Código",
                str(b.get("language") or "json"),
                b["content"],
            ))
        elif kind == "feed" and b.get("rows"):
            # Feed → tabla simple para el inspector
            feed_rows = b["rows"][:_MAX_TABLE_ROWS]
            arts.append({
                "kind": "table",
                "title": b.get("title") or "Feed en vivo",
                "columns": ["dato"],
                "rows": [[
                    " · ".join(str(c) for c in (row.get("cells") or []))
                    if isinstance(row, dict) else str(row)
                ] for row in feed_rows],
                "total": len(b["rows"]),
            })
    return arts


def _build(node_name: str, node_output: Any) -> list[dict[str, Any]]:
    if not isinstance(node_output, dict):
        return []

    arts: list[dict[str, Any]] = []

    # ── Planner: decisión de enrutado ──
    if node_name in ("query_planner", "supervisor"):
        plan = node_output.get("plan") or ""
        intent = node_output.get("intent") or ""
        agents = node_output.get("active_agents") or []
        tickers = node_output.get("tickers") or []
        if plan:
            arts.append({"kind": "summary", "title": "Plan", "text": str(plan)})
        items = []
        if intent:
            items.append({"label": "intent", "value": intent})
        if agents:
            items.append({"label": "agentes", "value": len(agents)})
        if items:
            arts.append({"kind": "metrics", "title": "Decisión", "items": items})
        if agents:
            arts.append({"kind": "chips", "title": "Agentes activados", "items": list(agents)})
        if tickers:
            arts.append({"kind": "chips", "title": "Tickers", "items": list(tickers)[:30]})
        return arts

    # ── Synthesizer: respuesta estructurada ──
    if node_name == "synthesizer":
        sr = node_output.get("structured_response")
        resp = node_output.get("final_response") or ""
        if resp:
            arts.append({"kind": "summary", "title": "Respuesta final", "text": str(resp)})
        if isinstance(sr, dict) and sr:
            arts.append({"kind": "json", "title": "Respuesta estructurada", "data": sr})
        return arts

    # ── Context enricher: escribe bajo _market_pulse_context, no bajo su
    # nombre de nodo. Era el nodo con más tool-calls (30% en la semana del
    # 2026-08-05) y CERO artifacts: sus 60 cotizaciones descubiertas eran
    # inauditables por run. Ahora el inspector las enseña.
    if node_name == "context_enricher":
        ctx = (node_output.get("agent_results") or {}).get("_market_pulse_context")
        if not isinstance(ctx, dict) or not ctx:
            return []
        arts.append({"kind": "chips", "title": "Claves añadidas",
                     "items": [str(k) for k in ctx.keys()]})
        quotes = ctx.get("discovered_quotes")
        if isinstance(quotes, dict) and quotes:
            rows = []
            for sym, q in list(quotes.items())[:_MAX_TABLE_ROWS]:
                if not isinstance(q, dict):
                    continue
                rows.append([
                    str(sym), str(q.get("current_price")),
                    str(q.get("todaysChangePerc")),
                    str(q.get("premarket_change_percent")),
                    str(q.get("postmarket_change_percent")),
                    str(q.get("rvol")),
                ])
            if rows:
                arts.append({
                    "kind": "table",
                    "title": "Cotizaciones descubiertas",
                    "columns": ["symbol", "price", "chg%", "pm%", "ah%", "rvol"],
                    "rows": rows,
                    "total": len(rows),
                })
        raw = _raw_artifact(ctx)
        if raw:
            arts.append(raw)
        return arts

    # ── Agentes: agent_results[node] ──
    ar = node_output.get("agent_results", {})
    result = ar.get(node_name) if isinstance(ar, dict) else None
    if not isinstance(result, dict):
        return []

    if result.get("error"):
        arts.append({"kind": "summary", "title": "Error", "text": str(result["error"])})

    # Resumen humano si el agente lo produjo
    for key, title in (
        ("paraphrase", "Interpretación"),
        ("analysis", "Análisis"),
        ("summary", "Resumen"),
        ("interpretation", "Interpretación"),
    ):
        v = result.get(key)
        if isinstance(v, str) and len(v) > 10:
            arts.append({"kind": "summary", "title": title, "text": v})
            break

    metrics = _metrics_artifact(result)
    if metrics:
        arts.append(metrics)

    # ── Código / specs completos ──
    if node_name == "code_exec" and result.get("code"):
        arts.append(_code_artifact("Código generado", "python", result["code"]))
        # Resultados de la ejecución real en el sandbox (Fase 4b)
        arts.extend(_sandbox_artifacts(result))
        if result.get("exec_error"):
            arts.append(_code_artifact("Error de ejecución", "text", result["exec_error"]))
    if node_name == "screener" and result.get("filters_generated"):
        arts.append(_code_artifact("Filtros compilados", "json", result["filters_generated"]))
    if node_name == "strategy_scanner" and result.get("spec"):
        arts.append(_code_artifact("Spec compilada", "json", result["spec"]))
    if node_name == "alert_compiler" and result.get("spec"):
        arts.append(_code_artifact("AlertSpec compilada", "json", result["spec"]))
    if node_name == "backtest":
        cfg = (result.get("backtest_result") or {}).get("strategy_config") or result.get("strategy_config")
        if cfg:
            arts.append(_code_artifact("Configuración de estrategia", "json", cfg))

    # ── Tablas completas ──
    emitted_tables = 0
    seen_ids: set[int] = set()
    for title, path in _TABLE_PATHS.get(node_name, []):
        rows = _dig(result, path)
        if _is_row_list(rows) and id(rows) not in seen_ids:
            t = _rows_to_table(rows, title)
            if t:
                arts.append(t)
                seen_ids.add(id(rows))
                emitted_tables += 1

    # dry_run del alert_compiler: una tabla por día con TODOS los matches
    if node_name == "alert_compiler":
        dry = result.get("dry_run") or {}
        for day in (dry.get("per_day") or []):
            if emitted_tables >= _MAX_TABLES:
                break
            matches = day.get("matches") or []
            if _is_row_list(matches):
                t = _rows_to_table(matches, f"Dry-run {day.get('date', '')} · {day.get('count', len(matches))} disparos")
                if t:
                    arts.append(t)
                    emitted_tables += 1
        # Evidencia de charts (barras de minuto + fires + niveles)
        for i, ev in enumerate((dry.get("chart_evidence") or [])[:_MAX_CHARTS]):
            if isinstance(ev, dict):
                label = ev.get("symbol") or ev.get("ticker") or f"evidencia {i + 1}"
                arts.append({
                    "kind": "chart",
                    "title": f"Evidencia · {label}" + (f" · {ev.get('date')}" if ev.get("date") else ""),
                    "chart": ev,
                })

    # Barrido genérico: cualquier otra lista-de-dicts que no hayamos emitido.
    # `outputs`/`charts` del sandbox ya se emiten en _sandbox_artifacts.
    _skip_scan = ("dry_run", "outputs", "charts") if node_name == "code_exec" else ("dry_run",)
    if emitted_tables < _MAX_TABLES:
        for label, rows in _find_all_row_lists(result):
            if emitted_tables >= _MAX_TABLES:
                break
            if id(rows) in seen_ids or label.startswith(_skip_scan):
                continue
            t = _rows_to_table(rows, label)
            if t:
                arts.append(t)
                seen_ids.add(id(rows))
                emitted_tables += 1

    # ── Raw JSON al final (transparencia tipo notebook) ──
    raw = _raw_artifact(result)
    if raw:
        arts.append(raw)

    return arts
