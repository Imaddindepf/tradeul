"""
Rich per-node summaries for the live execution canvas.

Each completed graph node emits a `node_completed` WS event. Besides the
human-readable `preview`, we attach a small structured `data` payload the
frontend renders INSIDE the node card: real metrics, a sample of the actual
table the agent produced, the compiled spec/filters/code, tickers, errors.

The payload is intentionally tiny (~2-4 KB): a handful of metrics, up to
6 rows x 6 columns of table sample, and a few hundred chars of code.
"""
from __future__ import annotations

from typing import Any

# Preferred (title, path) locations of tabular data per agent. Searched in
# order; the first list-of-dicts found wins. Fallback: recursive scan.
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

# Priority columns when a row has more keys than we can show.
_PRIORITY_COLS = [
    "symbol", "ticker", "title", "name", "company_name",
    "price", "close", "open", "change_percent", "change_pct", "close_vs_open_pct",
    "rvol", "volume", "market_cap", "sector", "event_type", "date", "created",
]

_MAX_ROWS = 6
_MAX_COLS = 5
_MAX_METRICS = 6
_MAX_CODE_CHARS = 900


def _fmt_cell(v: Any) -> str:
    if isinstance(v, float):
        if abs(v) >= 1_000_000_000:
            return f"{v / 1_000_000_000:.2f}B"
        if abs(v) >= 1_000_000:
            return f"{v / 1_000_000:.1f}M"
        return f"{v:,.2f}"
    if isinstance(v, int) and abs(v) >= 1_000_000:
        return f"{v / 1_000_000_000:.2f}B" if abs(v) >= 1_000_000_000 else f"{v / 1_000_000:.1f}M"
    s = str(v)
    return s[:38] + "…" if len(s) > 39 else s


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


def _find_rows_recursive(obj: Any, depth: int = 0) -> list[dict] | None:
    """First list-of-dicts anywhere in the result (bounded depth)."""
    if depth > 3 or not isinstance(obj, dict):
        return None
    for v in obj.values():
        if _is_row_list(v):
            return v
    for v in obj.values():
        found = _find_rows_recursive(v, depth + 1)
        if found:
            return found
    return None


def _rows_to_table(rows: list[dict], title: str | None) -> dict | None:
    scalar_keys: list[str] = []
    for key, val in rows[0].items():
        if isinstance(val, (str, int, float, bool)) or val is None:
            scalar_keys.append(key)
    if not scalar_keys:
        return None
    # Priority columns first, keep original order for the rest
    cols = sorted(
        scalar_keys,
        key=lambda k: (_PRIORITY_COLS.index(k) if k in _PRIORITY_COLS else 99),
    )[:_MAX_COLS]
    table_rows = [
        [_fmt_cell(row.get(c, "")) for c in cols]
        for row in rows[:_MAX_ROWS]
    ]
    out: dict[str, Any] = {"columns": cols, "rows": table_rows, "total": len(rows)}
    if title:
        out["title"] = title
    return out


def _extract_table(agent: str, result: dict) -> dict | None:
    for title, path in _TABLE_PATHS.get(agent, []):
        rows = _dig(result, path)
        if _is_row_list(rows):
            return _rows_to_table(rows, title)
    rows = _find_rows_recursive(result)
    if rows:
        return _rows_to_table(rows, None)
    return None


def _extract_code(agent: str, result: dict) -> dict | None:
    """Generated code or the compiled spec/filters — the 'how' of the node."""
    import json

    if agent == "code_exec" and result.get("code"):
        return {"language": "python", "content": str(result["code"])[:_MAX_CODE_CHARS]}
    if agent == "screener" and result.get("filters_generated"):
        return {
            "language": "json",
            "content": json.dumps(result["filters_generated"], indent=1, ensure_ascii=False)[:_MAX_CODE_CHARS],
        }
    if agent == "strategy_scanner" and result.get("spec"):
        return {
            "language": "json",
            "content": json.dumps(result["spec"], indent=1, ensure_ascii=False)[:_MAX_CODE_CHARS],
        }
    if agent == "backtest":
        cfg = (result.get("backtest_result") or {}).get("strategy_config") or result.get("strategy_config")
        if cfg:
            return {"language": "json", "content": json.dumps(cfg, indent=1, ensure_ascii=False)[:_MAX_CODE_CHARS]}
    return None


