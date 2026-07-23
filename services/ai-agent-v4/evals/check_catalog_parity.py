"""
Catálogo↔gateway parity gate.

El catálogo estático (agents/mcp_catalog.py) y el gateway MCP en vivo pueden
divergir en silencio: una tool renombrada en el gateway rompe agentes en
runtime; una tool nueva en el gateway sin declarar queda inalcanzable. Hoy
esto solo se logueaba al arranque. Este script lo convierte en un gate:

  - `missing`  (declaradas pero NO en el gateway) → las llamadas darán 404.
    Es la dirección peligrosa → exit 1.
  - `undeclared` (en el gateway pero NO declaradas) → capacidad huérfana,
    informativo → no falla (pero se reporta).

Uso (dentro del contenedor):
    python -m evals.check_catalog_parity
"""
from __future__ import annotations

import asyncio
import sys


async def run() -> int:
    from agents._mcp_tools import _get_client
    from agents.mcp_catalog import all_catalog_tools

    declared = {t.full_name for t in all_catalog_tools()}
    try:
        client = await _get_client()
        resp = await client.get("/api/tools")
        data = resp.json()
        live = {t["name"] for t in data.get("tools", [])}
    except Exception as exc:  # noqa: BLE001
        print(f"[error] gateway unreachable: {exc}", file=sys.stderr)
        return 2

    if not live:
        print("[error] gateway returned empty tool list", file=sys.stderr)
        return 2

    missing = sorted(declared - live)
    undeclared = sorted(live - declared)

    print(f"declared={len(declared)}  live={len(live)}  "
          f"missing={len(missing)}  undeclared={len(undeclared)}")
    if missing:
        print(f"  MISSING (declared, not on gateway → 404 risk): {missing}")
    if undeclared:
        print(f"  UNDECLARED (on gateway, not in catalog → orphan): {undeclared}")
    if not missing and not undeclared:
        print("  PARITY OK")

    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
