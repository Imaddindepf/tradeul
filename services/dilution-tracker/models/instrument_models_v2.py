"""
Instrument models v2 aligned with dilutiontracker schema.

These models map 1:1 to:
- tickers
- instruments
- *_details tables
- completed_offerings
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated, Literal, Optional, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class OfferingType(str, Enum):
    ATM = "ATM"
    SHELF = "Shelf"
    WARRANT = "Warrant"
    CONVERTIBLE_NOTE = "Convertible Note"
    CONVERTIBLE_PREFERRED = "Convertible Preferred"
    EQUITY_LINE = "Equity Line"
    S1_OFFERING = "S-1 Offering"


class CardColor(str, Enum):
    RED = "red"
    YELLOW = "yellow"
    GRAY = "gray"


class BaseStrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InstrumentBase(BaseStrictModel):
    id: UUID
    ticker: str
    offering_type: OfferingType
    security_name: str
    card_color: CardColor
    reg_status: str
    edgar_url: Optional[str] = None
    file_number: Optional[str] = None
    last_update_date: Optional[date] = None
    created_at: datetime
    updated_at: datetime

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return value.upper().strip()

    @field_validator("edgar_url", "file_number", mode="before")
    @classmethod
    def empty_to_none(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class ATMDetails(BaseStrictModel):
    instrument_id: UUID
    total_atm_capacity: Optional[Decimal] = None
    remaining_atm_capacity: Optional[Decimal] = None
    atm_limited_by_baby_shelf: Optional[bool] = None
    remaining_capacity_wo_bs: Optional[Decimal] = None
    placement_agent: Optional[str] = None
    agreement_start_date: Optional[date] = None


class ShelfDetails(BaseStrictModel):
    instrument_id: UUID
    total_shelf_capacity: Optional[Decimal] = None
    current_raisable_amount: Optional[Decimal] = None
    total_amount_raised: Optional[Decimal] = None
    baby_shelf_restriction: Optional[bool] = None
    outstanding_shares: Optional[int] = None
    float_shares: Optional[int] = None
    highest_60_day_close: Optional[Decimal] = None
    ib6_float_value: Optional[Decimal] = None
    effect_date: Optional[date] = None
    expiration_date: Optional[date] = None
    last_banker: Optional[str] = None
    total_amt_raised_12mo_ib6: Optional[Decimal] = None
    price_to_exceed_bs: Optional[Decimal] = None


class WarrantDetails(BaseStrictModel):
    instrument_id: UUID
    remaining_warrants: Optional[Decimal] = None
    total_warrants_issued: Optional[Decimal] = None
    exercise_price: Optional[Decimal] = None
    price_protection: Optional[str] = None
    issue_date: Optional[date] = None
    exercisable_date: Optional[date] = None
    expiration_date: Optional[date] = None
    known_owners: Optional[str] = None
    underwriter: Optional[str] = None
    pp_clause: Optional[str] = None


class ConvertibleNoteDetails(BaseStrictModel):
    instrument_id: UUID
    remaining_principal: Optional[Decimal] = None
    total_principal: Optional[Decimal] = None
    conversion_price: Optional[Decimal] = None
    remaining_shares_converted: Optional[Decimal] = None
    total_shares_converted: Optional[Decimal] = None
    price_protection: Optional[str] = None
    issue_date: Optional[date] = None
    convertible_date: Optional[date] = None
    maturity_date: Optional[date] = None
    known_owners: Optional[str] = None
    pp_clause: Optional[str] = None
    underwriter: Optional[str] = None


class ConvertiblePreferredDetails(BaseStrictModel):
    instrument_id: UUID
    remaining_shares_converted: Optional[Decimal] = None
    remaining_dollar_amount: Optional[Decimal] = None
    conversion_price: Optional[Decimal] = None
    total_shares_converted: Optional[Decimal] = None
    total_dollar_amount: Optional[Decimal] = None
    price_protection: Optional[str] = None
    issue_date: Optional[date] = None
    convertible_date: Optional[date] = None
    maturity_date: Optional[date] = None
    known_owners: Optional[str] = None
    underwriter: Optional[str] = None
    pp_clause: Optional[str] = None


class EquityLineDetails(BaseStrictModel):
    instrument_id: UUID
    total_el_capacity: Optional[Decimal] = None
    remaining_el_capacity: Optional[Decimal] = None
    agreement_start_date: Optional[date] = None
    agreement_end_date: Optional[date] = None
    el_owners: Optional[str] = None
    current_shares_equiv: Optional[Decimal] = None


class S1Status(str, Enum):
    IN_PROGRESS = "In Progress"
    PRICED = "Priced"
    WITHDRAWN = "Withdrawn"


class S1OfferingDetails(BaseStrictModel):
    instrument_id: UUID
    anticipated_deal_size: Optional[Decimal] = None
    status: Optional[S1Status] = None
    s1_filing_date: Optional[date] = None
    warrant_coverage: Optional[Decimal] = None
    underwriter: Optional[str] = None
    final_deal_size: Optional[Decimal] = None
    final_pricing: Optional[Decimal] = None
    final_shares_offered: Optional[Decimal] = None
    final_warrant_coverage: Optional[Decimal] = None
    exercise_price: Optional[Decimal] = None


class ATMInstrument(InstrumentBase):
    offering_type: Literal[OfferingType.ATM]
    details: ATMDetails


class ShelfInstrument(InstrumentBase):
    offering_type: Literal[OfferingType.SHELF]
    details: ShelfDetails


class WarrantInstrument(InstrumentBase):
    offering_type: Literal[OfferingType.WARRANT]
    details: WarrantDetails


class ConvertibleNoteInstrument(InstrumentBase):
    offering_type: Literal[OfferingType.CONVERTIBLE_NOTE]
    details: ConvertibleNoteDetails


class ConvertiblePreferredInstrument(InstrumentBase):
    offering_type: Literal[OfferingType.CONVERTIBLE_PREFERRED]
    details: ConvertiblePreferredDetails


class EquityLineInstrument(InstrumentBase):
    offering_type: Literal[OfferingType.EQUITY_LINE]
    details: EquityLineDetails


class S1OfferingInstrument(InstrumentBase):
    offering_type: Literal[OfferingType.S1_OFFERING]
    details: S1OfferingDetails


InstrumentUnion = Annotated[
    Union[
        ATMInstrument,
        ShelfInstrument,
        WarrantInstrument,
        ConvertibleNoteInstrument,
        ConvertiblePreferredInstrument,
        EquityLineInstrument,
        S1OfferingInstrument,
    ],
    Field(discriminator="offering_type"),
]


class CompletedOffering(BaseStrictModel):
    id: int
    ticker: str
    offering_date: Optional[date] = None
    offering_type: Optional[str] = None
    method: Optional[str] = None
    shares: Optional[Decimal] = None
    price: Optional[Decimal] = None
    warrants: Optional[Decimal] = None
    amount: Optional[Decimal] = None
    bank: Optional[str] = None

    @field_validator("ticker")
    @classmethod
    def normalize_completed_ticker(cls, value: str) -> str:
        return value.upper().strip()


class TickerInfo(BaseStrictModel):
    ticker: str
    company: Optional[str] = None
    float_shares: Optional[int] = None
    inst_ownership: Optional[Decimal] = None
    short_interest: Optional[Decimal] = None
    market_cap: Optional[Decimal] = None
    enterprise_value: Optional[Decimal] = None
    cash_per_share: Optional[Decimal] = None
    shares_outstanding: Optional[int] = None
    cash_position: Optional[Decimal] = None
    last_price: Optional[Decimal] = None
    num_offerings: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @field_validator("ticker")
    @classmethod
    def normalize_ticker_info(cls, value: str) -> str:
        return value.upper().strip()


class InstrumentStats(BaseStrictModel):
    total: int
    registered: int
    pending_effect: int
    by_type: dict[str, int]


class TickerInstrumentContext(BaseStrictModel):
    ticker_info: TickerInfo
    instruments: list[InstrumentUnion]
    completed_offerings: list[CompletedOffering]
    stats: InstrumentStats