def _extract_metrics(result: dict) -> dict[str, Any]:
    """Small top-level scalars: counts, statuses, modes."""
    metrics: dict[str, Any] = {}
    for key, val in result.items():
        if key.startswith("_") or key in ("error", "code", "raw_output", "query_interpreted"):
            continue
        if isinstance(val, bool):
            continue
        if isinstance(val, (int, float)):
            metrics[key] = val
        elif isinstance(val, str) and 0 < len(val) <= 24:
            metrics[key] = val
        elif isinstance(val, list) and val and all(isinstance(x, str) for x in val) and key != "tickers_queried":
            metrics[key] = f"{len(val)}"
        if len(metrics) >= _MAX_METRICS:
            break
    # Nested counts worth surfacing
    for path, label in (
        (("scan_results", "count"), "matches"),
        (("screen_results", "total_matched"), "matched"),
    ):
        v = _dig(result, path)
        if isinstance(v, (int, float)):
            metrics[label] = v
    return metrics


def summarize_node_output(node_name: str, node_output: Any) -> tuple[str, dict | None]:
    """(human preview, structured card data) for a completed graph node."""
    if not isinstance(node_output, dict):
        return "", None

    # ── Planner: routing decision ──
    if node_name in ("query_planner", "supervisor"):
        intent = node_output.get("intent") or ""
        tickers = node_output.get("tickers") or []
        agents = node_output.get("active_agents") or []
        plan = (node_output.get("plan") or "")[:220]
        data: dict[str, Any] = {"metrics": {}}
        if intent:
            data["metrics"]["intent"] = intent
        if agents:
            data["metrics"]["agentes"] = len(agents)
            data["routing"] = agents
        if tickers:
            data["tickers"] = tickers[:8]
        if plan:
            data["text"] = plan
        preview = f"{intent} → {', '.join(agents)}" if agents else intent
        return preview, (data if (data["metrics"] or data.get("tickers")) else None)

    # ── Synthesizer: response shape ──
    if node_name == "synthesizer":
        resp = node_output.get("final_response") or ""
        sr = node_output.get("structured_response") or {}
        sections = len(sr.get("sections", [])) if isinstance(sr, dict) else 0
        metrics: dict[str, Any] = {"caracteres": len(resp)}
        if sections:
            metrics["secciones"] = sections
        preview = f"Respuesta lista ({len(resp)} chars" + (f", {sections} secciones)" if sections else ")")
        return preview, {"metrics": metrics}

    # ── Agents: extract from agent_results[node] ──
    ar = node_output.get("agent_results", {})
    result = ar.get(node_name) if isinstance(ar, dict) else None
    if not isinstance(result, dict):
        # context_enricher etc: nothing card-worthy
        return "", None

    data = {}
    if result.get("error"):
        err = str(result["error"])[:220]
        return f"Error: {err}", {"error": err}

    table = _extract_table(node_name, result)
    if table:
        data["table"] = table
    code = _extract_code(node_name, result)
    if code:
        data["code"] = code
    metrics = _extract_metrics(result)
    if metrics:
        data["metrics"] = metrics
    errs = result.get("_errors")
    if isinstance(errs, list) and errs:
        data["error"] = str(errs[0])[:220]

    # Human preview line
    if table and table.get("total"):
        preview = f"{table['total']} filas de datos"
        if table.get("title"):
            preview = f"{table['title']}: {table['total']} filas"
    elif code:
        preview = "Spec compilada" if code["language"] == "json" else "Código generado"
    elif metrics:
        preview = ", ".join(f"{k}: {v}" for k, v in list(metrics.items())[:3])
    else:
        preview = "Completado"

    return preview, (data or None)
