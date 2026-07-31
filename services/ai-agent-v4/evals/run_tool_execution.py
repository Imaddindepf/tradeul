"""
Gate de EJECUCIÓN de tools contra el gateway MCP en vivo.

check_catalog_parity.py garantiza que cada tool declarada EXISTE en el
gateway; este gate garantiza que además FUNCIONA: llama cada tool del
catálogo con argumentos mínimos y exige HTTP 200. Cubre el hueco que dejó
pasar events_get_events_by_ticker rota 5 meses (TypeError FunctionTool,
auditoría 2026-07-28): los evals de routing validaban nombres, nunca
ejecutaban nada — 29/29 verdes con una tool que fallaba el 100% de las veces.

Uso (dentro del contenedor del agente):
    python -m evals.run_tool_execution           # tools baratas (por defecto)
    python -m evals.run_tool_execution --all     # incluye las caras/lentas

Exit codes: 0 ok · 1 alguna tool falló · 2 gateway inaccesible.
"""
from __future__ import annotations

import asyncio
import sys
import time

# Args explícitos por tool (fusionan SOBRE lo sintetizado del input_schema
# que expone GET /api/tools). Mantener llamadas mínimas: esto corre contra
# producción.
FIXTURES: dict[str, dict] = {
    "events_get_recent_events": {"count": 1},
    "events_get_events_by_ticker": {"symbol": "AAPL", "count": 1},
    "events_query_historical_events": {"symbol": "AAPL", "limit": 1},
    "events_get_event_stats": {"symbol": "AAPL"},
    "news_get_latest_news": {"count": 1},
    "news_get_news_by_ticker": {"symbol": "AAPL", "count": 1},
    "news_get_catalyst_alerts": {"count": 1},
    "historical_get_day_bars": {"date": "yesterday", "symbols": ["AAPL"], "limit": 1},
    "historical_get_minute_bars": {"date": "yesterday", "symbol": "AAPL"},
    "historical_get_top_movers": {"date": "yesterday"},
    "market_pulse_analyze_market": {"queries": [{"group": "sectors"}]},
    "screener_search_by_theme": {"themes": ["AI"]},
    "scanner_get_enriched_batch": {"symbols": ["AAPL"]},
    "screener_enrich_with_classification": {"symbols": ["AAPL"]},
    "analytics_get_rvol_batch": {"symbols": ["AAPL"]},
    "strategy_scan_day_setups": {"steps": [{"event_types": ["new_high"]}], "limit": 1},
}

# Args que solo existen en runtime: se derivan de una tool hermana antes del
# gate (accession real, event_id real, ticker del universo de dilución — AAPL
# no está en él). Si la derivación falla, la tool se salta con aviso.
DERIVED_FIXTURES: dict[str, tuple] = {
    # sec_get_filing_detail: en KNOWN_BROKEN — reactivar esta derivación al arreglarla:
    # "sec_get_filing_detail": ("sec_get_recent_filings", {}, ("accessionNo", "accession_number", "accessionNumber"), "accession_number"),
    "predictions_get_prediction_price_history": ("predictions_get_prediction_events", {}, ("event_id", "event_ticker"), "event_id"),
    "dilution_get_instrument_context": ("dilution_get_trending_dilution", {}, ("ticker", "symbol"), "ticker"),
    "dilution_get_dilution_risk_ratings": ("dilution_get_trending_dilution", {}, ("ticker", "symbol"), "ticker"),
}

# Tools rotas conocidas: se saltan SIEMPRE con aviso ruidoso — quitar de aquí
# al arreglarlas para que el gate vuelva a ejercitarlas.
KNOWN_BROKEN: dict[str, str] = {
    "screener_get_daily_indicators": "GET /api/v1/indicators no existe en el servicio screener (detectado por este gate 2026-07-28)",
    "sec_get_filing_detail": "GET /api/v1/filings/{accession} no existe en el servicio sec-filings (detectado por este gate 2026-07-28)",
}


def _find_key(obj, keys: tuple):
    """DFS por dicts/listas anidados buscando la primera clave candidata."""
    if isinstance(obj, dict):
        for k in keys:
            if k in obj and obj[k] not in (None, ""):
                return obj[k]
        for v in obj.values():
            found = _find_key(v, keys)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _find_key(item, keys)
            if found is not None:
                return found
    return None

SKIP_EXPENSIVE: dict[str, str] = {
    "strategy_get_event_catalog": "agregación ~140s en frío (la calienta el warmer del gateway)",
    "strategy_scan_day_setups": "scan SQL pesado sobre ~12M eventos/día",
    "dilution_get_cash_position": "latencia observada ~12s",
    "dilution_get_dilution_analysis": "compone varias llamadas SEC lentas",
    "dilution_get_atm_offerings": "upstream SEC >30s (visto en smoke 2026-07-28)",
}

