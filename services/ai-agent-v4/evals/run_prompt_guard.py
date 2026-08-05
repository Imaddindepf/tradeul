"""
Prompt and payload guard.

    docker exec tradeul_ai_agent_v4 python -m evals.run_prompt_guard

Three invariants that nothing else checks, all three broken in production at
some point on 2026-07-29:

  1. Every prompt template renders. The synthesizer prompt documents JSON
     shapes to the model, and str.format() read {"available": false} as a
     replacement field: KeyError on every single query, silently degrading
     every answer to plain markdown for weeks.

  2. Trimming an oversized agent payload leaves valid JSON. The old trim cut
     the serialised text at 4000 characters, mid-row, and the model dutifully
     produced a table that stopped halfway through a company.

  3. A question naming several windows produces several windows. Collapsing
     them to one silently answered half the question.

Offline: no network, no model, no gateway. Exit code 1 on any failure, so it
can gate a deploy.
"""
from __future__ import annotations

import json
import string
import sys
from datetime import datetime, timezone

failures: list[str] = []
checks = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if condition:
        print(f"  [PASS] {name}")
    else:
        print(f"  [FAIL] {name}" + (f"  <- {detail}" if detail else ""))
        failures.append(name)


# ── 1. Prompts ──────────────────────────────────────────────────────
print("\nPrompt rendering")

from agents._prompts import PromptError, placeholders, render  # noqa: E402

check("render leaves JSON braces alone",
      render("keep {\"available\": false} and <<x>>", x="ok")
      == "keep {\"available\": false} and ok")

check("render leaves prices alone",
      render("EPS was $3.84 <<x>>", x="ok") == "EPS was $3.84 ok")

try:
    render("<<a>> and <<b>>", a="1")
    check("missing value raises", False, "no exception")
except PromptError:
    check("missing value raises", True)

try:
    render("<<a>>", a="1", stale="2")
    check("stale value raises", False, "no exception")
except PromptError:
    check("stale value raises", True)

from agents.synthesizer import STRUCTURED_PROMPT  # noqa: E402

_now = datetime.now(timezone.utc)
try:
    rendered = render(
        STRUCTURED_PROMPT,
        current_date=_now.strftime("%B %d, %Y"),
        last_fy=_now.year - 1,
    )
    check("STRUCTURED_PROMPT renders", True)
    check("no placeholder survives rendering", not placeholders(rendered))
    check("JSON examples survive rendering", '"available"' in rendered)
except PromptError as exc:
    check("STRUCTURED_PROMPT renders", False, str(exc))

# Any prompt still going through str.format() must be free of stray braces.
import importlib  # noqa: E402

for mod_name, const in (
    ("agents.alert_compiler", "_REPAIR_PROMPT"),
    ("agents.brief_router", "_CLASSIFIER_PROMPT"),
    ("agents.code_exec", "CODE_GEN_PROMPT"),
    ("agents.code_exec", "_REPAIR_PROMPT"),
):
    try:
        template = getattr(importlib.import_module(mod_name), const, None)
    except Exception as exc:  # noqa: BLE001
        check(f"{const} importable", False, str(exc))
        continue
    if template is None:
        continue
    fields = [f for _, f, _, _ in string.Formatter().parse(template) if f is not None]
    stray = [f for f in fields if not f.replace("_", "").isalnum()]
    check(f"{const} has no JSON-looking format field", not stray, str(stray))


# ── 2. Payload trimming ─────────────────────────────────────────────
print("\nPayload trimming")

from agents.synthesizer import _drop_items, _safe_json_size  # noqa: E402

rows = {"results": [{"symbol": f"T{i}", "eps": 1.0, "note": "x" * 50} for i in range(200)]}
trimmed = _drop_items(rows, _safe_json_size(rows), 2000)
try:
    json.dumps(trimmed)
    check("trimmed dict is valid JSON", True)
except (TypeError, ValueError) as exc:
    check("trimmed dict is valid JSON", False, str(exc))

