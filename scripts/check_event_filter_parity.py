#!/usr/bin/env python3
"""
Parity check between EventTable frontend wire keys and websocket backend parser.

Fails (exit 1) when:
- Frontend sends keys that backend cannot parse
- Backend has filter keys that frontend never sends
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path("/opt/tradeul")
FRONTEND_EVENTS = ROOT / "frontend/components/events/EventTableContent.tsx"
FRONTEND_STORE = ROOT / "frontend/stores/useEventFiltersStore.ts"
BACKEND_WS = ROOT / "services/websocket_server/src/index.js"
CATALOG_FILE = ROOT / "shared/config/event_filter_catalog.json"


def extract_frontend_keys() -> tuple[set[str], set[str]]:
    events_src = FRONTEND_EVENTS.read_text(encoding="utf-8")
    store_src = FRONTEND_STORE.read_text(encoding="utf-8")

    subscribe_keys = set(re.findall(r"setF\('([^']+)'", events_src))
    subscribe_keys |= set(re.findall(r"setS\('([^']+)'", events_src))

    m = re.search(
        r"const uPairs: \[string, number \| undefined\]\[] = \[(.*?)\];",
        events_src,
        re.S,
    )
    update_keys = set(re.findall(r"\['([^']+)'\s*,", m.group(1))) if m else set()
    update_keys |= {"security_type", "sector", "industry"}

    # Frontend now sends all min_/max_ keys dynamically in update_event_filters.
    update_keys |= set(re.findall(r"\b(min_[a-zA-Z0-9_]+|max_[a-zA-Z0-9_]+)\b", store_src))

    return subscribe_keys, update_keys


def extract_backend_pairs() -> list[tuple[str, str, str | None]]:
    ws_src = BACKEND_WS.read_text(encoding="utf-8")

    num_block = re.search(
        r"const NUMERIC_FILTER_DEFS = \[(.*?)\];\n\n// String filter definitions",
        ws_src,
        re.S,
    )
    if not num_block:
        raise RuntimeError("Could not locate NUMERIC_FILTER_DEFS")
    numeric_pairs = [
        (a, b, c)
        for a, b, c in re.findall(r"\['([^']+)'\s*,\s*'([^']+)'\s*,\s*(pf|pi|pb)\]", num_block.group(1))
    ]

    str_block = re.search(r"const STRING_FILTER_DEFS = \[(.*?)\];", ws_src, re.S)
    if not str_block:
        raise RuntimeError("Could not locate STRING_FILTER_DEFS")
    string_pairs = [(a, b, None) for a, b in re.findall(r"\['([^']+)'\s*,\s*'([^']+)'\]", str_block.group(1))]

    return numeric_pairs + string_pairs


def load_catalog_pairs() -> tuple[list[tuple[str, str, str | None]], dict[str, str]]:
    catalog = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    numeric = [(row["subKey"], row["dataKey"], row["parser"]) for row in catalog["numeric"]]
    string = [(row["subKey"], row["dataKey"], None) for row in catalog["string"]]
    aliases = dict(catalog.get("aliases", {}))
    return numeric + string, aliases


def aliases_for_pair(sub_key: str, data_key: str, explicit_aliases: dict[str, str]) -> set[str]:
    aliases = {sub_key, data_key}
    if data_key.endswith("_min"):
        aliases.add(f"min_{data_key[:-4]}")
    if data_key.endswith("_max"):
        aliases.add(f"max_{data_key[:-4]}")
    explicit = explicit_aliases.get(data_key)
    if explicit:
        aliases.add(explicit)
    return aliases


def main() -> int:
    fe_subscribe, fe_update = extract_frontend_keys()
    backend_pairs = extract_backend_pairs()
    catalog_pairs, explicit_aliases = load_catalog_pairs()

    if backend_pairs != catalog_pairs:
        print("Event filter parity check FAILED")
        print("- Backend filter defs diverged from shared catalog.")
        print(f"  backend pairs: {len(backend_pairs)} | catalog pairs: {len(catalog_pairs)}")
        return 1

    all_pairs = catalog_pairs
    accepted_wire = set()
    for sub_key, data_key, _ in all_pairs:
        accepted_wire |= aliases_for_pair(sub_key, data_key, explicit_aliases)

    sub_unaccepted = sorted(k for k in fe_subscribe if k not in accepted_wire)
    upd_unaccepted = sorted(k for k in fe_update if k not in accepted_wire)

    missing_in_sub = []
    missing_in_upd = []
    for sub_key, data_key, _ in all_pairs:
        aliases = aliases_for_pair(sub_key, data_key, explicit_aliases)
        if not (aliases & fe_subscribe):
            missing_in_sub.append(data_key)
        if not (aliases & fe_update):
            missing_in_upd.append(data_key)

    if sub_unaccepted or upd_unaccepted or missing_in_sub or missing_in_upd:
        print("Event filter parity check FAILED")
        if sub_unaccepted:
            print(f"- Frontend subscribe keys not parsed by backend ({len(sub_unaccepted)}):")
            print("  " + ", ".join(sub_unaccepted[:50]))
        if upd_unaccepted:
            print(f"- Frontend update keys not parsed by backend ({len(upd_unaccepted)}):")
            print("  " + ", ".join(upd_unaccepted[:50]))
        if missing_in_sub:
            print(f"- Backend keys never sent on subscribe ({len(missing_in_sub)}):")
            print("  " + ", ".join(missing_in_sub[:50]))
        if missing_in_upd:
            print(f"- Backend keys never sent on update ({len(missing_in_upd)}):")
            print("  " + ", ".join(missing_in_upd[:50]))
        return 1

    print("Event filter parity check OK")
    print(f"- subscribe keys: {len(fe_subscribe)}")
    print(f"- update keys: {len(fe_update)}")
    print(f"- backend parser keys: {len(all_pairs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
