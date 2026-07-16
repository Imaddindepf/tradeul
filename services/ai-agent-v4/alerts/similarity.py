"""
Detect duplicate / near-duplicate AlertSpecs for a user.

Exact match → same fingerprint (event types + universe filters + membership).
Near match  → same primary event/membership + overlapping symbols, different
              thresholds (e.g. RVOL 1.5 vs 2.0) — surface for the user to decide.
"""
from __future__ import annotations

from typing import Any, Optional

from alerts.spec import AlertSpec


def _norm_symbols(syms: list[str] | None) -> tuple[str, ...]:
    return tuple(sorted({(s or "").upper() for s in (syms or []) if s}))


def _step_signature(spec: AlertSpec) -> tuple:
    steps = []
    for s in spec.steps or []:
        steps.append((
            tuple(sorted(s.event_types or [])),
            s.after,
            s.within_minutes,
        ))
    return tuple(steps)


def _day_signature(spec: AlertSpec) -> tuple:
    return tuple(
        sorted((c.metric, c.op, float(c.value)) for c in (spec.day_conditions or []))
    )


def _membership_signature(spec: AlertSpec) -> tuple | None:
    m = spec.membership
    if m is None:
        return None
    return (m.category, m.on, m.rank_lte)


def fingerprint(spec: AlertSpec) -> tuple:
    """Stable identity of what the alert watches (ignores name/id/status)."""
    u = spec.universe
    tier = spec.tier if isinstance(spec.tier, str) else spec.tier.value
    return (
        tier,
        _norm_symbols(u.symbols_include),
        _norm_symbols(u.symbols_exclude),
        u.min_price, u.max_price,
        u.min_rvol, u.min_volume,
        u.min_market_cap, u.max_market_cap,
        (u.sector or "").lower() or None,
        u.session,
        _step_signature(spec),
        _day_signature(spec),
        _membership_signature(spec),
    )


def _soft_key(spec: AlertSpec) -> tuple:
    """Coarser key: same intent family (ticker set + primary events/category)."""
    u = spec.universe
    tier = spec.tier if isinstance(spec.tier, str) else spec.tier.value
    events: tuple[str, ...] = ()
    if spec.steps:
        events = tuple(sorted({e for s in spec.steps for e in (s.event_types or [])}))
    mem = None
    if spec.membership:
        mem = (spec.membership.category, spec.membership.on)
    return (tier, _norm_symbols(u.symbols_include), events, mem, u.session)


def _summarize(raw: dict[str, Any]) -> dict[str, Any]:
    steps = raw.get("steps") or []
    events = []
    for s in steps:
        events.extend(s.get("event_types") or [])
    mem = raw.get("membership") or {}
    return {
        "spec_id": raw.get("id"),
        "name": raw.get("name"),
        "status": raw.get("status"),
        "tier": raw.get("tier"),
        "paraphrase": raw.get("paraphrase") or "",
        "symbols": (raw.get("universe") or {}).get("symbols_include") or [],
        "event_types": events,
        "membership": mem or None,
        "updated_at": raw.get("updated_at"),
    }


def find_similar(
    candidate: AlertSpec,
    existing: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare candidate against the user's specs.

    Returns:
      {
        "exact": [summaries...],   # identical fingerprint (not archived)
        "near":  [summaries...],   # same soft key, different fingerprint
        "recommendation": "create" | "reuse" | "review"
      }
    """
    cand_fp = fingerprint(candidate)
    cand_soft = _soft_key(candidate)
    exact: list[dict] = []
    near: list[dict] = []

    for raw in existing:
        if raw.get("id") == candidate.id:
            continue
        status = raw.get("status") or "draft"
        if status == "archived":
            continue
        try:
            other = AlertSpec(**raw)
        except Exception:
            continue
        if fingerprint(other) == cand_fp:
            exact.append(_summarize(raw))
        elif _soft_key(other) == cand_soft:
            near.append(_summarize(raw))

    if exact:
        # Prefer pointing at an already-armed copy
        armed = [e for e in exact if e["status"] == "armed"]
        recommendation = "reuse"
        ordered = armed + [e for e in exact if e not in armed]
        return {"exact": ordered, "near": near, "recommendation": recommendation}
    if near:
        return {"exact": [], "near": near, "recommendation": "review"}
    return {"exact": [], "near": [], "recommendation": "create"}
