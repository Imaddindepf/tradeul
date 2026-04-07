"""
Pydantic contracts for agent-driven instrument actions (v2).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from models.instrument_models_v2 import CardColor, OfferingType


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ActionKind(str, Enum):
    CREATE = "create_instrument"
    UPDATE = "update_instrument"
    TRANSITION = "state_transition"
    LOG = "log_only"


class InstrumentBasePatch(StrictModel):
    security_name: Optional[str] = None
    card_color: Optional[CardColor] = None
    reg_status: Optional[str] = None
    edgar_url: Optional[str] = None
    file_number: Optional[str] = None
    last_update_date: Optional[date] = None


class CreateInstrumentAction(StrictModel):
    action: Literal[ActionKind.CREATE]
    offering_type: OfferingType
    base: InstrumentBasePatch = Field(
        ...,
        description="Base fields for instruments table. security_name/reg_status/card_color expected.",
    )
    details: dict[str, Any] = Field(default_factory=dict)
    reason: Optional[str] = None
    confidence: Decimal = Field(default=Decimal("0.0"), ge=Decimal("0"), le=Decimal("1"))
    evidence: list[str] = Field(default_factory=list)


class UpdateInstrumentAction(StrictModel):
    action: Literal[ActionKind.UPDATE]
    instrument_id: UUID
    base: InstrumentBasePatch = Field(default_factory=InstrumentBasePatch)
    details: dict[str, Any] = Field(default_factory=dict)
    reason: Optional[str] = None
    confidence: Decimal = Field(default=Decimal("0.0"), ge=Decimal("0"), le=Decimal("1"))
    evidence: list[str] = Field(default_factory=list)


class TransitionInstrumentAction(StrictModel):
    action: Literal[ActionKind.TRANSITION]
    instrument_id: UUID
    new_reg_status: str
    transition_date: Optional[date] = None
    reason: Optional[str] = None
    confidence: Decimal = Field(default=Decimal("0.0"), ge=Decimal("0"), le=Decimal("1"))
    evidence: list[str] = Field(default_factory=list)


class LogOnlyAction(StrictModel):
    action: Literal[ActionKind.LOG]
    reason: str
    confidence: Decimal = Field(default=Decimal("0.0"), ge=Decimal("0"), le=Decimal("1"))
    evidence: list[str] = Field(default_factory=list)


AgentAction = CreateInstrumentAction | UpdateInstrumentAction | TransitionInstrumentAction | LogOnlyAction


class FilingActionBatch(StrictModel):
    accession_number: str
    ticker: str
    form_type: str
    filing_date: date
    filing_url: Optional[str] = None
    agent_model: Optional[str] = None
    agent_summary: Optional[str] = None
    actions: list[AgentAction]

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return value.upper().strip()


class ApplyActionsRequest(StrictModel):
    dry_run: bool = True
    batch: FilingActionBatch


class AppliedChange(StrictModel):
    action: str
    instrument_id: Optional[UUID] = None
    result: str
    details: dict[str, Any] = Field(default_factory=dict)


class ApplyActionsResponse(StrictModel):
    dry_run: bool
    ticker: str
    accession_number: str
    applied: bool
    changes: list[AppliedChange]
    warnings: list[str] = Field(default_factory=list)
