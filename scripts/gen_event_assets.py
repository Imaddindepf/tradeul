#!/usr/bin/env python3
"""
Generates derived EVENT catalog assets from the alert_engine registry
(services/alert_engine/registry/alert_catalog.py — THE single source of
truth: one AlertDefinition per AlertType the engine can emit).

Outputs:
  1. shared/config/event_catalog.json
       canonical, language-complete JSON — consumed by tooling and by the
       backtester boundary validation (Fase 1 del diseño)
  2. frontend/lib/alert-catalog.generated.ts
       ALERT_CATEGORIES / ALERT_CATALOG / derived maps — drives the BUILD
       strategy builder, EventFeed, EventTable and the backtest window via
       the facade frontend/lib/alert-catalog.ts

Run after ANY edit to registry/alert_catalog.py or models/alert_types.py:
  python3 scripts/gen_event_assets.py

Verify generated assets are up to date (CI / parity):
  python3 scripts/gen_event_assets.py --check

The generator FAILS (exit 2) if any AlertType lacks a registry entry, so a
new event type that would silently miss the catalog breaks the build instead.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "services/alert_engine"))

from models.alert_types import AlertType  # noqa: E402
from registry.alert_catalog import ALERT_CATALOG, CATEGORY_CATALOG  # noqa: E402

JSON_OUT = ROOT / "shared/config/event_catalog.json"
TS_OUT = ROOT / "frontend/lib/alert-catalog.generated.ts"

# The backend registry encodes direction as "+" / "-" / "" — map to the
# frontend vocabulary here.
DIRECTION_MAP = {"+": "bullish", "-": "bearish", "": "neutral"}

# Hand-crafted compact labels for table cells / badges (display sugar the
# backend registry does not carry). Fallback for new codes is the full name;
# add a row here when a nicer short form exists.
SHORT_LABELS: dict = {
    "BBD": "σ Break ↓",
    "BBU": "σ Break ↑",
    "BP": "Block",
    "C": "Consol",
    "CA20": "SMA20d ↑",
    "CA200": "SMA200 ↑",
    "CA50": "SMA50d ↑",
    "CAC": "↑ Close",
    "CACC": "↑ Close Conf",
    "CAO": "↑ Open",
    "CAOC": "↑ Open Conf",
    "CAVC": "VWAP ↑",
    "CB20": "SMA20d ↓",
    "CB200": "SMA200 ↓",
    "CB50": "SMA50d ↓",
    "CBC": "↓ Close",
    "CBCC": "↓ Close Conf",
    "CBO": "↓ Open",
    "CBOC": "↓ Open Conf",
    "CBVC": "VWAP ↓",
    "CDHR": "Day High ↑",
    "CDLS": "Day Low ↓",
    "CHBD": "Ch Break ↓",
    "CHBDC": "Ch Brk ↓ Conf",
    "CHBO": "Ch Break ↑",
    "CHBOC": "Ch Brk ↑ Conf",
    "CMD": "Check ↓",
    "CMU": "Check ↑",
    "FGDR": "False Gap↓",
    "FGUR": "False Gap↑",
    "GBBOT": "Broad Bot",
    "GBTOP": "Broad Top",
    "GDBOT": "Dbl Bot",
    "GDR": "Gap↓ Rev",
    "GDTOP": "Dbl Top",
    "GHAS": "H&S",
    "GHASI": "Inv H&S",
    "GRBOT": "Rect Bot",
    "GRTOP": "Rect Top",
    "GTBOT": "Tri Bot",
    "GTTOP": "Tri Top",
    "GUR": "Gap↑ Rev",
    "HALT": "HALT",
    "HPMV": "Pre Vol",
    "HPOST": "Post High",
    "HPRE": "Pre High",
    "HRV": "RVOL",
    "LAS": "Lg Ask",
    "LBS": "Lg Bid",
    "LPOST": "Post Low",
    "LPRE": "Pre Low",
    "LSP": "Lg Spread",
    "MC": "Mkt Cross",
    "MCD": "Mkt Cross ↓",
    "MCU": "Mkt Cross ↑",
    "MDAS10": "MACD Sig 10m↑",
    "MDAS15": "MACD Sig 15m↑",
    "MDAS30": "MACD Sig 30m↑",
    "MDAS5": "MACD Sig 5m↑",
    "MDAS60": "MACD Sig 60m↑",
    "MDAZ10": "MACD 0 10m↑",
    "MDAZ15": "MACD 0 15m↑",
    "MDAZ30": "MACD 0 30m↑",
    "MDAZ5": "MACD 0 5m↑",
    "MDAZ60": "MACD 0 60m↑",
    "MDBS10": "MACD Sig 10m↓",
    "MDBS15": "MACD Sig 15m↓",
    "MDBS30": "MACD Sig 30m↓",
    "MDBS5": "MACD Sig 5m↓",
    "MDBS60": "MACD Sig 60m↓",
    "MDBZ10": "MACD 0 10m↓",
    "MDBZ15": "MACD 0 15m↓",
    "MDBZ30": "MACD 0 30m↓",
    "MDBZ5": "MACD 0 5m↓",
    "MDBZ60": "MACD 0 60m↓",
    "ML": "Mkt Lock",
    "NHA": "High Ask",
    "NHAF": "HiAsk Filt",
    "NHB": "High Bid",
    "NHBF": "HiBid Filt",
    "NHP": "New High",
    "NHPF": "High Filt",
    "NLA": "Low Ask",
    "NLAF": "LoAsk Filt",
    "NLB": "Low Bid",
    "NLBF": "LoBid Filt",
    "NLP": "New Low",
    "NLPF": "Low Filt",
    "PDD": "% Down",
    "PFH25": "PB 25% H",
    "PFH25C": "PB 25% H/C",
    "PFH25O": "PB 25% H/O",
    "PFH75": "PB 75% H",
    "PFH75C": "PB 75% H/C",
    "PFH75O": "PB 75% H/O",
    "PFL25": "Bounce 25%",
    "PFL25C": "Bounce 25% C",
    "PFL25O": "Bounce 25% O",
    "PFL75": "Bounce 75%",
    "PFL75C": "Bounce 75% C",
    "PFL75O": "Bounce 75% O",
    "PUD": "% Up",
    "RD": "Run ↓ Sust",
    "RDC": "Run ↓ Conf",
    "RDI": "Run ↓ Int",
    "RDN": "Run ↓",
    "RESUME": "RESUME",
    "RU": "Run ↑ Sust",
    "RUC": "Run ↑ Conf",
    "RUI": "Run ↑ Int",
    "RUN": "Run ↑",
    "SC20_15": "Stoch 15m↑20",
    "SC20_5": "Stoch 5m↑20",
    "SC20_60": "Stoch 60m↑20",
    "SC80_15": "Stoch 15m↓80",
    "SC80_5": "Stoch 5m↓80",
    "SC80_60": "Stoch 60m↓80",
    "SV": "Strong Vol",
    "TRA": "Trd Above",
    "TRAS": "Trd Abv Spec",
    "TRB": "Trd Below",
    "TRBS": "Trd Blw Spec",
    "TSPD": "TS% Down",
    "TSPU": "TS% Up",
    "TSSD": "TSVol Down",
    "TSSU": "TSVol Up",
    "UNOP": "Unusual",
    "VDD": "VWAP Div ↓",
    "VDU": "VWAP Div ↑",
    "VS1": "Vol Spike"
}


def validate() -> None:
    errors = []
    covered = {d.alert_type for d in ALERT_CATALOG.values()}
    missing = sorted(t.value for t in AlertType if t not in covered)
    if missing:
        errors.append(f"AlertType sin entrada en el registry: {missing}")
    seen_types: dict = {}
    for d in ALERT_CATALOG.values():
        if d.alert_type in seen_types:
            errors.append(f"event_type duplicado: {d.alert_type.value} ({seen_types[d.alert_type]} y {d.code})")
        seen_types[d.alert_type] = d.code
        if d.direction not in DIRECTION_MAP:
            errors.append(f"{d.code}: direction invalida {d.direction!r}")
        if d.category not in CATEGORY_CATALOG:
            errors.append(f"{d.code}: categoria desconocida {d.category!r}")
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)


def category_rows() -> list:
    return [
        {
            "id": c.id,
            "name": c.name,
            "name_es": c.name_es,
            "icon": c.icon,
            "description": c.description,
            "description_es": c.description_es,
            "order": c.order,
        }
        for c in sorted(CATEGORY_CATALOG.values(), key=lambda c: c.order)
    ]


def event_rows() -> list:
    rows = []
    for d in ALERT_CATALOG.values():
        rows.append(
            {
                "code": d.code,
                "event_type": d.alert_type.value,
                "name": d.name,
                "name_es": d.name_es,
                "short_label": SHORT_LABELS.get(d.code, d.name),
                "category": d.category,
                "direction": DIRECTION_MAP[d.direction],
                "phase": d.phase,
                "active": d.active,
                "cooldown": d.cooldown,
                "description": d.description,
                "description_es": d.description_es,
                "flip_code": d.flip_code,
                "parent_code": d.parent_code,
                "keywords": list(d.keywords),
                "custom_setting": {
                    "type": d.custom_setting_type.value,
                    "label": d.custom_setting_label or "",
                    "label_es": d.custom_setting_label_es or "",
                    "hint": d.custom_setting_hint or "",
                    "unit": d.custom_setting_unit or "",
                    "default": d.custom_setting_default,
                },
                "quality_description": d.quality_description,
                "quality_description_es": d.quality_description_es,
                "requires": list(d.requires),
            }
        )
    return rows


def render_json() -> str:
    payload = {
        "version": 1,
        "source": "services/alert_engine/registry/alert_catalog.py",
        "generator": "scripts/gen_event_assets.py",
        "total_events": len(ALERT_CATALOG),
        "categories": category_rows(),
        "events": event_rows(),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def ts_str(v: str) -> str:
    return json.dumps(v, ensure_ascii=False)


def render_ts() -> str:
    out = []
    out.append("/**")
    out.append(" * AUTO-GENERATED — DO NOT EDIT BY HAND.")
    out.append(" *")
    out.append(" * Source of truth: services/alert_engine/registry/alert_catalog.py")
    out.append(" * Regenerate with:  python3 scripts/gen_event_assets.py")
    out.append(" */")
    out.append("")
    out.append("/* eslint-disable */")
    out.append("")
    out.append("export type AlertDirection = 'bullish' | 'bearish' | 'neutral';")
    out.append("")
    setting_types = sorted({d.custom_setting_type.value for d in ALERT_CATALOG.values()} | {"none"})
    out.append("export type CustomSettingType =")
    for i, s in enumerate(setting_types):
        sep = ";" if i == len(setting_types) - 1 else ""
        out.append(f"  | '{s}'{sep}")
    out.append("")
    out.append("""export interface CustomSettingMeta {
  type: CustomSettingType;
  label: string;
  labelEs: string;
  hint: string;
  unit: string;
  defaultValue: number | null;
}

