#!/usr/bin/env python3
"""
Filter catalog parity check (v2) — verifies that EVERY zone that consumes
filter definitions is in sync with the single source of truth:

    shared/config/filter_catalog.json

Zones checked:
  1. Generated assets up to date (TS frontend, RETE mapping, v1 events json)
     → delegates to `scripts/gen_filter_assets.py --check`
  2. websocket_server eventPassesSubscription covers every events-scope filter
  3. websocket_server loads defs from the shared json (no inline duplicates)
  4. RETE user_rules imports the generated mapping (no inline duplicates)
  5. Pydantic FilterParameters declares every catalog param key
  6. Frontend ConfigWindow / EventTableContent use the generated assets
  7. Frontend event filters store declares every events-scope param key

Exit 1 on any divergence. Run in CI and before deploys.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path("/opt/tradeul")
CATALOG_V2 = ROOT / "shared/config/filter_catalog.json"
BACKEND_WS = ROOT / "services/websocket_server/src/index.js"
RETE_USER_RULES = ROOT / "services/scanner/rete/user_rules.py"
PYDANTIC_MODELS = ROOT / "shared/models/scanner.py"
FE_CONFIG_WINDOW = ROOT / "frontend/components/config/ConfigWindow.tsx"
FE_EVENT_TABLE = ROOT / "frontend/components/events/EventTableContent.tsx"
FE_STORE = ROOT / "frontend/stores/useEventFiltersStore.ts"
GEN_SCRIPT = ROOT / "scripts/gen_filter_assets.py"


def fail(errors: list[str]) -> int:
    print("Filter catalog parity check FAILED")
    for e in errors:
        print(f"- {e}")
    return 1


def main() -> int:
    errors: list[str] = []
    cat = json.loads(CATALOG_V2.read_text())
    entries = cat["filters"]
    events_entries = [e for e in entries if "events" in e["scopes"]]
    scanner_entries = [e for e in entries if "scanner" in e["scopes"]]

    # ── 1) Generated assets up to date ───────────────────────────────────
    gen = subprocess.run(
        [sys.executable, str(GEN_SCRIPT), "--check"],
        capture_output=True, text=True,
    )
    if gen.returncode != 0:
        errors.append("Generated assets are STALE. Run: python3 scripts/gen_filter_assets.py")

    ws_src = BACKEND_WS.read_text()

    # ── 2) eventPassesSubscription covers every events-scope subKey ──────
    m = re.search(r"function eventPassesSubscription\(evt, sub\) \{(.*?)\n\}", ws_src, re.S)
    if not m:
        errors.append("eventPassesSubscription not found in websocket_server")
        body = ""
    else:
        body = m.group(1)
    covered = set(re.findall(r"'([A-Za-z0-9_]+(?:Min|Max))'", body))
    # Index filters are checked via INDEX_FILTER_DEFS template keys
    has_index_loop = "INDEX_FILTER_DEFS" in body
    idx_prefixes = {"spy": "spyChg", "qqq": "qqqChg", "dia": "diaChg"}
    idx_windows = {"chg_5min": "5min", "chg_10min": "10min", "chg_15min": "15min",
                   "chg_30min": "30min", "chg_today": "Today"}
    if has_index_loop:
        for sym in idx_prefixes.values():
            for w in idx_windows.values():
                covered.add(f"{sym}{w}Min")
                covered.add(f"{sym}{w}Max")
    missing_checks = []
    for e in events_entries:
        for side in ("subKeyMin", "subKeyMax"):
            if e[side] not in covered:
                missing_checks.append(e[side])
    if missing_checks:
        errors.append(
            f"websocket eventPassesSubscription missing checks ({len(missing_checks)}): "
            + ", ".join(missing_checks[:30])
        )

    # ── 3) websocket loads defs from json (no inline literal lists) ──────
    if "event_filter_catalog.json" not in ws_src:
        errors.append("websocket_server no longer loads shared event_filter_catalog.json")
    if re.search(r"const NUMERIC_FILTER_DEFS = \[\s*\n\s*\[", ws_src):
        errors.append("websocket_server has an inline NUMERIC_FILTER_DEFS literal (must load from catalog)")

    # ── 4) RETE mapping is the generated one ─────────────────────────────
    rete_src = RETE_USER_RULES.read_text()
    if "from .filter_mapping_generated import FILTER_FIELD_MAPPING" not in rete_src:
        errors.append("rete/user_rules.py does not import the generated FILTER_FIELD_MAPPING")
    if re.search(r"^FILTER_FIELD_MAPPING = \[", rete_src, re.M):
        errors.append("rete/user_rules.py has an inline FILTER_FIELD_MAPPING literal")

    # ── 5) Pydantic FilterParameters declares every param ────────────────
    pyd_src = PYDANTIC_MODELS.read_text()
    m = re.search(r"class FilterParameters\(BaseModel\):(.*?)\nclass ", pyd_src, re.S)
    if not m:
        errors.append("FilterParameters class not found in shared/models/scanner.py")
    else:
        declared = set(re.findall(r"^\s+((?:min|max)_[a-z0-9_]+):", m.group(1), re.M))
        missing_pyd = sorted(
            p for e in entries
            for p in (e["paramMin"], e.get("paramMax"))
            if p and p not in declared
        )
        if missing_pyd:
            errors.append(
                f"Pydantic FilterParameters missing params ({len(missing_pyd)}): "
                + ", ".join(missing_pyd[:30])
            )

    # ── 6) Frontend uses generated assets ────────────────────────────────
    cw_src = FE_CONFIG_WINDOW.read_text()
    if "filter-catalog.generated" not in cw_src or "FILTER_GROUPS" not in cw_src:
        errors.append("ConfigWindow.tsx does not use generated FILTER_GROUPS")
    if re.search(r"const FG = \[", cw_src):
        errors.append("ConfigWindow.tsx has an inline FG literal (must use generated catalog)")
    et_src = FE_EVENT_TABLE.read_text()
    if "EVENT_WIRE_PAIRS" not in et_src:
        errors.append("EventTableContent.tsx does not use generated EVENT_WIRE_PAIRS")

    # ── 7) Store declares every events-scope param key ───────────────────
    store_src = FE_STORE.read_text()
    store_keys = set(re.findall(r"\b((?:min|max)_[a-zA-Z0-9_]+)\b", store_src))
    missing_store = sorted(
        p for e in events_entries
        for p in (e["paramMin"], e.get("paramMax"))
        if p and p not in store_keys
    )
    if missing_store:
        errors.append(
            f"useEventFiltersStore missing param keys ({len(missing_store)}): "
            + ", ".join(missing_store[:30])
        )

    if errors:
        return fail(errors)

    print("Filter catalog parity check OK")
    print(f"- catalog filters: {len(entries)} (events={len(events_entries)}, scanner={len(scanner_entries)})")
    print(f"- websocket checks covered: {len(covered)} subKeys")
    print("- generated assets in sync (TS, RETE mapping, v1 events json)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
