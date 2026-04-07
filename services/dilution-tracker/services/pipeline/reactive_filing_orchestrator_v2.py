"""
Reactive orchestrator for dilution v2 filing events.

Consumes `stream:dilution:v2:filings`, resolves safe agent actions, and applies
them transactionally using the v2 action service.
"""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import redis.asyncio as aioredis

SERVICE_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.append(str(SERVICE_ROOT))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))
if "/app" not in sys.path:
    sys.path.append("/app")

from models.agent_actions_v2 import (  # noqa: E402
    ActionKind,
    ApplyActionsRequest,
    FilingActionBatch,
    LogOnlyAction,
    TransitionInstrumentAction,
    UpdateInstrumentAction,
)
from repositories.instrument_context_repository import InstrumentContextRepository  # noqa: E402
from services.core.agent_action_service_v2 import AgentActionServiceV2  # noqa: E402
from shared.config.settings import settings  # noqa: E402
from shared.utils.logger import get_logger  # noqa: E402
from shared.utils.timescale_client import TimescaleClient  # noqa: E402

logger = get_logger(__name__)


@dataclass
class OrchestratorDecision:
    actions: list[Any]
    reason: str
    confidence: Decimal
    ambiguous: bool = False


class RuleBasedDecisionEngineV2:
    """
    Conservative decision engine.

    It only auto-applies deterministic transitions/updates and sends uncertain
    cases to the ambiguous queue for human/agent review.
    """

    EFFECT_FORMS = {"EFFECT"}
    WITHDRAW_FORMS = {"RW"}
    UPDATE_FORMS = {"424B5", "424B3", "424B2", "8-K"}

    def decide(self, filing: dict[str, Any], context) -> OrchestratorDecision:
        form_type = (filing.get("form_type") or "").upper().strip()
        accession = filing.get("accession_number", "unknown-accession")

        if form_type in self.EFFECT_FORMS:
            candidates = [
                item
                for item in context.instruments
                if item.reg_status in {"Pending Effect", "Filed", "In Progress"}
            ]
            if not candidates:
                return OrchestratorDecision(
                    actions=[
                        LogOnlyAction(
                            action=ActionKind.LOG,
                            reason="EFFECT filing without pending instruments",
                            confidence=Decimal("0.95"),
                            evidence=[f"accession={accession}", "no_pending_instruments"],
                        )
                    ],
                    reason="no pending instruments for EFFECT",
                    confidence=Decimal("0.95"),
                )
            actions = [
                TransitionInstrumentAction(
                    action=ActionKind.TRANSITION,
                    instrument_id=item.id,
                    new_reg_status="Registered",
                    transition_date=_safe_filing_date(filing.get("filed_at")),
                    reason=f"EFFECT filing marks {item.offering_type.value} as Registered",
                    confidence=Decimal("0.88"),
                    evidence=[f"accession={accession}", f"instrument_id={item.id}"],
                )
                for item in candidates
            ]
            return OrchestratorDecision(
                actions=actions,
                reason=f"transitioned {len(actions)} instrument(s) to Registered",
                confidence=Decimal("0.88"),
            )

        if form_type in self.WITHDRAW_FORMS:
            candidates = [
                item
                for item in context.instruments
                if item.reg_status not in {"Withdrawn", "Terminated", "Expired"}
            ]
            if len(candidates) != 1:
                return OrchestratorDecision(
                    actions=[
                        LogOnlyAction(
                            action=ActionKind.LOG,
                            reason="RW filing requires manual instrument selection",
                            confidence=Decimal("0.50"),
                            evidence=[
                                f"accession={accession}",
                                f"candidate_count={len(candidates)}",
                            ],
                        )
                    ],
                    reason=f"rw ambiguous with {len(candidates)} candidates",
                    confidence=Decimal("0.50"),
                    ambiguous=True,
                )
            target = candidates[0]
            return OrchestratorDecision(
                actions=[
                    TransitionInstrumentAction(
                        action=ActionKind.TRANSITION,
                        instrument_id=target.id,
                        new_reg_status="Withdrawn",
                        transition_date=_safe_filing_date(filing.get("filed_at")),
                        reason=f"RW filing withdraws {target.offering_type.value}",
                        confidence=Decimal("0.78"),
                        evidence=[f"accession={accession}", f"instrument_id={target.id}"],
                    )
                ],
                reason="single target withdrawn via RW",
                confidence=Decimal("0.78"),
            )

        if form_type in self.UPDATE_FORMS:
            active = [
                item
                for item in context.instruments
                if item.reg_status in {"Registered", "Pending Effect", "In Progress", "Active"}
            ]
            if len(active) != 1:
                return OrchestratorDecision(
                    actions=[
                        LogOnlyAction(
                            action=ActionKind.LOG,
                            reason="Non-deterministic update form; manual review needed",
                            confidence=Decimal("0.45"),
                            evidence=[
                                f"accession={accession}",
                                f"candidate_count={len(active)}",
                                f"form_type={form_type}",
                            ],
                        )
                    ],
                    reason=f"{form_type} ambiguous with {len(active)} candidates",
                    confidence=Decimal("0.45"),
                    ambiguous=True,
                )
            target = active[0]
            return OrchestratorDecision(
                actions=[
                    UpdateInstrumentAction(
                        action=ActionKind.UPDATE,
                        instrument_id=target.id,
                        base={"last_update_date": _safe_filing_date(filing.get("filed_at"))},
                        details={},
                        reason=f"{form_type} updates latest filing touchpoint",
                        confidence=Decimal("0.72"),
                        evidence=[f"accession={accession}", f"instrument_id={target.id}"],
                    )
                ],
                reason=f"updated instrument {target.id} for {form_type}",
                confidence=Decimal("0.72"),
            )

        return OrchestratorDecision(
            actions=[
                LogOnlyAction(
                    action=ActionKind.LOG,
                    reason=f"No deterministic auto-apply rule for form {form_type or 'unknown'}",
                    confidence=Decimal("0.60"),
                    evidence=[f"accession={accession}"],
                )
            ],
            reason=f"no deterministic rule for {form_type or 'unknown'}",
            confidence=Decimal("0.60"),
            ambiguous=True,
        )