export interface AlertCategory {
  id: string;
  name: string;
  nameEs: string;
  icon: string;
  order: number;
}

export interface AlertDefinition {
  code: string;
  eventType: string;
  name: string;
  nameEs: string;
  shortLabel: string;
  category: string;
  direction: AlertDirection;
  active: boolean;
  description: string;
  descriptionEs: string;
  flipCode?: string;
  keywords: string[];
  customSetting: CustomSettingMeta;
  qualityDesc?: string;
  qualityDescEs?: string;
}
""")
    out.append("export const ALERT_CATEGORIES: AlertCategory[] = [")
    for c in sorted(CATEGORY_CATALOG.values(), key=lambda c: c.order):
        out.append(
            f"  {{ id: {ts_str(c.id)}, name: {ts_str(c.name)}, nameEs: {ts_str(c.name_es)}, "
            f"icon: {ts_str(c.icon)}, order: {c.order} }},"
        )
    out.append("];")
    out.append("")
    out.append("export const ALERT_CATEGORIES_MAP: Record<string, AlertCategory> = Object.fromEntries(")
    out.append("  ALERT_CATEGORIES.map(c => [c.id, c])")
    out.append(");")
    out.append("")
    out.append("export const ALERT_CATALOG: AlertDefinition[] = [")
    for d in ALERT_CATALOG.values():
        cs_parts = [
            f"type: {ts_str(d.custom_setting_type.value)}",
            f"label: {ts_str(d.custom_setting_label or '')}",
            f"labelEs: {ts_str(d.custom_setting_label_es or '')}",
            f"hint: {ts_str(d.custom_setting_hint or '')}",
            f"unit: {ts_str(d.custom_setting_unit or '')}",
            f"defaultValue: {json.dumps(d.custom_setting_default)}",
        ]
        parts = [
            f"code: {ts_str(d.code)}",
            f"eventType: {ts_str(d.alert_type.value)}",
            f"name: {ts_str(d.name)}",
            f"nameEs: {ts_str(d.name_es)}",
            f"shortLabel: {ts_str(SHORT_LABELS.get(d.code, d.name))}",
            f"category: {ts_str(d.category)}",
            f"direction: {ts_str(DIRECTION_MAP[d.direction])}",
            f"active: {json.dumps(d.active)}",
            f"description: {ts_str(d.description)}",
            f"descriptionEs: {ts_str(d.description_es)}",
        ]
        if d.flip_code:
            parts.append(f"flipCode: {ts_str(d.flip_code)}")
        parts.append("keywords: [" + ", ".join(ts_str(k) for k in d.keywords) + "]")
        parts.append("customSetting: { " + ", ".join(cs_parts) + " }")
        if d.quality_description:
            parts.append(f"qualityDesc: {ts_str(d.quality_description)}")
        if d.quality_description_es:
            parts.append(f"qualityDescEs: {ts_str(d.quality_description_es)}")
        out.append("  { " + ", ".join(parts) + " },")
    out.append("];")
    out.append("")
    out.append("""export const ALERT_BY_EVENT_TYPE: Record<string, AlertDefinition> = Object.fromEntries(
  ALERT_CATALOG.map(a => [a.eventType, a])
);

export const ALERT_BY_CODE: Record<string, AlertDefinition> = Object.fromEntries(
  ALERT_CATALOG.map(a => [a.code, a])
);

/** All event type strings */
export const ALL_EVENT_TYPES: string[] = ALERT_CATALOG.map(a => a.eventType);

/** All active event type strings */
export const ACTIVE_EVENT_TYPES: string[] = ALERT_CATALOG.filter(a => a.active).map(a => a.eventType);
""")
    return "\n".join(out)


def main() -> None:
    validate()
    outputs = {JSON_OUT: render_json(), TS_OUT: render_ts()}
    if "--check" in sys.argv:
        stale = [str(p) for p, content in outputs.items()
                 if not p.exists() or p.read_text(encoding="utf-8") != content]
        if stale:
            print("STALE generated assets (run python3 scripts/gen_event_assets.py):", file=sys.stderr)
            for s in stale:
                print(f"  {s}", file=sys.stderr)
            sys.exit(1)
        print(f"OK — {len(ALERT_CATALOG)} eventos, artefactos al día")
        return
    for p, content in outputs.items():
        p.write_text(content, encoding="utf-8")
        print(f"wrote {p.relative_to(ROOT)} ({len(content):,} bytes)")


if __name__ == "__main__":
    main()
