"""
AlertSpec IR — the intermediate representation every user alert compiles to.

Design principles (from CEP / SIEM / observability alerting research):
  1. The LLM emits ONLY this IR, never free-form code. Validation happens
     here (Pydantic), against the live event catalog, before anything runs.
  2. The IR is a superset routed by tier:
       T0 "event_match"  — stateless predicates on a single alert-engine
                           event (evaluated by the reactive TriggerEngine).
       T1 "sequence"     — ordered multi-step event sequences (dry-run via
                           strategy.scan_day_setups today; live CEP in phase 3).
       T2 "membership"   — enter/exit a scanner ranking (phase 4).
       T3 "agentic"      — trigger a LangGraph workflow on fire (existing
                           TriggerEngine "workflow" action).
  3. Every spec is versioned and carries its own provenance (the original
     NL sentence + the paraphrase the user confirmed), so a spec is always
     auditable back to intent.
"""
from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

SPEC_VERSION = 1

# Day-level metrics accepted by strategy.scan_day_setups day_conditions.
DAY_METRICS = {
    "open_price", "close_price", "low_price", "high_price",
    "close_vs_open_pct", "low_vs_open_pct", "high_vs_open_pct",
    "opening_drop_pct", "market_cap", "n_events",
}

_OPS = {"gt", "gte", "lt", "lte", "eq"}


class AlertTier(str, Enum):
    EVENT_MATCH = "event_match"   # T0 — stateless single-event predicates
    SEQUENCE = "sequence"         # T1 — ordered event sequence (stateful)
    MEMBERSHIP = "membership"     # T2 — scanner ranking enter/exit
    AGENTIC = "agentic"           # T3 — fire triggers a LangGraph workflow


class AlertStatus(str, Enum):
    DRAFT = "draft"         # compiled, dry-run shown, awaiting confirmation
    ARMED = "armed"         # live in the evaluation runtime
    PAUSED = "paused"       # kept but not evaluated
    ARCHIVED = "archived"   # soft-deleted


# ── Condition primitives ─────────────────────────────────────────

class Universe(BaseModel):
    """Pre-filters applied before any event/sequence logic (cheap firehose cut)."""
    symbols_include: list[str] = Field(default_factory=list)
    symbols_exclude: list[str] = Field(default_factory=list)
    min_price: Optional[float] = Field(None, ge=0)
    max_price: Optional[float] = Field(None, ge=0)
    min_rvol: Optional[float] = Field(None, ge=0)
    min_volume: Optional[int] = Field(None, ge=0)
    min_market_cap: Optional[float] = Field(None, ge=0)
    max_market_cap: Optional[float] = Field(None, ge=0)
    sector: Optional[str] = None
    session: Literal["regular", "premarket", "afterhours", "all"] = "regular"


class SequenceStep(BaseModel):
    """One step of an ordered event sequence (mirrors scan_day_setups steps)."""
    event_types: list[str] = Field(..., min_length=1)
    after: Literal["session_open", "opening_low", "prev_step"] = "prev_step"
    within_minutes: Optional[int] = Field(None, ge=1, le=480)

    @field_validator("event_types")
    @classmethod
    def _lower(cls, v: list[str]) -> list[str]:
        return [e.strip().lower() for e in v if e and e.strip()]


