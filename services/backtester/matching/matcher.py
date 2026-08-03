"""Port 1:1 a Python de eventPassesSubscription (websocket_server).

Réplica exacta del pipeline de matching del vivo, con semántica JavaScript
donde importa (parseFloat/parseInt de prefijo, coerción Number() en las
comparaciones relacionales, NaN que no falla rangos normales pero sí
invertidos, falsy de '' en los strings). Las tablas de comprobaciones y las
listas de campos NO están escritas a mano: vienen de
matcher_defs_generated.py, generado desde el fuente JS por
scripts/gen_matcher_port_assets.py.

La paridad se verifica contra los fixtures congelados del código vivo:
services/backtester/parity/check_matcher_parity.py.
"""

from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from .matcher_defs_generated import (
    CHECKS,
    ENRICHED_FLOAT_FIELDS,
    ENRICHED_INT_FIELDS,
    ENRICHED_KEY_REMAP,
    ENRICHED_STRING_FIELDS,
    INDEX_FILTER_DEFS,
    INDEX_FILTER_WINDOWS,
    PAYLOAD_INT_FIELDS,
    PAYLOAD_STRING_FIELDS,
)

def _find_shared_config(filename: str) -> Path:
    """Localiza un json de shared/config en cualquier despliegue.

    Orden: env EVENT_CATALOGS_DIR → /app/shared/config (Docker, mismo
    convenio que el websocket_server) → raíz del repo (checkout).
    """
    import os

    here = Path(__file__).resolve()
    candidates = []
    if os.getenv("EVENT_CATALOGS_DIR"):
        candidates.append(Path(os.environ["EVENT_CATALOGS_DIR"]) / filename)
    candidates.append(here.parent.parent / "shared/config" / filename)   # /app en Docker
    if len(here.parents) >= 4:
        candidates.append(here.parents[3] / "shared/config" / filename)  # repo
    for c in candidates:
        if c.is_file():
            return c
    raise FileNotFoundError(f"{filename} no encontrado. Probado: {[str(c) for c in candidates]}")


_CATALOG_PATH = _find_shared_config("event_filter_catalog.json")
_ET = ZoneInfo("America/New_York")

_NAN = float("nan")
_FLOAT_PREFIX = re.compile(r"^[+-]?(?:Infinity|\d+\.?\d*(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?)")
_INT_PREFIX = re.compile(r"^[+-]?\d+")


# ── Semántica numérica de JavaScript ─────────────────────────────────────────

def js_parse_float(v: Any) -> Optional[float]:
    """parseFloat(): parseo de prefijo; NaN → None."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if v is None:
        return None
    m = _FLOAT_PREFIX.match(str(v).strip())
    if not m:
        return None
    tok = m.group(0)
    if tok.endswith("Infinity"):
        return float("-inf") if tok.startswith("-") else float("inf")
    return float(tok)


def js_parse_int(v: Any) -> Optional[int]:
    """parseInt() base 10: prefijo de dígitos; NaN → None."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        v = str(v)
    if v is None:
        return None
    m = _INT_PREFIX.match(str(v).strip())
    return int(m.group(0)) if m else None


def js_number(v: Any) -> float:
    """Coerción Number() de las comparaciones relacionales ('' → 0, no-numérico → NaN)."""
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)):
        return float(v)
    if v is None:
        return _NAN
    s = str(v).strip()
    if s == "":
        return 0.0
    try:
        return float(s)
    except ValueError:
        return _NAN


def minutes_since_market_open(ts: Any) -> Optional[float]:
    """Réplica de minutesSinceMarketOpen: naive = hora local del host (UTC en prod)."""
    if not ts:
        return None
    if isinstance(ts, (int, float)) and not isinstance(ts, bool):
        d = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
    else:
        try:
            d = datetime.fromisoformat(str(ts))
        except ValueError:
            return None
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
    et = d.astimezone(_ET)
    return (et.hour * 60 + et.minute) - (9 * 60 + 30)


# ── Catálogo de filtros (el MISMO json que carga el websocket) ───────────────

def load_filter_catalog(path: Optional[Path] = None) -> dict:
    cat = json.loads((path or _CATALOG_PATH).read_text(encoding="utf-8"))
    return {
        "numeric": [(r["subKey"], r["dataKey"], r["parser"]) for r in cat["numeric"]],
        "string": [(r["subKey"], r["dataKey"]) for r in cat["string"]],
    }


