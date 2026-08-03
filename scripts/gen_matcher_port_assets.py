#!/usr/bin/env python3
"""Genera las definiciones del matcher portado DESDE el fuente vivo.

Fuente de verdad: services/websocket_server/src/index.js. Este script parsea
mecánicamente las regiones del matcher (la lista ordenada de comprobaciones
chkEvt, las listas ENRICHED_*, el REMAP, los sets del payload y los filtros de
índice) y emite services/backtester/matching/matcher_defs_generated.py.

Así el port de Python no duplica NADA a mano: si el matcher vivo cambia, se
regenera; y el modo --check (CI) detecta el desfase.

    python3 scripts/gen_matcher_port_assets.py          # regenerar
    python3 scripts/gen_matcher_port_assets.py --check  # verificar al día

Falla (exit 2) si alguna expresión chkEvt del fuente no encaja en los patrones
conocidos — un cambio de forma en el matcher rompe el build en vez de callar.
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "services/websocket_server/src/index.js"
OUT = ROOT / "services/backtester/matching/matcher_defs_generated.py"

CHK_RE = re.compile(
    r"if \(!chkEvt\((.+?), '([A-Za-z0-9_]+Min)', '([A-Za-z0-9_]+Max)'\)\) return false;"
)
EXPR_PATTERNS = [
    (re.compile(r"^evt\.(\w+)$"), "evt"),
    (re.compile(r"^enriched\.(\w+)$"), "enr"),
    (re.compile(r"^val\('(\w+)', '(\w+)'\)$"), "val"),
    (re.compile(r"^spread$"), "spread"),
    (re.compile(r"^minutesSinceMarketOpen\(evt\.timestamp\)$"), "mso"),
]


def js_string_array(src: str, name: str) -> list:
    """Extrae los strings del primer [...] tras `name` (array plano o new Set([...]))."""
    m = re.search(re.escape(name) + r"[^\[]*\[([^\]]*)\]", src, re.S)
    if not m:
        raise SystemExit(f"ERROR: no encuentro el array {name}")
    return re.findall(r'"([^"]+)"', m.group(1))


def main() -> None:
    src = SRC.read_text(encoding="utf-8")

    a = src.index("function eventPassesSubscription")
    b = src.index("\n  return true;\n}", a)
    body = src[a:b]

    checks, errors = [], []
    for expr, min_key, max_key in CHK_RE.findall(body):
        expr = expr.strip()
        for pat, kind in EXPR_PATTERNS:
            m = pat.match(expr)
            if m:
                checks.append((kind, list(m.groups()), min_key, max_key))
                break
        else:
            errors.append(f"expresion chkEvt no reconocida: {expr!r}")
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)

    bm = src.index("function broadcastMarketEvent")
    payload_str = js_string_array(src[bm:], "const STRING_FIELDS")
    payload_int = js_string_array(src[bm:], "const INT_FIELDS")

    enr_float = js_string_array(src, "const ENRICHED_FLOAT_FIELDS")
    enr_int = js_string_array(src, "const ENRICHED_INT_FIELDS")
    enr_str = js_string_array(src, "const ENRICHED_STRING_FIELDS")

    m = re.search(r"const ENRICHED_KEY_REMAP = \{(.*?)\};", src, re.S)
    if not m:
        raise SystemExit("ERROR: no encuentro ENRICHED_KEY_REMAP")
    remap = dict(re.findall(r'(\w+):\s*"([^"]+)"', m.group(1)))

    m = re.search(r"const INDEX_FILTER_DEFS = \[(.*?)\];", src, re.S)
    idx_defs = re.findall(r"\['(\w+)', '(\w+)'\]", m.group(1))
    m = re.search(r"const INDEX_FILTER_WINDOWS = \[(.*?)\];", src, re.S)
    idx_windows = [
        (w, None if f == "null" else f.strip("'"))
        for w, f in re.findall(r"\['(\w+)', (null|'\w+')\]", m.group(1))
    ]

    sha = hashlib.sha256(src.encode()).hexdigest()

    def fmt(obj) -> str:
        return repr(obj)

    content = f'''"""AUTO-GENERADO — NO EDITAR A MANO.

Fuente de verdad: services/websocket_server/src/index.js
Regenerar con:    python3 scripts/gen_matcher_port_assets.py
"""

SOURCE_SHA256 = "{sha}"

# (kind, args, min_key, max_key) en el orden del fuente.
# kind: evt | enr | val | spread | mso
CHECKS = {fmt(checks)}

PAYLOAD_STRING_FIELDS = frozenset({fmt(payload_str)})
PAYLOAD_INT_FIELDS = frozenset({fmt(payload_int)})

ENRICHED_FLOAT_FIELDS = {fmt(enr_float)}
ENRICHED_INT_FIELDS = {fmt(enr_int)}
ENRICHED_STRING_FIELDS = {fmt(enr_str)}
ENRICHED_KEY_REMAP = {fmt(remap)}

INDEX_FILTER_DEFS = {fmt(idx_defs)}
INDEX_FILTER_WINDOWS = {fmt(idx_windows)}
'''

    if "--check" in sys.argv:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != content:
            print("STALE: regenerar con python3 scripts/gen_matcher_port_assets.py", file=sys.stderr)
            sys.exit(1)
        print(f"OK — {len(checks)} comprobaciones, defs del matcher al día")
        return
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(content, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(checks)} comprobaciones chkEvt)")


if __name__ == "__main__":
    main()