check("trimmed dict keeps whole rows",
      all(isinstance(r, dict) and ("symbol" in r or "_omitted" in r)
          for r in trimmed["results"]))
check("trimmed dict reports what it dropped",
      any("_omitted" in r for r in trimmed["results"] if isinstance(r, dict)))
check("trimmed dict is smaller", _safe_json_size(trimmed) < _safe_json_size(rows))

big_list = [{"symbol": f"S{i}"} for i in range(500)]
trimmed_list = _drop_items(big_list, _safe_json_size(big_list), 1000)
check("trimmed list is valid JSON", bool(json.dumps(trimmed_list)))
check("trimmed list is shorter", len(trimmed_list) < len(big_list))

check("small values pass through untouched",
      _drop_items({"a": 1}, 10, 30_000) == {"a": 1})


# ── 3. Question windows ─────────────────────────────────────────────
print("\nEarnings windows")

from agents.news_events import _extract_earnings_windows  # noqa: E402

_today = datetime.now()


def _slots(text: str) -> list[str | None]:
    return [slot for _, slot in _extract_earnings_windows(text)]


def _count(text: str) -> int:
    return len(_extract_earnings_windows(text))


CASES: list[tuple[str, str, int, list[str | None]]] = [
    ("double es slot+day", "top earnings de esta mañana pre market y de ayer after hour", 2, ["bmo", "amc"]),
    ("double en slot+day", "earnings today in pre market and yesterday after hours", 2, ["bmo", "amc"]),
    ("double en reversed", "yesterday after hours and today pre market earnings", 2, ["amc", "bmo"]),
    ("double days only", "dame los earnings de hoy y de ayer", 2, [None, None]),
    ("triple days", "earnings de hoy, ayer y el lunes", 3, [None, None, None]),
    ("triple mixed", "pre market de hoy, after hours de ayer y todo lo del lunes", 3, ["bmo", "amc", None]),
    ("explicit ISO dates", "earnings del 2026-07-28 y del 2026-07-27", 2, [None, None]),
    ("single slot repeated", "top stocks with earnings after hours ordered by after hours change", 0, []),
    ("single plain", "quien presenta resultados hoy", 0, []),
]

for name, text, want_n, want_slots in CASES:
    got = _extract_earnings_windows(text)
    check(f"{name}: {want_n} window(s)", len(got) == want_n, f"got {got}")
    if want_n:
        check(f"{name}: slots {want_slots}", [s for _, s in got] == want_slots, f"got {got}")

check("windows are unique", len(set(_extract_earnings_windows(
    "pre market de hoy, after hours de ayer y todo lo del lunes"))) == 3)


# ── 4. Calendar cleaning ────────────────────────────────────────────
# El fan-out sólo sirve si un día compactado cabe: en crudo son ~30 KB y tres
# días se comen el presupuesto entero del sintetizador.
print("\nCalendar cleaning")

from agents.news_events import _clean_calendar  # noqa: E402

raw_day = {"date": "2026-07-27", "reports": [
    {"symbol": f"S{i}", "company_name": f"Company {i}", "report_time": "09:00",
     "eps_actual": 1.0 if i % 2 else None, "eps_estimate": 0.9,
     "market_cap": 1e9 * (100 - i), "status": "reported" if i % 2 else "scheduled",
     "summary": "x " * 400, "event_id": i, "grounding_sources": ["a"] * 20}
    for i in range(80)]}

clean = _clean_calendar(raw_day, cap=10)
check("calendar splits reported vs scheduled",
      clean["reported_count"] + clean["scheduled_count"] == 80)
check("calendar caps each list", len(clean["reported"]) <= 10 and len(clean["scheduled"]) <= 10)
check("calendar says it truncated", "truncated" in clean)
check("calendar drops dead weight",
      all("event_id" not in r and "grounding_sources" not in r
          for r in clean["reported"]))
check("calendar keeps a trimmed summary",
      all(len(r.get("summary", "")) <= 320 for r in clean["reported"]))
check("calendar sorts by market cap",
      [r["symbol"] for r in clean["reported"]][:2] == ["S1", "S3"],
      str([r["symbol"] for r in clean["reported"]][:3]))

