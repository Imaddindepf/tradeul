"""Validación de frontera del backtester (Fase 1, §5.2-① del diseño).

Valida una estrategia BUILD ({event_types, ...filters}) contra los catálogos
canónicos ANTES de ejecutar nada:

  - eventos → shared/config/event_catalog.json (generado del registry, 279)
  - filtros → las mismas claves que acepta el websocket vivo: para cada
    definición del event_filter_catalog.json se aceptan exactamente las formas
    que resuelve pickWireKey (dataKey, subKey, legacy min_/max_, el caso
    especial de change) — replicado vía matching.matcher._pick_wire_key
  - especiales: aq:<tipo válido>, symbols_include/exclude, event_types

Nada desconocido se descarta en silencio: la API devuelve 422 con las listas
exactas (`unknown_events`, `unknown_filters`).

También clasifica cada filtro activo por su FUENTE de datos, que es lo que
decide la fidelidad histórica en L0:
  - event    → viaja en la fila del evento (exacto en el lake)
  - snapshot → sale del enrichedCache (en historia: slow snapshot del cierre)
  - index    → enrichedCache de SPY/QQQ/DIA (no reproducible en L0 v1)
  - clock    → derivado del timestamp del evento (exacto)
  - quality  → aq:; quality no se persiste (solo evaluable en vivo)
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, List

from matching.matcher import _catalog, _find_shared_config, _pick_wire_key
from matching.matcher_defs_generated import CHECKS, INDEX_FILTER_DEFS

_EVENT_CATALOG = _find_shared_config("event_catalog.json")

_SPECIAL_KEYS = {"event_types", "symbols_include", "symbols_exclude"}


@lru_cache(maxsize=1)
def valid_event_types() -> frozenset:
    cat = json.loads(_EVENT_CATALOG.read_text(encoding="utf-8"))
    return frozenset(e["event_type"] for e in cat["events"])


@lru_cache(maxsize=1)
def _sub_key_source() -> Dict[str, str]:
    """subKey base (sin Min/Max) → fuente, derivado de la tabla CHECKS generada."""
    kind_to_source = {"evt": "event", "val": "event", "enr": "snapshot",
                      "spread": "snapshot", "mso": "clock"}
    out: Dict[str, str] = {}
    for kind, _args, min_key, _max_key in CHECKS:
        out[min_key[:-3]] = kind_to_source[kind]
    for camel_prefix, _sym in INDEX_FILTER_DEFS:
        # las ventanas (5min/10min/…/Today) comparten prefijo de subKey
        out[camel_prefix] = "index"
    return out


def _resolve_filter_key(key: str) -> tuple:
    """(subKey, lado) si el vivo aceptaría esta clave; None si no."""
    probe = {key: 1}
    for sub_key, data_key, _parser in _catalog["numeric"]:
        if _pick_wire_key(probe, data_key, sub_key) == key:
            return sub_key, "numeric"
    for sub_key, data_key in _catalog["string"]:
        if _pick_wire_key(probe, data_key, sub_key) == key:
            return sub_key, "string"
    return None


def validate_strategy(sub_data: dict) -> Dict[str, List[str]]:
    """Listas exactas de lo NO reconocido. Vacías ⇒ la estrategia es válida."""
    unknown_events = [t for t in (sub_data.get("event_types") or [])
                      if t not in valid_event_types()]
    unknown_filters: List[str] = []
    for key in sub_data:
        if key in _SPECIAL_KEYS:
            continue
        if key.startswith("aq:"):
            if key[3:] not in valid_event_types():
                unknown_filters.append(key)
            continue
        if _resolve_filter_key(key) is None:
            unknown_filters.append(key)
    return {"unknown_events": unknown_events, "unknown_filters": sorted(unknown_filters)}


@lru_cache(maxsize=1)
def _sub_key_event_field() -> Dict[str, str]:
    """subKey base → campo del evento, para los checks con fuente 'event'."""
    out: Dict[str, str] = {}
    for kind, args, min_key, _max_key in CHECKS:
        if kind in ("evt", "val"):
            out[min_key[:-3]] = args[0]
    return out


def event_field_for(key: str) -> str | None:
    """Campo de la fila del evento que alimenta este filtro (None si no aplica)."""
    resolved = _resolve_filter_key(key)
    if resolved is None:
        return None
    sub_key, side = resolved
    if side == "string":
        return sub_key if sub_key in ("securityType", "sector") else None
    base = sub_key[:-3] if sub_key.endswith(("Min", "Max")) else sub_key
    return _sub_key_event_field().get(base)


def classify_filters(sub_data: dict) -> Dict[str, str]:
    """Fuente de datos de cada filtro activo (clave del cliente → fuente)."""
    sources = _sub_key_source()
    out: Dict[str, str] = {}
    for key, value in sub_data.items():
        if key in _SPECIAL_KEYS or value is None:
            continue
        if key.startswith("aq:"):
            out[key] = "quality"
            continue
        resolved = _resolve_filter_key(key)
        if resolved is None:
            continue  # validate_strategy ya lo reporta
        sub_key, side = resolved
        if side == "string":
            out[key] = "snapshot" if sub_key == "industry" else "event"
            continue
        base = sub_key[:-3] if sub_key.endswith(("Min", "Max")) else sub_key
        src = sources.get(base)
        if src is None:
            for camel_prefix, _sym in INDEX_FILTER_DEFS:
                if base.startswith(camel_prefix):
                    src = "index"
                    break
        out[key] = src or "snapshot"
    return out