_catalog = load_filter_catalog()


def _pick_wire_key(data: dict, data_key: str, sub_key: str) -> Optional[str]:
    if data_key in data:
        return data_key
    if sub_key in data:
        return sub_key
    if data_key == "change_min" and "min_change_percent" in data:
        return "min_change_percent"
    if data_key == "change_max" and "max_change_percent" in data:
        return "max_change_percent"
    if data_key.endswith("_min"):
        legacy = f"min_{data_key[:-4]}"
        if legacy in data:
            return legacy
    if data_key.endswith("_max"):
        legacy = f"max_{data_key[:-4]}"
        if legacy in data:
            return legacy
    return None


def _pf(data: dict, key: str) -> Optional[float]:
    v = data.get(key)
    return js_parse_float(v) if v is not None else None


def _pi(data: dict, key: str) -> Optional[int]:
    v = data.get(key)
    return js_parse_int(v) if v is not None else None


def _ps(data: dict, key: str) -> Optional[str]:
    v = data.get(key)
    return str(v) if v is not None and v != "" else None


_PARSERS = {"pf": _pf, "pi": _pi}


def build_event_subscription(data: dict) -> dict:
    """Réplica de buildEventSubscription (acepta formato legacy min_/max_)."""
    requested = data.get("event_types")
    sub: Dict[str, Any] = {
        "allTypes": not requested,
        "eventTypes": set(requested or []),
        "symbolsInclude": None,
        "symbolsExclude": set(),
    }
    for sub_key, data_key, parser in _catalog["numeric"]:
        wire = _pick_wire_key(data, data_key, sub_key)
        if not wire or data[wire] is None:
            sub[sub_key] = None
        else:
            sub[sub_key] = _PARSERS[parser](data, wire)
    for sub_key, data_key in _catalog["string"]:
        wire = _pick_wire_key(data, data_key, sub_key)
        sub[sub_key] = _ps(data, wire) if wire else None

    if isinstance(data.get("symbols_include"), list):
        sub["symbolsInclude"] = {str(s).upper() for s in data["symbols_include"]}
    if isinstance(data.get("symbols_exclude"), list):
        sub["symbolsExclude"] = {str(s).upper() for s in data["symbols_exclude"]}

    aq: Dict[str, float] = {}
    for key, val in data.items():
        if key.startswith("aq:") and val is not None:
            n = js_parse_float(val)
            if n is not None:
                aq[key[3:]] = n
    sub["alertQuality"] = aq
    return sub


def build_event_payload(event_data: dict) -> dict:
    """Réplica del fragmento de broadcastMarketEvent que parsea el evento."""
    payload: Dict[str, Any] = {
        "event_type": event_data.get("event_type"),
        "symbol": event_data.get("symbol"),
    }
    details = None
    if event_data.get("details"):
        raw = event_data["details"]
        if isinstance(raw, str):
            try:
                details = json.loads(raw)
            except (ValueError, TypeError):
                details = None
        else:
            details = raw
    for key, raw in event_data.items():
        if key in ("event_type", "symbol"):
            continue
        if key == "details":
            payload["details"] = details
            continue
        if key in PAYLOAD_STRING_FIELDS:
            payload[key] = raw
            continue
        if key in PAYLOAD_INT_FIELDS:
            payload[key] = js_parse_int(raw)
            continue
        payload[key] = js_parse_float(raw)
    return payload


def enrich_event_from_cache(evt: dict, cache: Dict[str, dict]) -> None:
    """Réplica de enrichEventFromCache (muta evt ANTES del matching)."""
    enriched = cache.get(evt.get("symbol"))
    if not enriched:
        return
    for key in ENRICHED_FLOAT_FIELDS:
        evt_key = ENRICHED_KEY_REMAP.get(key, key)
        if evt.get(evt_key) is None and enriched.get(key) is not None:
            v = enriched[key]
            n = float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else js_parse_float(v)
            if n is not None and not math.isnan(n):
                evt[evt_key] = n
    for key in ENRICHED_INT_FIELDS:
        evt_key = ENRICHED_KEY_REMAP.get(key, key)
        if evt.get(evt_key) is None and enriched.get(key) is not None:
            n = js_parse_int(enriched[key])
            if n is not None:
                evt[evt_key] = n
    for key in ENRICHED_STRING_FIELDS:
        evt_key = ENRICHED_KEY_REMAP.get(key, key)
        cur = evt.get(evt_key)
        v = enriched.get(key)
        if (cur is None or cur == "") and v is not None and v != "":
            evt[evt_key] = str(v)
    if evt.get("spread") is None and evt.get("ask") is not None and evt.get("bid") is not None:
        evt["spread"] = float(f"{js_number(evt['ask']) - js_number(evt['bid']):.4f}")