# Lo que importa no es que el payload sea pequeño —la ventana del modelo es
# enorme— sino que limpiar reduzca de verdad y sin romper nada. Afirmar un
# tamaño máximo llevó a borrar datos buenos para cumplir un número inventado.
_raw_size = _safe_json_size(raw_day)
_clean_size = _safe_json_size(clean)
check("cleaning actually reduces the payload", _clean_size < _raw_size,
      f"{_clean_size} vs {_raw_size}")
check("three cleaned days stay well inside the safety valve",
      _clean_size * 3 < 200_000, f"{_clean_size} chars each")
check("non-calendar payloads pass through", _clean_calendar({"x": 1}) == {"x": 1})

# Invariante: una fila debe poder identificar su propio día. Cuando se piden
# varios días y el modelo los aplana u ordena por movimiento, una fila anónima
# termina atribuida al día equivocado (GRMN, que reportó el 29, apareció bajo
# un encabezado del 28).
_two_days = {"date": "2026-07-27", "reports": [
    {"symbol": "AAA", "eps_actual": 1.0, "market_cap": 2e9},
    {"symbol": "BBB", "market_cap": 1e9},
]}
_cleaned = _clean_calendar(_two_days, cap=5)
# Invariante de identidad: una fila debe bastarse a sí misma. Cada vez que un
# dato ha viajado sin su identidad, el modelo lo ha atribuido mal — el número
# sin su punto de referencia (GLW, -12% de hueco leído como caída desde la
# apertura) y la fila sin su día (GRMN, del 29, listada bajo el 28).
_ROW_IDENTITY = ("symbol", "report_date")

check("calendar rows carry their own date",
      all(r.get("report_date") == "2026-07-27"
          for r in _cleaned["reported"] + _cleaned["scheduled"]),
      str(_cleaned["reported"][:1]))


# ── 4b. Code validation before execution ────────────────────────────
# Ejecutar primero y preguntar después cuesta una ejecución y un turno. Los
# dos fallos que se vieron en producción se detectan sin ejecutar nada.
print("\nCode validation")

from agents.code_exec import _validate_code  # noqa: E402

_TRUNCATED = "```python\nimport pandas as pd\ndf = pd.DataFrame()\nsave_"
check("catches the unclosed markdown fence", (_validate_code(_TRUNCATED) or "").startswith("SyntaxError"),
      str(_validate_code(_TRUNCATED))[:80])

_FABRICATED = (
    "rows = [\n"
    "    {'ticker': 'MSFT', 'eps_actual': 2.95, 'eps_estimate': 2.80},\n"
    "    {'ticker': 'GOOGL', 'eps_actual': 1.60, 'eps_estimate': 1.75},\n"
    "]\nsave_output(rows)\n"
)
check("catches hand-written market rows", "escritos a mano" in (_validate_code(_FABRICATED) or ""),
      str(_validate_code(_FABRICATED))[:80])

_LEGIT = (
    "df = historical_query('AAPL', start='2026-07-01', end='2026-07-28')\n"
    "THRESHOLDS = {'min_volume': 1000000, 'max_pe': 30}\n"
    "save_output({'rows': df.to_dict('records'), 'limits': THRESHOLDS})\n"
)
check("lets legitimate code through", _validate_code(_LEGIT) is None,
      str(_validate_code(_LEGIT))[:80])

check("rejects empty output", _validate_code("   ") is not None)


_ident_rows = _clean_calendar(_two_days, cap=5)["reported"]
check("calendar rows are self-identifying",
      all(all(k in r for k in _ROW_IDENTITY) for r in _ident_rows),
      str(_ident_rows[:1]))


# ── 5. One vocabulary, every consumer ───────────────────────────────
# Session words used to be spelled out in four places with four different
# lists. "after hour" in the singular was understood in one and not the
# others, so the same question was answered in full or in half depending on
# which tool the selector picked.
print("\nShared session vocabulary")

