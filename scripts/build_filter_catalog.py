#!/usr/bin/env python3
"""
[BOOTSTRAP — one-time migration script, already executed]

Built the unified filter catalog (v2) by merging the previously-dispersed
zones. It parsed the old inline FG array of ConfigWindow.tsx and the old
inline FILTER_FIELD_MAPPING of rete/user_rules.py, which NO LONGER EXIST
(they are now generated from the catalog). Re-running this script will fail;
it is kept for historical reference only.

The source of truth is now shared/config/filter_catalog.json — edit it by
hand and run scripts/gen_filter_assets.py.

Merges metadata from the previously-dispersed zones:
  - shared/config/event_filter_catalog.json (v1: wire keys + parser, events path)
  - frontend/components/config/ConfigWindow.tsx FG array (labels, groups, units)
  - services/scanner/rete/user_rules.py FILTER_FIELD_MAPPING (ticker fields)

And appends NEW filters that previously did not exist everywhere:
  - Dilution Risk scores (existed only in scanner path; now also events)
  - Index change filters SPY/QQQ/DIA (Trade Ideas Spy5..DiaD parity) — global
    market-context filters.

Output: shared/config/filter_catalog.json  (v2 schema, one entry per filter)

Schema per numeric entry:
  base        canonical snake_case name (e.g. "price", "spy_chg_5min")
  field       ticker/enriched field the value comes from (None => same as base)
  source      "row" (per-symbol value) | "market" (global SPY/QQQ/DIA context)
  parser      "pf" | "pi"
  label       UI label (None => not exposed in filter UI)
  group       UI group (None => not exposed)
  suf/units/defU/phMin/phMax   UI hints (optional)
  ui          optional UI hint ("select3" for dilution 1-3 selects)
  scopes      ["events", "scanner"] — which filtering paths support it
  paramMin/paramMax   FE/pydantic/RETE parameter names (min_x / max_x)
  dataKeyMin/dataKeyMax  wire keys for event subscriptions (x_min / x_max)
  subKeyMin/subKeyMax    internal camelCase sub keys (events backend)

The v1 file (event_filter_catalog.json) is REGENERATED from this catalog so
existing tooling keeps working (events scope only, same shape as before).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
V1_PATH = ROOT / "shared/config/event_filter_catalog.json"
V2_PATH = ROOT / "shared/config/filter_catalog.json"
CONFIG_WINDOW = ROOT / "frontend/components/config/ConfigWindow.tsx"
RETE_RULES = ROOT / "services/scanner/rete/user_rules.py"


# ---------------------------------------------------------------------------
# Parsers for existing zones
# ---------------------------------------------------------------------------

def load_v1() -> tuple[dict, dict, dict]:
    """Returns ({base: row_meta}, aliases, string_rows)."""
    cat = json.loads(V1_PATH.read_text())
    entries: dict[str, dict] = {}
    for row in cat["numeric"]:
        dk = row["dataKey"]
        if dk.endswith("_min"):
            base, side = dk[:-4], "min"
        elif dk.endswith("_max"):
            base, side = dk[:-4], "max"
        else:
            raise ValueError(f"Unexpected dataKey {dk}")
        e = entries.setdefault(base, {"parser": row["parser"]})
        e[f"subKey{side.capitalize()}"] = row["subKey"]
        e[f"dataKey{side.capitalize()}"] = dk
    return entries, dict(cat.get("aliases", {})), list(cat.get("string", []))


def parse_config_window_fg() -> dict[str, dict]:
    """Extract {param_base: ui_meta} from the FG array in ConfigWindow.tsx."""
    src = CONFIG_WINDOW.read_text()
    m = re.search(r"const FG = \[(.*?)\] as const;", src, re.S)
    if not m:
        raise RuntimeError("FG array not found in ConfigWindow.tsx")
    fg_src = m.group(1)

    ui: dict[str, dict] = {}
    group = None
    order = 0
    for line in fg_src.splitlines():
        gm = re.search(r"group: ['\"](.+?)['\"]", line)
        if gm:
            group = gm.group(1).replace("\\'", "'")
        fm = re.search(
            r"\{ label: ['\"](?P<label>.+?)['\"], minK: '(?P<minK>[a-z0-9_]+)', maxK: '(?P<maxK>[a-z0-9_]+)', suf: '(?P<suf>[^']*)'"
            r"(?:, units: \[(?P<units>[^\]]*)\], defU: '(?P<defU>[^']*)')?"
            r"(?:, phMin: '(?P<phMin>[^']*)', phMax: '(?P<phMax>[^']*)')?",
            line,
        )
        if not fm:
            continue
        d = fm.groupdict()
        base = d["minK"][4:]  # strip min_
        order += 1
        meta = {
            "label": d["label"].replace("\\'", "'"),
            "group": group,
            "suf": d["suf"],
            "paramMin": d["minK"],
            "paramMax": d["maxK"],
            "uiOrder": order,
        }
        if d["units"] is not None:
            meta["units"] = [u.strip().strip("'\"") for u in d["units"].split(",")]
            meta["defU"] = d["defU"]
        if d["phMin"] is not None:
            meta["phMin"] = d["phMin"]
            meta["phMax"] = d["phMax"]
        ui[base] = meta
    return ui


def parse_rete_mapping() -> dict[str, dict]:
    """Extract {param_base: {field}} from FILTER_FIELD_MAPPING tuples."""
    src = RETE_RULES.read_text()
    m = re.search(r"FILTER_FIELD_MAPPING = \[(.*?)\n\]", src, re.S)
    if not m:
        raise RuntimeError("FILTER_FIELD_MAPPING not found")
    result: dict[str, dict] = {}
    for mm in re.finditer(
        r'\(\s*"(min_[a-z0-9_]+)"\s*,\s*(?:"(max_[a-z0-9_]+)"|None)\s*,\s*"([a-z0-9_]+)"\s*\)',
        m.group(1),
    ):
        min_p, max_p, field = mm.group(1), mm.group(2), mm.group(3)
        base = min_p[4:]
        result[base] = {"field": field, "paramMin": min_p, "paramMax": max_p}
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def camel(s: str) -> str:
    parts = s.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def mk_entry(base: str, **kw) -> dict:
    e = {
        "base": base,
        "field": kw.get("field"),
        "source": kw.get("source", "row"),
        "parser": kw.get("parser", "pf"),
        "label": kw.get("label"),
        "group": kw.get("group"),
        "suf": kw.get("suf", ""),
        "scopes": kw.get("scopes", ["events", "scanner"]),
        "paramMin": kw.get("paramMin", f"min_{base}"),
        "paramMax": kw.get("paramMax", f"max_{base}"),
        "dataKeyMin": kw.get("dataKeyMin", f"{base}_min"),
        "dataKeyMax": kw.get("dataKeyMax", f"{base}_max"),
        "subKeyMin": kw.get("subKeyMin", f"{camel(base)}Min"),
        "subKeyMax": kw.get("subKeyMax", f"{camel(base)}Max"),
    }
    for opt in ("units", "defU", "phMin", "phMax", "ui", "uiOrder"):
        if kw.get(opt) is not None:
            e[opt] = kw[opt]
    return e


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def main() -> None:
    v1_entries, aliases, string_rows = load_v1()
    fg = parse_config_window_fg()
    rete = parse_rete_mapping()

    # Reverse aliases: dataKey base -> param base (change_min -> min_change_percent)
    # v1 "change" base maps to FE param min_change_percent.
    param_overrides = {}
    for dk, param in aliases.items():
        if dk.endswith("_min"):
            param_overrides[dk[:-4]] = ("paramMin", param)
        elif dk.endswith("_max"):
            param_overrides.setdefault(dk[:-4] + "__max", ("paramMax", param))

    entries: list[dict] = []
    seen: set[str] = set()

    # --- 1) Everything in the v1 events catalog -----------------------------
    for base, meta in v1_entries.items():
        # FE param base may differ from wire base (aliases)
        param_base = base
        if base == "change":
            param_base = "change_percent"
        ui_meta = fg.get(param_base, {})
        rete_meta = rete.get(param_base, {})
        scopes = ["events"] + (["scanner"] if param_base in rete else [])
        entries.append(mk_entry(
            base,
            field=rete_meta.get("field") or None,
            parser=meta["parser"],
            label=ui_meta.get("label"),
            group=ui_meta.get("group"),
            suf=ui_meta.get("suf", ""),
            units=ui_meta.get("units"),
            defU=ui_meta.get("defU"),
            phMin=ui_meta.get("phMin"),
            phMax=ui_meta.get("phMax"),
            uiOrder=ui_meta.get("uiOrder"),
            scopes=scopes,
            paramMin=f"min_{param_base}",
            paramMax=f"max_{param_base}",
            dataKeyMin=meta["dataKeyMin"],
            dataKeyMax=meta["dataKeyMax"],
            subKeyMin=meta["subKeyMin"],
            subKeyMax=meta["subKeyMax"],
        ))
        seen.add(param_base)

    # --- 2) Scanner-only filters (in RETE but not in events catalog) --------
    for param_base, rete_meta in rete.items():
        if param_base in seen:
            continue
        ui_meta = fg.get(param_base, {})
        entries.append(mk_entry(
            param_base,
            field=rete_meta["field"] if rete_meta["field"] != param_base else None,
            label=ui_meta.get("label"),
            group=ui_meta.get("group"),
            suf=ui_meta.get("suf", ""),
            units=ui_meta.get("units"),
            defU=ui_meta.get("defU"),
            phMin=ui_meta.get("phMin"),
            phMax=ui_meta.get("phMax"),
            uiOrder=ui_meta.get("uiOrder"),
            scopes=["scanner"],
            paramMin=rete_meta["paramMin"],
            # None si el alias RETE solo tiene lado min (ej. min_volume_today)
            paramMax=rete_meta["paramMax"],
        ))
        seen.add(param_base)

    # --- 3) Dilution Risk: was scanner-only; now also in events scope -------
    dilution_bases = [
        ("dilution_overall_risk_score", "Overall Risk"),
        ("dilution_offering_ability_score", "Offering Ability"),
        ("dilution_overhead_supply_score", "Overhead Supply"),
        ("dilution_historical_score", "Historical"),
        ("dilution_cash_need_score", "Cash Need"),
    ]
    for base, label in dilution_bases:
        # Already present from RETE pass (scanner scope) — upgrade in place
        for e in entries:
            if e["base"] == base:
                e["scopes"] = ["events", "scanner"]
                e["label"] = label
                e["group"] = "Dilution Risk"
                e["parser"] = "pi"
                e["ui"] = "select3"
                break

    # --- 4) NEW: Index change filters (SPY/QQQ/DIA) — market context --------
    index_defs = [
        ("spy", "S&P", "SPY"),
        ("qqq", "NASDAQ", "QQQ"),
        ("dia", "Dow", "DIA"),
    ]
    window_defs = [
        ("chg_5min", "Change 5 Minute"),
        ("chg_10min", "Change 10 Minute"),
        ("chg_15min", "Change 15 Minute"),
        ("chg_30min", "Change 30 Minute"),
        ("chg_today", "Change Today"),
    ]
    next_order = max((e.get("uiOrder", 0) for e in entries), default=0)
    for sym_key, sym_label, _sym in index_defs:
        for w_key, w_label in window_defs:
            base = f"{sym_key}_{w_key}"
            next_order += 1
            entries.append(mk_entry(
                base,
                source="market",
                label=f"{sym_label} {w_label}",
                group="Index Change",
                suf="%",
                phMin="-1",
                phMax="1",
                uiOrder=next_order,
                scopes=["events", "scanner"],
            ))

    catalog = {
        "version": 2,
        "filters": entries,
        "string": string_rows,
        "aliases": aliases,
    }
    V2_PATH.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {V2_PATH} with {len(entries)} numeric filters")

    # --- Regenerate v1 (events scope) so existing tooling keeps working -----
    v1_numeric = []
    for e in entries:
        if "events" not in e["scopes"]:
            continue
        v1_numeric.append({"subKey": e["subKeyMin"], "dataKey": e["dataKeyMin"], "parser": e["parser"]})
        v1_numeric.append({"subKey": e["subKeyMax"], "dataKey": e["dataKeyMax"], "parser": e["parser"]})
    v1 = {"version": 1, "numeric": v1_numeric, "string": string_rows, "aliases": aliases}
    V1_PATH.write_text(json.dumps(v1, indent=2, ensure_ascii=False) + "\n")
    print(f"Regenerated {V1_PATH} with {len(v1_numeric)} numeric rows (events scope)")

    # Stats
    n_events = sum(1 for e in entries if "events" in e["scopes"])
    n_scanner = sum(1 for e in entries if "scanner" in e["scopes"])
    n_labeled = sum(1 for e in entries if e["label"])
    print(f"scopes: events={n_events} scanner={n_scanner} | labeled={n_labeled}/{len(entries)}")


if __name__ == "__main__":
    main()
