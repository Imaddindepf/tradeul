"""
Transactional applier for agent action batches (v2).
"""

from __future__ import annotations

import sys
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

SERVICE_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.append(str(SERVICE_ROOT))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))
if "/app" not in sys.path:
    sys.path.append("/app")

from models.agent_actions_v2 import (
    ActionKind,
    AppliedChange,
    ApplyActionsRequest,
    ApplyActionsResponse,
    CreateInstrumentAction,
    LogOnlyAction,
    TransitionInstrumentAction,
    UpdateInstrumentAction,
)
from models.instrument_models_v2 import OfferingType
from shared.utils.logger import get_logger
from shared.utils.timescale_client import TimescaleClient

logger = get_logger(__name__)


DETAIL_COLUMNS: dict[OfferingType, set[str]] = {
    OfferingType.ATM: {
        "total_atm_capacity",
        "remaining_atm_capacity",
        "atm_limited_by_baby_shelf",
        "remaining_capacity_wo_bs",
        "placement_agent",
        "agreement_start_date",
    },
    OfferingType.SHELF: {
        "total_shelf_capacity",
        "current_raisable_amount",
        "total_amount_raised",
        "baby_shelf_restriction",
        "outstanding_shares",
        "float_shares",
        "highest_60_day_close",
        "ib6_float_value",
        "effect_date",
        "expiration_date",
        "last_banker",
        "total_amt_raised_12mo_ib6",
        "price_to_exceed_bs",
    },
    OfferingType.WARRANT: {
        "remaining_warrants",
        "total_warrants_issued",
        "exercise_price",
        "price_protection",
        "issue_date",
        "exercisable_date",
        "expiration_date",
        "known_owners",
        "underwriter",
        "pp_clause",
    },
    OfferingType.CONVERTIBLE_NOTE: {
        "remaining_principal",
        "total_principal",
        "conversion_price",
        "remaining_shares_converted",
        "total_shares_converted",
        "price_protection",
        "issue_date",
        "convertible_date",
        "maturity_date",
        "known_owners",
        "pp_clause",
        "underwriter",
    },
    OfferingType.CONVERTIBLE_PREFERRED: {
        "remaining_shares_converted",
        "remaining_dollar_amount",
        "conversion_price",
        "total_shares_converted",
        "total_dollar_amount",
        "price_protection",
        "issue_date",
        "convertible_date",
        "maturity_date",
        "known_owners",
        "underwriter",
        "pp_clause",
    },
    OfferingType.EQUITY_LINE: {
        "total_el_capacity",
        "remaining_el_capacity",
        "agreement_start_date",
        "agreement_end_date",
        "el_owners",
        "current_shares_equiv",
    },
    OfferingType.S1_OFFERING: {
        "anticipated_deal_size",
        "status",
        "s1_filing_date",
        "warrant_coverage",
        "underwriter",
        "final_deal_size",
        "final_pricing",
        "final_shares_offered",
        "final_warrant_coverage",
        "exercise_price",
    },
}

DETAIL_TABLE_BY_TYPE: dict[OfferingType, str] = {
    OfferingType.ATM: "atm_details",
    OfferingType.SHELF: "shelf_details",
    OfferingType.WARRANT: "warrant_details",
    OfferingType.CONVERTIBLE_NOTE: "conv_note_details",
    OfferingType.CONVERTIBLE_PREFERRED: "conv_preferred_details",
    OfferingType.EQUITY_LINE: "equity_line_details",
    OfferingType.S1_OFFERING: "s1_offering_details",
}


