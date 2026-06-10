#!/usr/bin/env python3
"""
Generates derived filter assets from the unified catalog
(shared/config/filter_catalog.json — THE single source of truth).

Outputs:
  1. frontend/lib/filter-catalog.generated.ts
       - FILTER_GROUPS   → drives ConfigWindow "Filters" tab UI
       - FILTER_LABELS   → min_/max_ key → display label map
       - EVENT_WIRE_PAIRS→ drives EventTableContent subscribe/update payloads
       - DILUTION_FILTERS→ dilution select-UI definitions
  2. services/scanner/rete/filter_mapping_generated.py
       - FILTER_FIELD_MAPPING → drives RETE user rule conversion
  3. shared/config/event_filter_catalog.json (v1, events scope — consumed by
     websocket_server at runtime and by parity tooling)

Run after ANY edit to shared/config/filter_catalog.json:
  python3 scripts/gen_filter_assets.py

Verify generated assets are up to date (CI / parity):
  python3 scripts/gen_filter_assets.py --check
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
V2_PATH = ROOT / "shared/config/filter_catalog.json"
TS_OUT = ROOT / "frontend/lib/filter-catalog.generated.ts"
RETE_OUT = ROOT / "services/scanner/rete/filter_mapping_generated.py"
V1_OUT = ROOT / "shared/config/event_filter_catalog.json"

HEADER_TS = """\
/**
 * AUTO-GENERATED — DO NOT EDIT BY HAND.
 *
 * Source of truth: shared/config/filter_catalog.json
 * Regenerate with:  python3 scripts/gen_filter_assets.py
 */

/* eslint-disable */

export interface FilterDef {
  label: string;
  minK: string;
  maxK: string;
  suf: string;
  units?: readonly string[];
  defU?: string;
  phMin?: string;
  phMax?: string;
}

export interface FilterGroup {
  id: string;
  group: string;
  filters: FilterDef[];
}
"""

HEADER_PY = '''\
"""
AUTO-GENERATED — DO NOT EDIT BY HAND.

Source of truth: shared/config/filter_catalog.json
Regenerate with:  python3 scripts/gen_filter_assets.py