class ReactiveFilingOrchestratorV2:
    DILUTION_STREAM_KEY = "stream:dilution:v2:filings"
    AMBIGUOUS_STREAM_KEY = "stream:dilution:v2:ambiguous"
    GROUP_NAME = "dilution-v2-orchestrator"
    CONSUMER_NAME = "dilution-v2-orchestrator-consumer"

    def __init__(self):
        self._running = False
        self._task: asyncio.Task | None = None
        self._redis = None
        self._db: TimescaleClient | None = None
        self._decision_engine = RuleBasedDecisionEngineV2()
        self._min_apply_confidence = Decimal(
            str(getattr(settings, "dilution_v2_min_apply_confidence", "0.70"))
        )

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._redis = await self._build_redis_client()
        self._db = TimescaleClient()
        await self._db.connect(min_size=1, max_size=5)
        await self._ensure_group()
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "reactive_filing_orchestrator_started",
            min_apply_confidence=str(self._min_apply_confidence),
        )

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._redis:
            await self._redis.close()
        if self._db:
            await self._db.disconnect()
        logger.info("reactive_filing_orchestrator_stopped")

    async def _run_loop(self) -> None:
        assert self._redis is not None
        while self._running:
            try:
                records = await self._redis.xreadgroup(
                    groupname=self.GROUP_NAME,
                    consumername=self.CONSUMER_NAME,
                    streams={self.DILUTION_STREAM_KEY: ">"},
                    count=50,
                    block=5000,
                )
                if not records:
                    continue
                for stream_name, entries in records:
                    for message_id, fields in entries:
                        try:
                            await self._handle_message(fields)
                            await self._redis.xack(stream_name, self.GROUP_NAME, message_id)
                        except Exception as exc:
                            logger.error(
                                "reactive_orchestrator_message_failed",
                                error=str(exc),
                                message_id=message_id,
                            )
                            await self._redis.xack(stream_name, self.GROUP_NAME, message_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("reactive_orchestrator_loop_error", error=str(exc))
                await asyncio.sleep(2)

    async def _handle_message(self, fields: dict[str, Any]) -> None:
        raw = fields.get("data")
        if not raw:
            return
        filing = json.loads(raw)
        ticker = (filing.get("ticker") or "").upper().strip()
        accession = (filing.get("accession_number") or "").strip()
        form_type = (filing.get("form_type") or "").strip()
        if not ticker or not accession:
            return

        if not await self._acquire_idempotency_lock(accession):
            logger.info("orchestrator_duplicate_skipped", ticker=ticker, accession_number=accession)
            return

        assert self._db is not None
        context_repo = InstrumentContextRepository(self._db)
        context = await context_repo.get_ticker_context(ticker=ticker, include_completed_offerings=True)
        if context is None:
            logger.warning("orchestrator_ticker_missing_context", ticker=ticker, accession_number=accession)
            return

        decision = self._decision_engine.decide(filing=filing, context=context)
        apply_confidence = decision.confidence >= self._min_apply_confidence and not decision.ambiguous

        if not apply_confidence:
            await self._publish_ambiguous_event(
                filing=filing,
                reason=decision.reason,
                confidence=decision.confidence,
                candidate_count=context.stats.total,
            )
            logger.info(
                "orchestrator_sent_to_ambiguous_queue",
                ticker=ticker,
                accession_number=accession,
                form_type=form_type,
                confidence=str(decision.confidence),
                reason=decision.reason,
            )
            return

        request = ApplyActionsRequest(
            dry_run=False,
            batch=FilingActionBatch(
                accession_number=accession,
                ticker=ticker,
                form_type=form_type or "UNKNOWN",
                filing_date=_safe_filing_date(filing.get("filed_at")),
                filing_url=filing.get("filing_url"),
                agent_model="rule-based-orchestrator-v2",
                agent_summary=decision.reason,
                actions=decision.actions,
            ),
        )

        action_service = AgentActionServiceV2(self._db)
        response = await action_service.apply(request)
        logger.info(
            "orchestrator_actions_applied",
            ticker=ticker,
            accession_number=accession,
            changes=len(response.changes),
            warnings=len(response.warnings),
            confidence=str(decision.confidence),
        )

    async def _publish_ambiguous_event(
        self,
        filing: dict[str, Any],
        reason: str,
        confidence: Decimal,
        candidate_count: int,
    ) -> None:
        assert self._redis is not None
        payload = {
            **filing,
            "review_reason": reason,
            "confidence": str(confidence),
            "candidate_count": candidate_count,
            "queued_at": datetime.utcnow().isoformat(),
            "queue": "dilution_v2_ambiguous",
        }
        await self._redis.xadd(
            self.AMBIGUOUS_STREAM_KEY,
            {"data": json.dumps(payload)},
            maxlen=5000,
            approximate=True,
        )

    async def _acquire_idempotency_lock(self, accession_number: str) -> bool:
        assert self._redis is not None
        key = f"dilution:v2:orchestrator:lock:{accession_number}"
        # 48h retention prevents duplicate processing during retries/replays.
        return bool(await self._redis.set(key, "1", nx=True, ex=172800))

    async def _ensure_group(self) -> None:
        assert self._redis is not None
        try:
            await self._redis.xgroup_create(
                name=self.DILUTION_STREAM_KEY,
                groupname=self.GROUP_NAME,
                id="$",
                mkstream=True,
            )
        except Exception as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def _build_redis_client(self):
        if settings.redis_password:
            redis_url = (
                f"redis://:{settings.redis_password}@"
                f"{settings.redis_host}:{settings.redis_port}/{settings.redis_db}"
            )
        else:
            redis_url = f"redis://{settings.redis_host}:{settings.redis_port}/{settings.redis_db}"
        return await aioredis.from_url(redis_url, encoding="utf-8", decode_responses=True)


def _safe_filing_date(value: Any):
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            pass
    return datetime.utcnow().date()