class AgentActionServiceV2:
    def __init__(self, db: TimescaleClient):
        self.db = db

    async def apply(self, req: ApplyActionsRequest) -> ApplyActionsResponse:
        ticker = req.batch.ticker
        warnings: list[str] = []
        changes: list[AppliedChange] = []

        ticker_exists = await self.db.fetchval(
            "SELECT 1 FROM tickers WHERE ticker = $1",
            ticker,
        )
        if not ticker_exists:
            raise ValueError(f"Ticker {ticker} not found in dilution database")

        create_count = sum(1 for item in req.batch.actions if item.action == ActionKind.CREATE)
        multi_create = create_count > 1

        async with self.db.transaction() as conn:
            for action in req.batch.actions:
                if isinstance(action, CreateInstrumentAction):
                    change = await self._handle_create(
                        conn=conn,
                        ticker=ticker,
                        action=action,
                        dry_run=req.dry_run,
                    )
                    changes.append(change)
                    if not req.dry_run:
                        await self._insert_filing_event(
                            conn=conn,
                            ticker=ticker,
                            instrument_id=change.instrument_id,
                            req=req,
                            purpose=action.reason or "create instrument",
                            agent_action="MULTI_CREATE" if multi_create else "CREATE",
                            raw_payload=action.model_dump(mode="json"),
                        )
                elif isinstance(action, UpdateInstrumentAction):
                    change = await self._handle_update(
                        conn=conn,
                        ticker=ticker,
                        action=action,
                        dry_run=req.dry_run,
                    )
                    changes.append(change)
                    if not req.dry_run:
                        await self._insert_filing_event(
                            conn=conn,
                            ticker=ticker,
                            instrument_id=action.instrument_id,
                            req=req,
                            purpose=action.reason or "update instrument",
                            agent_action="UPDATE",
                            raw_payload=action.model_dump(mode="json"),
                        )
                elif isinstance(action, TransitionInstrumentAction):
                    change = await self._handle_transition(
                        conn=conn,
                        ticker=ticker,
                        action=action,
                        dry_run=req.dry_run,
                    )
                    changes.append(change)
                    if not req.dry_run:
                        await self._insert_filing_event(
                            conn=conn,
                            ticker=ticker,
                            instrument_id=action.instrument_id,
                            req=req,
                            purpose=action.reason or "state transition",
                            agent_action="UPDATE",
                            raw_payload=action.model_dump(mode="json"),
                        )
                elif isinstance(action, LogOnlyAction):
                    changes.append(
                        AppliedChange(
                            action=action.action.value,
                            result="logged_only",
                            details={"reason": action.reason},
                        )
                    )
                    if not req.dry_run:
                        await self._insert_filing_event(
                            conn=conn,
                            ticker=ticker,
                            instrument_id=None,
                            req=req,
                            purpose=action.reason,
                            agent_action="LOG",
                            raw_payload=action.model_dump(mode="json"),
                        )
                else:
                    warnings.append(f"Unsupported action type: {type(action).__name__}")

        return ApplyActionsResponse(
            dry_run=req.dry_run,
            ticker=ticker,
            accession_number=req.batch.accession_number,
            applied=not req.dry_run,
            changes=changes,
            warnings=warnings,
        )

    async def _handle_create(self, conn, ticker: str, action: CreateInstrumentAction, dry_run: bool) -> AppliedChange:
        if not action.base.security_name or not action.base.reg_status or not action.base.card_color:
            raise ValueError("create_instrument requires base.security_name, base.reg_status and base.card_color")

        instrument_id = uuid4()
        details = self._sanitize_details(action.offering_type, action.details)

        if dry_run:
            return AppliedChange(
                action=action.action.value,
                instrument_id=instrument_id,
                result="would_create",
                details={"offering_type": action.offering_type.value, "details_keys": sorted(details.keys())},
            )

        await conn.execute(
            """
            INSERT INTO instruments (
                id, ticker, offering_type, security_name, card_color, reg_status,
                edgar_url, file_number, last_update_date, created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW(), NOW())
            """,
            instrument_id,
            ticker,
            action.offering_type.value,
            action.base.security_name,
            action.base.card_color.value,
            action.base.reg_status,
            action.base.edgar_url,
            action.base.file_number,
            action.base.last_update_date,
        )
        await self._upsert_details(conn, action.offering_type, instrument_id, details, insert_mode=True)

        return AppliedChange(
            action=action.action.value,
            instrument_id=instrument_id,
            result="created",
            details={"offering_type": action.offering_type.value},
        )

    async def _handle_update(self, conn, ticker: str, action: UpdateInstrumentAction, dry_run: bool) -> AppliedChange:
        row = await conn.fetchrow(
            "SELECT id, offering_type FROM instruments WHERE id = $1 AND ticker = $2",
            action.instrument_id,
            ticker,
        )
        if not row:
            raise ValueError(f"instrument_id {action.instrument_id} not found for ticker {ticker}")

        offering_type = OfferingType(str(row["offering_type"]))
        base_updates = self._base_update_payload(action.base.model_dump(exclude_none=True))
        detail_updates = self._sanitize_details(offering_type, action.details)

        if dry_run:
            return AppliedChange(
                action=action.action.value,
                instrument_id=action.instrument_id,
                result="would_update",
                details={"base_fields": sorted(base_updates.keys()), "detail_fields": sorted(detail_updates.keys())},
            )

        if base_updates:
            set_parts = []
            values = []
            for idx, (key, value) in enumerate(base_updates.items(), start=1):
                set_parts.append(f"{key} = ${idx}")
                values.append(value)
            values.extend([action.instrument_id, ticker])
            query = (
                f"UPDATE instruments SET {', '.join(set_parts)}, updated_at = NOW() "
                f"WHERE id = ${len(values)-1} AND ticker = ${len(values)}"
            )
            await conn.execute(query, *values)

        if detail_updates:
            await self._upsert_details(conn, offering_type, action.instrument_id, detail_updates, insert_mode=False)

        return AppliedChange(
            action=action.action.value,
            instrument_id=action.instrument_id,
            result="updated",
            details={"offering_type": offering_type.value},
        )

    async def _handle_transition(
        self,
        conn,
        ticker: str,
        action: TransitionInstrumentAction,
        dry_run: bool,
    ) -> AppliedChange:
        exists = await conn.fetchval(
            "SELECT 1 FROM instruments WHERE id = $1 AND ticker = $2",
            action.instrument_id,
            ticker,
        )
        if not exists:
            raise ValueError(f"instrument_id {action.instrument_id} not found for ticker {ticker}")

        if dry_run:
            return AppliedChange(
                action=action.action.value,
                instrument_id=action.instrument_id,
                result="would_transition",
                details={"new_reg_status": action.new_reg_status},
            )

        await conn.execute(
            """
            UPDATE instruments
            SET reg_status = $1,
                last_update_date = COALESCE($2, CURRENT_DATE),
                updated_at = NOW()
            WHERE id = $3 AND ticker = $4
            """,
            action.new_reg_status,
            action.transition_date,
            action.instrument_id,
            ticker,
        )
        return AppliedChange(
            action=action.action.value,
            instrument_id=action.instrument_id,
            result="transitioned",
            details={"new_reg_status": action.new_reg_status},
        )

    async def _upsert_details(
        self,
        conn,
        offering_type: OfferingType,
        instrument_id: UUID,
        detail_payload: dict[str, Any],
        insert_mode: bool,
    ) -> None:
        if not detail_payload:
            return
        table = DETAIL_TABLE_BY_TYPE[offering_type]
        if insert_mode:
            columns = ["instrument_id", *detail_payload.keys()]
            placeholders = [f"${idx}" for idx in range(1, len(columns) + 1)]
            values = [instrument_id, *detail_payload.values()]
            await conn.execute(
                f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(placeholders)})",
                *values,
            )
            return

        # Ensure row exists before update.
        exists = await conn.fetchval(
            f"SELECT 1 FROM {table} WHERE instrument_id = $1",
            instrument_id,
        )
        if not exists:
            await conn.execute(
                f"INSERT INTO {table} (instrument_id) VALUES ($1)",
                instrument_id,
            )

        set_parts = []
        values = []
        for idx, (key, value) in enumerate(detail_payload.items(), start=1):
            set_parts.append(f"{key} = ${idx}")
            values.append(value)
        values.append(instrument_id)
        await conn.execute(
            f"UPDATE {table} SET {', '.join(set_parts)} WHERE instrument_id = ${len(values)}",
            *values,
        )

    def _sanitize_details(self, offering_type: OfferingType, details: dict[str, Any]) -> dict[str, Any]:
        allowed = DETAIL_COLUMNS[offering_type]
        payload = {key: value for key, value in details.items() if key in allowed}
        rejected = sorted(set(details.keys()) - set(payload.keys()))
        if rejected:
            logger.warning(
                "agent_detail_fields_rejected",
                offering_type=offering_type.value,
                rejected_fields=rejected,
            )
        return payload

    def _base_update_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "security_name",
            "card_color",
            "reg_status",
            "edgar_url",
            "file_number",
            "last_update_date",
        }
        normalized = {}
        for key, value in payload.items():
            if key not in allowed:
                continue
            if key == "card_color" and value is not None:
                normalized[key] = value.value if hasattr(value, "value") else value
            else:
                normalized[key] = value
        return normalized

    async def _insert_filing_event(
        self,
        conn,
        ticker: str,
        instrument_id: UUID | None,
        req: ApplyActionsRequest,
        purpose: str,
        agent_action: str,
        raw_payload: dict[str, Any],
    ) -> None:
        file_number = None
        if instrument_id is not None:
            file_number = await conn.fetchval(
                "SELECT file_number FROM instruments WHERE id = $1",
                instrument_id,
            )
        await conn.execute(
            """
            INSERT INTO filing_events (
                id, ticker, form_type, purpose, filing_date, edgar_url,
                accession_number, file_number, agent_action, instrument_id,
                confidence, agent_model, raw_extraction, processed_at
            )
            VALUES (
                $1, $2, $3, $4, $5, $6,
                $7, $8, $9::agent_action_enum, $10,
                $11, $12, $13::jsonb, $14
            )
            ON CONFLICT (accession_number) DO NOTHING
            """,
            uuid4(),
            ticker,
            req.batch.form_type,
            purpose[:255],
            req.batch.filing_date,
            req.batch.filing_url,
            req.batch.accession_number,
            file_number,
            agent_action,
            instrument_id,
            max((getattr(item, "confidence", 0) for item in req.batch.actions), default=0),
            req.batch.agent_model or "agent-v2",
            json.dumps(raw_payload),
            datetime.utcnow(),
        )