def _chk(v: Any, lo: Optional[float], hi: Optional[float]) -> bool:
    """Réplica exacta de chkEvt: estricto con ausentes, rangos invertidos, NaN."""
    if lo is None and hi is None:
        return True
    if v is None:
        return False
    x = v if isinstance(v, (int, float)) and not isinstance(v, bool) else js_number(v)
    if lo is not None and hi is not None and lo > hi:
        return x >= lo or x <= hi
    if lo is not None and x < lo:
        return False
    if hi is not None and x > hi:
        return False
    return True


def event_passes_subscription(evt: dict, sub: dict, cache: Dict[str, dict]) -> bool:
    """Réplica 1:1 de eventPassesSubscription."""
    if not sub["allTypes"] and sub["eventTypes"] and evt.get("event_type") not in sub["eventTypes"]:
        return False
    inc = sub.get("symbolsInclude")
    if inc is not None and len(inc) > 0 and evt.get("symbol") not in inc:
        return False
    exc = sub.get("symbolsExclude")
    if exc and evt.get("symbol") in exc:
        return False

    enriched = cache.get(evt.get("symbol")) or {}
    spread = None
    if enriched.get("ask") is not None and enriched.get("bid") is not None:
        spread = js_number(enriched["ask"]) - js_number(enriched["bid"])

    def val(evt_field: str, enr_field: str) -> Any:
        v = evt.get(evt_field)
        if v is not None:
            return v
        e = enriched.get(enr_field)
        return e if e is not None else None

    for kind, args, min_key, max_key in CHECKS:
        if kind == "evt":
            v = evt.get(args[0])
        elif kind == "enr":
            v = enriched.get(args[0])
        elif kind == "val":
            v = val(args[0], args[1])
        elif kind == "spread":
            v = spread
        elif kind == "mso":
            if sub.get("minutesSinceOpenMin") is None and sub.get("minutesSinceOpenMax") is None:
                continue
            v = minutes_since_market_open(evt.get("timestamp"))
        else:  # pragma: no cover - el generador valida los kinds
            raise ValueError(f"kind desconocido: {kind}")
        if not _chk(v, sub.get(min_key), sub.get(max_key)):
            return False

    for camel_prefix, index_sym in INDEX_FILTER_DEFS:
        idx_row = None
        for w_camel, w_field in INDEX_FILTER_WINDOWS:
            min_key = f"{camel_prefix}{w_camel}Min"
            max_key = f"{camel_prefix}{w_camel}Max"
            if sub.get(min_key) is None and sub.get(max_key) is None:
                continue
            if idx_row is None:
                idx_row = cache.get(index_sym) or {}
            if w_field:
                v = idx_row.get(w_field)
            else:
                v = idx_row.get("change_percent")
                if v is None:
                    v = idx_row.get("premarket_change_percent")
            if not _chk(v, sub.get(min_key), sub.get(max_key)):
                return False

    if sub.get("securityType") is not None:
        st = evt.get("security_type") or enriched.get("security_type")
        if not st or str(st).upper() != sub["securityType"].upper():
            return False
    if sub.get("sector") is not None:
        s = evt.get("sector") or enriched.get("sector")
        if not s or sub["sector"].upper() not in str(s).upper():
            return False
    if sub.get("industry") is not None:
        ind = enriched.get("industry")
        if not ind or sub["industry"].upper() not in str(ind).upper():
            return False

    aq = sub.get("alertQuality")
    if aq:
        min_q = aq.get(evt.get("event_type"))
        if min_q is not None:
            q = evt.get("quality")
            if q is None or js_number(q) < min_q:
                return False

    return True


def match_event(event_fields: dict, sub_data: dict, cache: Dict[str, dict]) -> bool:
    """Pipeline completo: payload → enriquecido → suscripción → veredicto."""
    payload = build_event_payload(event_fields)
    enrich_event_from_cache(payload, cache)
    sub = build_event_subscription(sub_data)
    return event_passes_subscription(payload, sub, cache)
