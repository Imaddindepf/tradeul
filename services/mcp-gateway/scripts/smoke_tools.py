#!/usr/bin/env python3
"""
Smoke test del MCP Gateway — dos modos:

  --static  Importa main.py (compone el gateway con los 14 servidores) y
            enumera el registro completo de tools. Falla si algún módulo no
            importa o si el total cae por debajo del mínimo esperado. Corre
            EN EL BUILD del Dockerfile: una imagen que no registra sus tools
            no llega a producción.

  --live    Ejercita cada tool registrada a través del dispatch REST real
            (POST /api/tool/<name>) con argumentos mínimos sintetizados del
            input_schema. Detecta exactamente la clase de fallo que mantuvo
            events_get_events_by_ticker roto 5 meses: una tool que registra
            bien pero revienta al ejecutarse. Correr tras cada deploy:
              python scripts/smoke_tools.py --live [--url http://localhost:8050]
              [--token $MCP_GATEWAY_TOKEN] [--all]

Sale con código 1 si algo falla. Solo stdlib (urllib) en modo --live.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

# Total esperado de tools (hoy: 69). Al añadir tools sube solo; si BAJA de
# aquí es que algo se des-registró — actualizar el número es un acto
# consciente, no un ajuste para que pase el build.
MIN_TOOLS = 69

# Cada dominio montado debe registrar >=1 tool: MIN_TOOLS solo no detecta la
# caída de un módulo pequeño (hallazgo revisión 2026-07-28).
EXPECTED_PREFIXES = {
    "scanner", "events", "news", "earnings", "sec", "financials", "dilution",
    "screener", "historical", "analytics", "patterns", "predictions",
    "market_pulse", "strategy",
}
ROOT_TOOLS = {"get_platform_status", "get_full_ticker_analysis"}

# Args explícitos para tools cuyo schema no basta para una llamada barata.
# Se fusionan SOBRE lo sintetizado del schema.
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

# Tools cuyos args solo existen en runtime (un accession real, un event_id
# real, un ticker del universo de dilución — AAPL no está en él): se derivan
# llamando antes a una tool hermana. Si la derivación falla, se saltan con
# aviso en vez de fallar con args inventados.
#   destino -> (tool fuente, args fuente, claves candidatas, param destino)
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


def _find_key(obj, keys: tuple) -> object:
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

# Tools caras o de larga latencia: solo con --all. La razón queda impresa.
SKIP_EXPENSIVE: dict[str, str] = {
    "strategy_get_event_catalog": "agregación ~140s en frío (la calienta el warmer)",
    "strategy_scan_day_setups": "scan SQL pesado sobre ~12M eventos/día",
    "dilution_get_cash_position": "latencia observada ~12s (auditoría 2026-07-28)",
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


def synth_args(schema: dict | None) -> dict:
    """Argumentos mínimos válidos a partir del JSON schema de la tool."""
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


def _post(url: str, payload: dict, token: str, timeout: float) -> tuple[int, str]:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json",
                 **({"X-MCP-Token": token} if token else {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            # cuerpo completo: hace falta para detectar errores in-band
            return resp.status, resp.read().decode(errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode(errors="replace")


def inband_error(body: str) -> str | None:
    """Los tools señalan fallo con HTTP 200 y {"result": {"error": ...}} (74
    return sites en 13 módulos). El agente los trata como fallo (MCPToolError):
    el smoke también debe hacerlo o queda ciego a caídas de DB/upstreams
    (hallazgo revisión 2026-07-28). Devuelve el mensaje de error o None."""
    try:
        result = json.loads(body).get("result")
    except Exception:
        return None
    if isinstance(result, dict) and result.get("error"):
        return str(result["error"])[:150]
    return None


def _get(url: str, token: str, timeout: float = 15) -> dict:
    req = urllib.request.Request(
        url, headers={"X-MCP-Token": token} if token else {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def run_static() -> int:
    import asyncio
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        import main  # compone gateway + monta los 14 servidores
    except Exception as exc:  # noqa: BLE001
        print(f"FALLO: main.py no importa: {type(exc).__name__}: {exc}")
        return 1
    tools = asyncio.run(main.gateway.get_tools())
    names = sorted(tools) if isinstance(tools, dict) else sorted(t.name for t in tools)
    by_prefix: dict[str, int] = {}
    for n in names:
        by_prefix[n.split("_", 1)[0]] = by_prefix.get(n.split("_", 1)[0], 0) + 1
    print(f"static OK: {len(names)} tools registradas en {len(by_prefix)} dominios")
    for prefix, cnt in sorted(by_prefix.items()):
        print(f"  {prefix:14s} {cnt}")
    return _check_registry(names)


def _check_registry(names: list[str]) -> int:
    """Garantías del registro: total mínimo, >=1 tool por dominio montado,
    y las tools de nivel gateway presentes."""
    problems = []
    if len(names) < MIN_TOOLS:
        problems.append(f"total {len(names)} < mínimo esperado {MIN_TOOLS}")
    for prefix in sorted(EXPECTED_PREFIXES):
        if not any(n.startswith(prefix + "_") for n in names):
            problems.append(f"dominio `{prefix}` sin tools registradas")
    for tool in sorted(ROOT_TOOLS):
        if tool not in names:
            problems.append(f"tool de gateway `{tool}` ausente")
    if problems:
        print("FALLO en garantías del registro:")
        for p in problems:
            print(f"  {p}")
        return 1
    return 0


def run_live(base_url: str, token: str, include_all: bool, timeout: float) -> int:
    listing = _get(f"{base_url}/api/tools", token)
    tools = listing.get("tools") or []
    names = [t["name"] for t in tools]
    if _check_registry(names) != 0:
        return 1

    # fixtures/skips huérfanos = tool renombrada: avisar para que no queden
    # skips muertos o fixtures sin efecto (hallazgo revisión 2026-07-28)
    for key in sorted((set(FIXTURES) | set(SKIP_EXPENSIVE) | set(KNOWN_BROKEN)
                       | set(DERIVED_FIXTURES)) - set(names)):
        print(f"  AVISO: FIXTURES/SKIP/KNOWN_BROKEN referencia una tool inexistente: {key}")

    # Derivar args runtime-dependientes desde tools hermanas
    underivable: dict[str, str] = {}
    for target, (source, src_args, keys, param) in DERIVED_FIXTURES.items():
        if target not in names:
            continue
        try:
            status, body = _post(f"{base_url}/api/tool/{source}", src_args, token, timeout)
            value = _find_key(json.loads(body).get("result"), keys) if status == 200 else None
        except Exception:  # noqa: BLE001
            value = None
        if value is None:
            underivable[target] = f"no se pudo derivar `{param}` desde {source}"
        else:
            FIXTURES.setdefault(target, {})[param] = value

    failures: list[str] = []
    skipped: list[str] = []
    for entry in sorted(tools, key=lambda t: t["name"]):
        name = entry["name"]
        if name in KNOWN_BROKEN:
            print(f"  BROKEN-KNOWN  {name} ({KNOWN_BROKEN[name]})")
            continue
        if name in underivable:
            print(f"  skip          {name} ({underivable[name]})")
            continue
        if not include_all and name in SKIP_EXPENSIVE:
            skipped.append(name)
            continue
        args = synth_args(entry.get("input_schema"))
        args.update(FIXTURES.get(name, {}))
        t0 = time.monotonic()
        try:
            status, body = _post(f"{base_url}/api/tool/{name}", args, token, timeout)
        except Exception as exc:  # noqa: BLE001
            status, body = -1, f"{type(exc).__name__}: {exc}"
        ms = int((time.monotonic() - t0) * 1000)
        err = inband_error(body) if status == 200 else None
        ok = status == 200 and err is None
        mark = "ok  " if ok else "FAIL"
        slow = "  [LENTA >5s]" if ok and ms > 5000 else ""
        print(f"  {mark} {status:>4} {ms:>7}ms  {name}{slow}")
        if not ok:
            failures.append(f"{name}: HTTP {status} — " + (f"error in-band: {err}" if err else body[:200]))

    for name in skipped:
        print(f"  skip          {name} ({SKIP_EXPENSIVE[name]})")
    executed = len(tools) - len(skipped) - len(underivable) - sum(1 for n in names if n in KNOWN_BROKEN)
    print(f"\nlive: {executed - len(failures)} ok, {len(failures)} fallos, "
          f"{len(skipped) + len(underivable)} saltadas, "
          f"{sum(1 for n in names if n in KNOWN_BROKEN)} rotas conocidas")
    if failures:
        print("FALLOS:")
        for f in failures:
            print(f"  {f}")
        return 1
    return 0


def main_cli() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--static", action="store_true")
    mode.add_argument("--live", action="store_true")
    ap.add_argument("--url", default=os.getenv("MCP_GATEWAY_URL", "http://localhost:8050"))
    ap.add_argument("--token", default=os.getenv("MCP_GATEWAY_TOKEN", ""))
    ap.add_argument("--all", action="store_true", help="incluye las tools caras")
    ap.add_argument("--timeout", type=float, default=30.0)
    ns = ap.parse_args()
    if ns.static:
        return run_static()
    return run_live(ns.url.rstrip("/"), ns.token.strip(), ns.all, ns.timeout)


if __name__ == "__main__":
    sys.exit(main_cli())