FILTER_FIELD_MAPPING: (min_param, max_param, ticker_field) tuples consumed by
rete/user_rules.py. MARKET_CONTEXT_FIELDS: fields resolved from the global
market context (SPY/QQQ/DIA) instead of the ticker being evaluated.
"""

'''


def slugify(group: str) -> str:
    return (
        group.lower()
        .replace("'", "")
        .replace("/", " ")
        .replace("&", " ")
        .replace("-", " ")
        .replace(".", "")
        .split()
        and "_".join(
            group.lower().replace("'", "").replace("/", " ").replace("&", " ").replace("-", " ").replace(".", "").split()
        )
        or "misc"
    )


def write_or_check(path: Path, content: str, check: bool, stale: list[str]) -> None:
    if check:
        current = path.read_text() if path.exists() else None
        if current != content:
            stale.append(str(path))
    else:
        path.write_text(content)


def main() -> None:
    check = "--check" in sys.argv
    stale: list[str] = []
    cat = json.loads(V2_PATH.read_text())
    entries = cat["filters"]

    # ── 1) TypeScript asset ──────────────────────────────────────────────
    # FILTER_GROUPS: labeled entries (except dilution select-UI), FG order
    ui_entries = [
        e for e in entries
        if e.get("label") and e.get("group") and e.get("ui") != "select3"
    ]
    ui_entries.sort(key=lambda e: e.get("uiOrder", 10**9))

    groups: list[dict] = []
    group_idx: dict[str, dict] = {}
    for e in ui_entries:
        g = e["group"]
        if g not in group_idx:
            group_idx[g] = {"id": slugify(g), "group": g, "filters": []}
            groups.append(group_idx[g])
        f: dict = {
            "label": e["label"],
            "minK": e["paramMin"],
            "maxK": e["paramMax"],
            "suf": e.get("suf", ""),
        }
        for opt in ("units", "defU", "phMin", "phMax"):
            if e.get(opt) is not None:
                f[opt] = e[opt]
        group_idx[g]["filters"].append(f)

    # FILTER_LABELS: param key → {label, suf} for every labeled filter
    labels: dict[str, dict] = {}
    for e in entries:
        if not e.get("label"):
            continue
        labels[e["paramMin"]] = {"label": f"{e['label']} >", "suf": e.get("suf", "")}
        if e.get("paramMax"):
            labels[e["paramMax"]] = {"label": f"{e['label']} <", "suf": e.get("suf", "")}

    # EVENT_WIRE_PAIRS: events-scope filters → wire keys for ws subscription
    wire_pairs = [
        [e["paramMin"], e["paramMax"], e["dataKeyMin"], e["dataKeyMax"]]
        for e in entries
        if "events" in e["scopes"] and e.get("paramMax")
    ]

    dilution = [
        {"label": e["label"], "minK": e["paramMin"], "maxK": e["paramMax"]}
        for e in entries
        if e.get("ui") == "select3"
    ]

    ts = HEADER_TS
    ts += "\nexport const FILTER_GROUPS: readonly FilterGroup[] = "
    ts += json.dumps(groups, indent=2, ensure_ascii=False)
    ts += " as const;\n"
    ts += "\nexport const FILTER_LABELS: Record<string, { label: string; suf: string }> = "
    ts += json.dumps(labels, indent=2, ensure_ascii=False)
    ts += ";\n"
    ts += "\n/** [paramMin, paramMax, wireMin, wireMax] for every events-scope filter */\n"
    ts += "export const EVENT_WIRE_PAIRS: readonly (readonly [string, string, string, string])[] = "
    ts += json.dumps(wire_pairs, ensure_ascii=False, indent=0).replace("\n", "\n")
    ts += " as const;\n"
    ts += "\nexport const DILUTION_FILTERS: readonly { label: string; minK: string; maxK: string }[] = "
    ts += json.dumps(dilution, indent=2, ensure_ascii=False)
    ts += " as const;\n"
    write_or_check(TS_OUT, ts, check, stale)
    print(f"{'Checked' if check else 'Wrote'} {TS_OUT} ({len(groups)} groups, {len(wire_pairs)} wire pairs)")

    # ── 2) RETE mapping (scanner scope) ──────────────────────────────────
    scanner_entries = [e for e in entries if "scanner" in e["scopes"]]
    py = HEADER_PY
    py += "FILTER_FIELD_MAPPING = [\n"
    for e in scanner_entries:
        field = e.get("field") or e["base"]
        max_repr = f'"{e["paramMax"]}"' if e.get("paramMax") else "None"
        py += f'    ("{e["paramMin"]}", {max_repr}, "{field}"),\n'
    py += "]\n\n"
    market_fields = sorted(
        (e.get("field") or e["base"])
        for e in scanner_entries
        if e.get("source") == "market"
    )
    py += "MARKET_CONTEXT_FIELDS = {\n"
    for f in market_fields:
        py += f'    "{f}",\n'
    py += "}\n"
    write_or_check(RETE_OUT, py, check, stale)
    print(f"{'Checked' if check else 'Wrote'} {RETE_OUT} ({len(scanner_entries)} mappings, {len(market_fields)} market fields)")

    # ── 3) v1 events catalog (runtime input for websocket_server) ────────
    v1_numeric = []
    for e in entries:
        if "events" not in e["scopes"]:
            continue
        v1_numeric.append({"subKey": e["subKeyMin"], "dataKey": e["dataKeyMin"], "parser": e["parser"]})
        v1_numeric.append({"subKey": e["subKeyMax"], "dataKey": e["dataKeyMax"], "parser": e["parser"]})
    v1 = {"version": 1, "numeric": v1_numeric, "string": cat["string"], "aliases": cat["aliases"]}
    write_or_check(V1_OUT, json.dumps(v1, indent=2, ensure_ascii=False) + "\n", check, stale)
    print(f"{'Checked' if check else 'Wrote'} {V1_OUT} ({len(v1_numeric)} numeric rows)")

    if check and stale:
        print("\nSTALE generated assets (run: python3 scripts/gen_filter_assets.py):")
        for s in stale:
            print(f"  - {s}")
        sys.exit(1)


if __name__ == "__main__":
    main()