class DayCondition(BaseModel):
    """Day-level metric condition (close vs open, opening drop...)."""
    metric: str
    op: Literal["gt", "gte", "lt", "lte", "eq"]
    value: float

    @field_validator("metric")
    @classmethod
    def _known_metric(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in DAY_METRICS:
            raise ValueError(f"unknown day metric '{v}'. Valid: {sorted(DAY_METRICS)}")
        return v


class MembershipWatch(BaseModel):
    """T2 — watch a scanner category for enter/exit transitions (phase 4 runtime)."""
    category: str = Field(..., description="Scanner category, e.g. gappers_up")
    on: Literal["enter", "exit"] = "enter"
    rank_lte: Optional[int] = Field(None, ge=1, le=100)


class Lifecycle(BaseModel):
    """Anti-noise state machine parameters (Grafana/Prometheus model)."""
    cooldown_seconds: int = Field(900, ge=0, le=86400)
    max_fires_per_day: int = Field(20, ge=1, le=500)
    pending_seconds: int = Field(0, ge=0, le=3600,
                                 description="Condition must hold this long before firing (phase 3)")


class AlertAction(BaseModel):
    """What happens on fire. Phase 1-2: user alert stream (in-app) or workflow."""
    channel: Literal["in_app", "workflow"] = "in_app"
    message_template: Optional[str] = Field(
        None,
        description="Placeholders: {symbol}, {price}, {event_type}, {trigger_name}, {rvol}",
    )
    workflow_id: Optional[str] = None


# ── The IR itself ────────────────────────────────────────────────

class AlertSpec(BaseModel):
    """Versioned, validated intermediate representation of a user alert."""

    # Identity / provenance
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    version: int = Field(default=SPEC_VERSION)
    user_id: str = "default"
    name: str = Field(..., min_length=1, max_length=200)
    status: AlertStatus = AlertStatus.DRAFT
    source_query: str = Field("", description="Original NL sentence from the user")
    paraphrase: str = Field("", description="NL restatement of what the system understood")
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    # Routing
    tier: AlertTier = AlertTier.EVENT_MATCH

    # Conditions
    universe: Universe = Field(default_factory=Universe)
    steps: list[SequenceStep] = Field(default_factory=list, max_length=5)
    day_conditions: list[DayCondition] = Field(default_factory=list, max_length=6)
    membership: Optional[MembershipWatch] = None

    # Behaviour
    lifecycle: Lifecycle = Field(default_factory=Lifecycle)
    actions: list[AlertAction] = Field(default_factory=lambda: [AlertAction()])

    # Runtime linkage (set when armed)
    trigger_id: Optional[str] = Field(None, description="TriggerEngine id when armed as T0")

    # Dry-run summary (persisted for the UI: "would have fired N times")
    dry_run: Optional[dict[str, Any]] = None

    class Config:
        use_enum_values = True

    # ── Cross-field validation ──
    @model_validator(mode="after")
    def _validate_tier_shape(self) -> "AlertSpec":
        tier = self.tier if isinstance(self.tier, str) else self.tier.value
        if tier == AlertTier.MEMBERSHIP.value:
            if self.membership is None:
                raise ValueError("membership tier requires a membership watch")
        elif tier == AlertTier.AGENTIC.value:
            if not any(a.channel == "workflow" and a.workflow_id for a in self.actions):
                raise ValueError("agentic tier requires a workflow action with workflow_id")
        else:
            if not self.steps:
                raise ValueError(f"{tier} tier requires at least one sequence step")
            if tier == AlertTier.EVENT_MATCH.value and len(self.steps) > 1:
                raise ValueError("event_match tier accepts exactly one step; use sequence tier")
        return self

    # ── Derived helpers ──

    def is_t0_armable(self) -> bool:
        """True when this spec can run TODAY on the reactive TriggerEngine.

        T0 = single step, no ordering anchors beyond session_open, and only
        conditions the TriggerEngine evaluates (event_types, price, rvol,
        volume, symbol lists). Day conditions need the day to be over, so
        they exclude live arming.
        """
        tier = self.tier if isinstance(self.tier, str) else self.tier.value
        return (
            tier == AlertTier.EVENT_MATCH.value
            and len(self.steps) == 1
            and not self.day_conditions
        )

    def to_trigger_config(self) -> dict[str, Any]:
        """Compile a T0 spec into the existing TriggerEngine config shape."""
        if not self.is_t0_armable():
            raise ValueError("spec is not T0-armable; live sequence runtime lands in phase 3")

        step = self.steps[0]
        workflow = next(
            (a for a in self.actions if a.channel == "workflow" and a.workflow_id), None,
        )
        alert_action = next((a for a in self.actions if a.channel == "in_app"), None)

        return {
            "id": self.trigger_id or uuid.uuid4().hex,
            "user_id": self.user_id,
            "name": self.name,
            "spec_id": self.id,
            "enabled": True,
            "conditions": {
                "event_types": step.event_types,
                "min_price": self.universe.min_price,
                "max_price": self.universe.max_price,
                "min_rvol": self.universe.min_rvol,
                "min_volume": self.universe.min_volume,
                "symbols_include": self.universe.symbols_include,
                "symbols_exclude": self.universe.symbols_exclude,
            },
            "action": {
                "type": "workflow" if workflow else "alert",
                "workflow_id": workflow.workflow_id if workflow else None,
                "message_template": (alert_action.message_template if alert_action else None),
            },
            "cooldown_seconds": self.lifecycle.cooldown_seconds,
            "last_triggered": None,
        }

    def to_scan_args(self, date: str) -> dict[str, Any]:
        """Compile this spec into strategy.scan_day_setups arguments (dry-run)."""
        args: dict[str, Any] = {
            "steps": [s.model_dump(exclude_none=True) for s in self.steps],
            "date": date,
            "session": self.universe.session,
            "day_conditions": [c.model_dump() for c in self.day_conditions],
            "limit": 50,
        }
        if self.universe.symbols_include:
            args["symbols"] = self.universe.symbols_include
        if self.universe.symbols_exclude:
            args["exclude_symbols"] = self.universe.symbols_exclude
        if self.universe.min_market_cap is not None:
            args["min_market_cap"] = self.universe.min_market_cap
        if self.universe.max_market_cap is not None:
            args["max_market_cap"] = self.universe.max_market_cap
        if self.universe.min_price is not None:
            args["min_price"] = self.universe.min_price
        if self.universe.max_price is not None:
            args["max_price"] = self.universe.max_price
        if self.universe.min_rvol is not None:
            args["min_rvol"] = self.universe.min_rvol
        if self.universe.sector:
            args["sector"] = self.universe.sector
        return args


def validate_event_types(spec: AlertSpec, known_types: set[str]) -> list[str]:
    """Return event types referenced by the spec that are unknown to the engine.

    The compiler calls this with the LIVE catalog so hallucinated event
    names are rejected before the spec reaches the user.
    """
    if not known_types:
        return []
    unknown: list[str] = []
    for step in spec.steps:
        for et in step.event_types:
            if et not in known_types:
                unknown.append(et)
    return unknown