from agents import _when  # noqa: E402
from agents.brief_router import _LIVE_DATA_RE  # noqa: E402
from agents.market_data import _CATEGORY_MAP, _detect_categories  # noqa: E402

check("news_events reads the shared module",
      _when.detect_slot is not None and _when.earnings_windows("x") == [])

PHRASINGS = [
    ("after hour", "amc"), ("after hours", "amc"), ("after-hours", "amc"),
    ("afterhours", "amc"), ("post market", "amc"), ("postmarket", "amc"),
    ("tras el cierre", "amc"),
    ("pre market", "bmo"), ("pre-market", "bmo"), ("premarket", "bmo"),
    ("antes de la apertura", "bmo"),
]

for phrase, slot in PHRASINGS:
    q = f"top movers {phrase} con mas de 1b"
    check(f"slot: '{phrase}' -> {slot}", _when.detect_slot(q) == slot,
          f"got {_when.detect_slot(q)}")

# The three consumers must react to the same words, each in its own way.
for phrase, slot in PHRASINGS:
    q = f"top movers {phrase}"
    if slot == "amc":
        check(f"market_data categories see '{phrase}'",
              "post_market" in _detect_categories(q), str(_detect_categories(q)))
    check(f"brief_router sees '{phrase}'", bool(_LIVE_DATA_RE.search(q)))

check("category map inherits every session phrase",
      all(p in _CATEGORY_MAP for p in _when.SESSION_PHRASES))
check("no consumer keeps a private session list",
      set(_when.AMC_PHRASES) | set(_when.BMO_PHRASES) == set(_when.SESSION_PHRASES))


# ── 6. Closure scoping ──────────────────────────────────────────────
# Un nombre del ámbito exterior que además se ASIGNA dentro de una función
# anidada pasa a ser local de esa función, y leerlo antes revienta con
# UnboundLocalError. Pasó de verdad: la rama de earnings dejó de ejecutarse
# una tarde entera y la respuesta caía a una ruta sin estimados, sin un solo
# error visible.
print("\nClosure scoping")

import ast  # noqa: E402
import inspect  # noqa: E402

from agents import news_events as _ne  # noqa: E402


def _unbound_locals(func) -> list[str]:
    """Nombres del ámbito exterior que una función anidada LEE antes de asignar.

    Asignar un nombre dentro de una anidada es normal (es una local nueva). El
    fallo es leerlo primero esperando el valor de fuera y asignarlo después:
    ahí Python ya lo considera local y la lectura revienta.
    """
    tree = ast.parse(inspect.getsource(func).lstrip())
    outer = {t.id for n in ast.walk(tree) if isinstance(n, ast.Assign)
             for t in n.targets if isinstance(t, ast.Name)}
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        if node is tree.body[0]:
            continue
        declared = {nm for n in ast.walk(node)
                    if isinstance(n, (ast.Global, ast.Nonlocal)) for nm in n.names}
        params = {a.arg for a in node.args.args + node.args.kwonlyargs}
        first_store: dict[str, int] = {}
        first_load: dict[str, int] = {}
        for n in ast.walk(node):
            if not isinstance(n, ast.Name):
                continue
            book = first_store if isinstance(n.ctx, ast.Store) else first_load
            if isinstance(n.ctx, (ast.Store, ast.Load)):
                book.setdefault(n.id, n.lineno)
        for name, store_line in first_store.items():
            if name in declared or name in params or name not in outer:
                continue
            load_line = first_load.get(name)
            if load_line is not None and load_line < store_line:
                offenders.append(
                    f"{node.name}() reads outer '{name}' (line {load_line}) "
                    f"before assigning it (line {store_line})")
    return offenders


for _fn in (_ne._news_events_node_native, _ne.news_events_node):
    _off = _unbound_locals(_fn)
    check(f"{_fn.__name__}: no nested reassignment of outer names",
          not _off, "; ".join(_off))


# ── Verdict ─────────────────────────────────────────────────────────
print(f"\n── {checks - len(failures)}/{checks} pass ──")
if failures:
    print("failed: " + ", ".join(failures))
    sys.exit(1)
