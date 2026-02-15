"""
Pydantic models for the Reactive Trigger Engine.

Defines the schema for trigger configuration, conditions, actions, and
the inbound market events that are evaluated against triggers.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────────────


class ActionType(str, Enum):
    WORKFLOW = "workflow"
    ALERT = "alert"


# ── Trigger sub-models ───────────────────────────────────────────


class TriggerConditions(BaseModel):
    """Conditions that must all be satisfied for a trigger to fire."""

    event_types: list[str] = Field(
        default_factory=list,
        description="Event types to match (e.g. halt_pending, volume_spike). Empty = all.",
    )
    min_price: Optional[float] = Field(
        None,
        ge=0,
        description="Minimum price threshold. None = no filter.",
    )
    max_price: Optional[float] = Field(
        None,
        ge=0,
        description="Maximum price threshold. None = no filter.",
    )
    min_rvol: Optional[float] = Field(
        None,
        ge=0,
        description="Minimum relative volume. None = no filter.",
    )
    min_volume: Optional[int] = Field(
        None,
        ge=0,
        description="Minimum absolute volume. None = no filter.",
    )
    symbols_include: list[str] = Field(
        default_factory=list,
        description="Only match these symbols. Empty = all symbols.",
    )
    symbols_exclude: list[str] = Field(
        default_factory=list,
        description="Never match these symbols.",
    )


class TriggerAction(BaseModel):
    """Action to perform when the trigger fires."""

    type: ActionType = Field(
        ...,
        description="Action type: 'workflow' to invoke a LangGraph workflow, "
                    "'alert' to send a notification.",
    )

    # Workflow action fields
    workflow_id: Optional[str] = Field(
        None,
        description="UUID of the saved workflow to execute (required when type=workflow).",
    )

    # Alert action fields
    message_template: Optional[str] = Field(
        None,
        description="Template string for the alert message. "
                    "Supports placeholders: {symbol}, {price}, {volume}, {event_type}.",
    )


class TriggerConfig(BaseModel):
    """Full trigger configuration stored per user."""

    id: str = Field(..., description="Unique trigger UUID.")
    user_id: str = Field(..., description="Owner of this trigger.")
    name: str = Field(..., min_length=1, max_length=256, description="Human-readable name.")
    enabled: bool = Field(True, description="Whether the trigger is active.")

    conditions: TriggerConditions = Field(
        default_factory=TriggerConditions,
        description="Conditions that must match for the trigger to fire.",
    )
    action: TriggerAction = Field(
        ...,
        description="Action to perform when the trigger fires.",
    )

    cooldown_seconds: int = Field(
        300,
        ge=0,
        description="Minimum seconds between consecutive firings (default 5 min).",
    )
    last_triggered: Optional[float] = Field(
        None,
        description="Unix timestamp of the last time this trigger fired.",
    )

    class Config:
        use_enum_values = True


# ── Inbound market event ────────────────────────────────────────


class TriggerEvent(BaseModel):
    """A market event received from the Redis stream.

    This is the normalised representation used internally; the raw Redis
    stream entry is parsed into this model before evaluation.
    """

    event_id: str = Field(..., description="Redis stream message ID.")
    event_type: str = Field(..., description="Type of market event (e.g. halt_pending).")
    symbol: str = Field(..., description="Ticker symbol.")
    price: Optional[float] = Field(None, description="Current price at event time.")
    volume: Optional[int] = Field(None, description="Current volume.")
    rvol: Optional[float] = Field(None, description="Relative volume.")
    timestamp: float = Field(..., description="Unix epoch timestamp of the event.")
    raw: dict[str, Any] = Field(
        default_factory=dict,
        description="Original payload from the Redis stream entry.",
    )