_TYPE_DEFAULTS = {"string": "AAPL", "integer": 1, "number": 1.0, "boolean": False,
                  "array": [], "object": {}}
_NAME_HINTS = {
    "symbol": "AAPL", "ticker": "AAPL", "query": "AAPL", "theme": "AI",
    "symbols": ["AAPL"], "tickers": ["AAPL"], "date": None,  # None → hoy
    "count": 1, "limit": 1, "days": 1,
}


def _synth_args(schema: dict | None) -> dict:
    if not schema or not isinstance(schema, dict):
        return {}
    args: dict = {}
    props = schema.get("properties") or {}
    for name in schema.get("required") or []:
        prop = props.get(name) or {}
        if name in _NAME_HINTS:
            hint = _NAME_HINTS[name]
            args[name] = time.strftime("%Y-%m-%d") if hint is None else hint
            continue
        ptype = prop.get("type")
        if ptype is None:
            for branch in prop.get("anyOf") or []:
                if branch.get("type") not in (None, "null"):
                    ptype = branch["type"]
                    break
        args[name] = _TYPE_DEFAULTS.get(ptype, "AAPL")
    return args


async def run(include_all: bool) -> int:
    from agents._mcp_tools import _get_client
    from agents.mcp_catalog import all_catalog_tools

    declared = {t.full_name for t in all_catalog_tools()}
    client = await _get_client()
    try:
        resp = await client.get("/api/tools")
        listing = resp.json().get("tools") or []
    except Exception as exc:  # noqa: BLE001
        print(f"[error] gateway inaccesible: {exc}", file=sys.stderr)
        return 2
    if not listing:
        print("[error] el gateway devolvió una lista de tools vacía", file=sys.stderr)
        return 2

    schemas = {t["name"]: t.get("input_schema") for t in listing}
    live_names = set(schemas)
    for key in sorted((set(FIXTURES) | set(SKIP_EXPENSIVE) | set(KNOWN_BROKEN)
                       | set(DERIVED_FIXTURES)) - live_names):
        print(f"  AVISO: FIXTURES/SKIP/KNOWN_BROKEN referencia una tool inexistente: {key}")

    # Derivar args runtime-dependientes desde tools hermanas
    underivable: dict[str, str] = {}
    for target, (source, src_args, keys, param) in DERIVED_FIXTURES.items():
        if target not in live_names:
            continue
        try:
            resp = await client.post(f"/api/tool/{source}", json=src_args, timeout=30.0)
            value = _find_key(resp.json().get("result"), keys) if resp.status_code == 200 else None
        except Exception:  # noqa: BLE001
            value = None
        if value is None:
            underivable[target] = f"no se pudo derivar `{param}` desde {source}"
        else:
            FIXTURES.setdefault(target, {})[param] = value

    failures: list[str] = []
    skipped = 0
    for name in sorted(declared):
        if name in KNOWN_BROKEN:
            print(f"  BROKEN-KNOWN  {name} ({KNOWN_BROKEN[name]})")
            skipped += 1
            continue
        if name in underivable:
            print(f"  skip          {name} ({underivable[name]})")
            skipped += 1
            continue
        if not include_all and name in SKIP_EXPENSIVE:
            print(f"  skip          {name} ({SKIP_EXPENSIVE[name]})")
            skipped += 1
            continue
        args = _synth_args(schemas.get(name))
        args.update(FIXTURES.get(name, {}))
        t0 = time.monotonic()
        err = None
        try:
            resp = await client.post(f"/api/tool/{name}", json=args, timeout=30.0)
            status = resp.status_code
            body = resp.text[:200]
            if status == 200:
                # error in-band: HTTP 200 con {"result": {"error": ...}} — el
                # agente lo trata como fallo (MCPToolError); el gate también.
                result = resp.json().get("result")
                if isinstance(result, dict) and result.get("error"):
                    err = str(result["error"])[:150]
        except Exception as exc:  # noqa: BLE001
            status, body = -1, f"{type(exc).__name__}: {exc}"
        ms = int((time.monotonic() - t0) * 1000)
        ok = status == 200 and err is None
        slow = "  [LENTA >5s]" if ok and ms > 5000 else ""
        print(f"  {'ok  ' if ok else 'FAIL'} {status:>4} {ms:>7}ms  {name}{slow}")
        if not ok:
            failures.append(f"{name}: HTTP {status} — " + (f"error in-band: {err}" if err else body))

    print(f"\nejecutadas={len(declared) - skipped}  fallos={len(failures)}  saltadas={skipped}")
    if failures:
        print("FALLOS:")
        for f in failures:
            print(f"  {f}")
        return 1
    print("EXECUTION OK — todas las tools del catálogo responden 200")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run(include_all="--all" in sys.argv[1:])))
