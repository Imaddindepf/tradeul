"""
Repository for dilutiontracker instrument-context loading.

Maps public schema:
- tickers
- instruments
- *_details
- completed_offerings
"""

import sys
from collections import Counter
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

SERVICE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.append(str(SERVICE_ROOT))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))
if "/app" not in sys.path:
    sys.path.append("/app")

from shared.utils.logger import get_logger
from shared.utils.timescale_client import TimescaleClient
from models.instrument_models_v2 import (
    ATMDetails,
    ATMInstrument,
    CompletedOffering,
    ConvertibleNoteDetails,
    ConvertibleNoteInstrument,
    ConvertiblePreferredDetails,
    ConvertiblePreferredInstrument,
    EquityLineDetails,
    EquityLineInstrument,
    InstrumentBase,
    InstrumentStats,
    OfferingType,
    S1OfferingDetails,
    S1OfferingInstrument,
    ShelfDetails,
    ShelfInstrument,
    TickerInfo,
    TickerInstrumentContext,
    WarrantDetails,
    WarrantInstrument,
)

logger = get_logger(__name__)


DETAIL_TABLE_BY_TYPE = {
    OfferingType.ATM: ("atm_details", ATMDetails),
    OfferingType.SHELF: ("shelf_details", ShelfDetails),
    OfferingType.WARRANT: ("warrant_details", WarrantDetails),
    OfferingType.CONVERTIBLE_NOTE: ("conv_note_details", ConvertibleNoteDetails),
    OfferingType.CONVERTIBLE_PREFERRED: ("conv_preferred_details", ConvertiblePreferredDetails),
    OfferingType.EQUITY_LINE: ("equity_line_details", EquityLineDetails),
    OfferingType.S1_OFFERING: ("s1_offering_details", S1OfferingDetails),
}


class InstrumentContextRepository:
    """Loads fully-typed instrument context for one ticker."""

    def __init__(self, db: TimescaleClient):
        self.db = db

    async def get_ticker_context(
        self,
        ticker: str,
        include_completed_offerings: bool = True,
    ) -> Optional[TickerInstrumentContext]:
        ticker = ticker.upper().strip()

        ticker_row = await self.db.fetchrow(
            """
            SELECT ticker, company, float_shares, inst_ownership, short_interest,
                   market_cap, enterprise_value, cash_per_share, shares_outstanding,
                   cash_position, last_price, num_offerings, created_at, updated_at
            FROM tickers
            WHERE ticker = $1
            """,
            ticker,
        )
        if not ticker_row:
            return None

        instrument_rows = await self.db.fetch(
            """
            SELECT id, ticker, offering_type, security_name, card_color, reg_status,
                   edgar_url, file_number, last_update_date, created_at, updated_at
            FROM instruments
            WHERE ticker = $1
            ORDER BY updated_at DESC, created_at DESC
            """,
            ticker,
        )

        detail_maps = await self._load_detail_maps(instrument_rows)
        instruments = []
        for row in instrument_rows:
            base = InstrumentBase.model_validate(row)
            details = detail_maps.get(base.offering_type, {}).get(base.id)
            if details is None:
                raise ValueError(
                    f"Missing detail row for instrument_id={base.id} "
                    f"type={base.offering_type.value}"
                )
            instruments.append(self._compose_instrument(base, details))

        completed_offerings: list[CompletedOffering] = []
        if include_completed_offerings:
            offering_rows = await self.db.fetch(
                """
                SELECT id, ticker, offering_date, offering_type, method, shares,
                       price, warrants, amount, bank
                FROM completed_offerings
                WHERE ticker = $1
                ORDER BY offering_date DESC NULLS LAST, id DESC
                """,
                ticker,
            )
            completed_offerings = [
                CompletedOffering.model_validate(row) for row in offering_rows
            ]

        by_type = Counter(item.offering_type.value for item in instruments)
        stats = InstrumentStats(
            total=len(instruments),
            registered=sum(1 for item in instruments if item.reg_status == "Registered"),
            pending_effect=sum(1 for item in instruments if item.reg_status == "Pending Effect"),
            by_type=dict(by_type),
        )

        return TickerInstrumentContext(
            ticker_info=TickerInfo.model_validate(ticker_row),
            instruments=instruments,
            completed_offerings=completed_offerings,
            stats=stats,
        )

    async def _load_detail_maps(
        self,
        instrument_rows: list[dict[str, Any]],
    ) -> dict[OfferingType, dict[UUID, Any]]:
        by_type_ids: dict[OfferingType, list[UUID]] = {}
        for row in instrument_rows:
            offering_type = OfferingType(str(row["offering_type"]))
            by_type_ids.setdefault(offering_type, []).append(row["id"])

        detail_maps: dict[OfferingType, dict[UUID, Any]] = {}
        for offering_type, ids in by_type_ids.items():
            table_name, model_cls = DETAIL_TABLE_BY_TYPE[offering_type]
            detail_rows = await self.db.fetch(
                f"SELECT * FROM {table_name} WHERE instrument_id = ANY($1::uuid[])",
                ids,
            )
            detail_maps[offering_type] = {
                item["instrument_id"]: model_cls.model_validate(item) for item in detail_rows
            }
        return detail_maps

    def _compose_instrument(self, base: InstrumentBase, details: Any):
        payload = {**base.model_dump(), "details": details}
        if base.offering_type == OfferingType.ATM:
            return ATMInstrument.model_validate(payload)
        if base.offering_type == OfferingType.SHELF:
            return ShelfInstrument.model_validate(payload)
        if base.offering_type == OfferingType.WARRANT:
            return WarrantInstrument.model_validate(payload)
        if base.offering_type == OfferingType.CONVERTIBLE_NOTE:
            return ConvertibleNoteInstrument.model_validate(payload)
        if base.offering_type == OfferingType.CONVERTIBLE_PREFERRED:
            return ConvertiblePreferredInstrument.model_validate(payload)
        if base.offering_type == OfferingType.EQUITY_LINE:
            return EquityLineInstrument.model_validate(payload)
        if base.offering_type == OfferingType.S1_OFFERING:
            return S1OfferingInstrument.model_validate(payload)
        raise ValueError(f"Unsupported offering_type={base.offering_type}")
