"""
Review endpoints for ambiguous dilution v2 filings.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

SERVICE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.append(str(SERVICE_ROOT))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))
if "/app" not in sys.path:
    sys.path.append("/app")

from models.agent_actions_v2 import ApplyActionsRequest, ApplyActionsResponse
from routers.security import require_dilution_admin_email
from services.core.agent_action_service_v2 import AgentActionServiceV2
from shared.config.settings import settings
from shared.utils.logger import get_logger
from shared.utils.timescale_client import TimescaleClient

logger = get_logger(__name__)

router = APIRouter(
    prefix="/api/dilution-v2/review",
    tags=["dilution-v2-review"],
    dependencies=[Depends(require_dilution_admin_email)],
)

AMBIGUOUS_STREAM_KEY = "stream:dilution:v2:ambiguous"
FILINGS_STREAM_KEY = "stream:dilution:v2:filings"
REVIEWED_STREAM_KEY = "stream:dilution:v2:reviewed"


class AmbiguousItem(BaseModel):
    message_id: str
    ticker: str | None = None
    accession_number: str | None = None
    form_type: str | None = None
    filed_at: str | None = None
    confidence: str | None = None
    review_reason: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class AmbiguousListResponse(BaseModel):
    total: int
    items: list[AmbiguousItem]


class ReviewedItem(BaseModel):
    message_id: str
    accession_number: str | None = None
    decision: str | None = None
    notes: str | None = None
    source_message_id: str | None = None
    reviewed_at: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ReviewedListResponse(BaseModel):
    total: int
    items: list[ReviewedItem]


class ReviewMetricsResponse(BaseModel):
    generated_at: str
    ambiguous_queue_depth: int
    filings_stream_depth: int
    reviewed_stream_depth: int
    reviewed_last_24h: int
    decisions_last_24h: dict[str, int]


class RequeueAmbiguousRequest(BaseModel):
    accession_number: str
    reason: str = "manual_requeue"


class ResolveAmbiguousRequest(BaseModel):
    accession_number: str
    resolution: Literal["ignore", "accepted_manual_apply"]
    notes: str | None = None


@router.get("/ambiguous", response_model=AmbiguousListResponse)
async def list_ambiguous_filings(
    limit: int = Query(default=50, ge=1, le=200),
    ticker: str | None = Query(default=None),
):
    redis_client = await _build_redis_client()
    try:
        rows = await redis_client.xrevrange(AMBIGUOUS_STREAM_KEY, count=max(limit * 3, limit))
        filtered: list[AmbiguousItem] = []
        ticker_norm = ticker.upper().strip() if ticker else None

        for message_id, fields in rows:
            payload = _decode_payload(fields)
            payload_ticker = (payload.get("ticker") or "").upper().strip()
            if ticker_norm and payload_ticker != ticker_norm:
                continue
            filtered.append(
                AmbiguousItem(
                    message_id=message_id,
                    ticker=payload.get("ticker"),
                    accession_number=payload.get("accession_number"),
                    form_type=payload.get("form_type"),
                    filed_at=payload.get("filed_at"),
                    confidence=payload.get("confidence"),
                    review_reason=payload.get("review_reason"),
                    payload=payload,
                )
            )
            if len(filtered) >= limit:
                break

        return AmbiguousListResponse(total=len(filtered), items=filtered)
    except Exception as exc:
        logger.error("ambiguous_list_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to list ambiguous filings") from exc
    finally:
        await redis_client.close()


@router.get("/reviewed", response_model=ReviewedListResponse)
async def list_reviewed_filings(
    limit: int = Query(default=50, ge=1, le=200),
    ticker: str | None = Query(default=None),
    decision: str | None = Query(default=None),
):
    redis_client = await _build_redis_client()
    try:
        rows = await redis_client.xrevrange(REVIEWED_STREAM_KEY, count=max(limit * 3, limit))
        filtered: list[ReviewedItem] = []
        ticker_norm = ticker.upper().strip() if ticker else None
        decision_norm = decision.strip().lower() if decision else None

        for message_id, fields in rows:
            audit_payload = _decode_payload(fields)
            inner_payload = audit_payload.get("payload") if isinstance(audit_payload.get("payload"), dict) else {}
            payload_ticker = (inner_payload.get("ticker") or "").upper().strip()
            payload_decision = str(audit_payload.get("decision") or "").strip().lower()

            if ticker_norm and payload_ticker != ticker_norm:
                continue
            if decision_norm and payload_decision != decision_norm:
                continue

            filtered.append(
                ReviewedItem(
                    message_id=message_id,
                    accession_number=audit_payload.get("accession_number"),
                    decision=audit_payload.get("decision"),
                    notes=audit_payload.get("notes"),
                    source_message_id=audit_payload.get("source_message_id"),
                    reviewed_at=audit_payload.get("reviewed_at"),
                    payload=inner_payload if isinstance(inner_payload, dict) else {},
                )
            )
            if len(filtered) >= limit:
                break

        return ReviewedListResponse(total=len(filtered), items=filtered)
    except Exception as exc:
        logger.error("reviewed_list_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to list reviewed filings") from exc
    finally:
        await redis_client.close()


@router.get("/metrics", response_model=ReviewMetricsResponse)
async def get_review_metrics():
    redis_client = await _build_redis_client()
    try:
        ambiguous_depth = int(await redis_client.xlen(AMBIGUOUS_STREAM_KEY))
        filings_depth = int(await redis_client.xlen(FILINGS_STREAM_KEY))
        reviewed_depth = int(await redis_client.xlen(REVIEWED_STREAM_KEY))

        rows = await redis_client.xrevrange(REVIEWED_STREAM_KEY, count=2000)
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=24)
        decisions: dict[str, int] = {}
        reviewed_last_24h = 0

        for _, fields in rows:
            payload = _decode_payload(fields)
            reviewed_at_raw = payload.get("reviewed_at")
            reviewed_at = _parse_iso_datetime(reviewed_at_raw)
            if not reviewed_at or reviewed_at < cutoff:
                continue
            reviewed_last_24h += 1
            key = str(payload.get("decision") or "unknown").strip().lower() or "unknown"
            decisions[key] = decisions.get(key, 0) + 1

        return ReviewMetricsResponse(
            generated_at=now.isoformat(),
            ambiguous_queue_depth=ambiguous_depth,
            filings_stream_depth=filings_depth,
            reviewed_stream_depth=reviewed_depth,
            reviewed_last_24h=reviewed_last_24h,
            decisions_last_24h=decisions,
        )
    except Exception as exc:
        logger.error("review_metrics_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to load review metrics") from exc
    finally:
        await redis_client.close()


@router.post("/ambiguous/requeue")
async def requeue_ambiguous_filing(request: RequeueAmbiguousRequest):
    redis_client = await _build_redis_client()
    try:
        message_id, payload = await _find_ambiguous_by_accession(
            redis_client,
            request.accession_number,
        )
        if payload is None:
            raise HTTPException(
                status_code=404,
                detail=f"Ambiguous filing {request.accession_number} not found",
            )

        republished_payload = {
            **payload,
            "requeued_at": datetime.utcnow().isoformat(),
            "requeue_reason": request.reason,
            "source": "ambiguous_review_requeue",
        }
        await redis_client.xadd(
            FILINGS_STREAM_KEY,
            {"data": json.dumps(republished_payload)},
            maxlen=5000,
            approximate=True,
        )
        await _publish_review_audit(
            redis_client=redis_client,
            accession_number=request.accession_number,
            decision="requeued",
            notes=request.reason,
            source_message_id=message_id,
            payload=republished_payload,
        )
        return {
            "status": "requeued",
            "accession_number": request.accession_number,
            "source_message_id": message_id,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("ambiguous_requeue_failed", error=str(exc), accession_number=request.accession_number)
        raise HTTPException(status_code=500, detail="Failed to requeue ambiguous filing") from exc
    finally:
        await redis_client.close()


@router.post("/ambiguous/resolve")
async def resolve_ambiguous_filing(request: ResolveAmbiguousRequest):
    redis_client = await _build_redis_client()
    try:
        message_id, payload = await _find_ambiguous_by_accession(
            redis_client,
            request.accession_number,
        )
        if payload is None:
            raise HTTPException(
                status_code=404,
                detail=f"Ambiguous filing {request.accession_number} not found",
            )
        await _publish_review_audit(
            redis_client=redis_client,
            accession_number=request.accession_number,
            decision=request.resolution,
            notes=request.notes,
            source_message_id=message_id,
            payload=payload,
        )
        return {
            "status": "resolved",
            "accession_number": request.accession_number,
            "resolution": request.resolution,
            "source_message_id": message_id,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("ambiguous_resolve_failed", error=str(exc), accession_number=request.accession_number)
        raise HTTPException(status_code=500, detail="Failed to resolve ambiguous filing") from exc
    finally:
        await redis_client.close()


@router.post("/ambiguous/apply", response_model=ApplyActionsResponse)
async def apply_ambiguous_actions(request: ApplyActionsRequest):
    db = TimescaleClient()
    redis_client = await _build_redis_client()
    try:
        await db.connect(min_size=1, max_size=2)
        service = AgentActionServiceV2(db)
        response = await service.apply(request)
        await _publish_review_audit(
            redis_client=redis_client,
            accession_number=request.batch.accession_number,
            decision="manual_apply_dry_run" if request.dry_run else "manual_apply",
            notes=request.batch.agent_summary,
            source_message_id=None,
            payload=request.model_dump(mode="json"),
        )
        return response
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error(
            "ambiguous_apply_failed",
            error=str(exc),
            accession_number=request.batch.accession_number,
        )
        raise HTTPException(status_code=500, detail="Failed to apply ambiguous actions") from exc
    finally:
        await db.disconnect()
        await redis_client.close()


async def _find_ambiguous_by_accession(redis_client, accession_number: str) -> tuple[str | None, dict[str, Any] | None]:
    accession_norm = accession_number.strip()
    rows = await redis_client.xrevrange(AMBIGUOUS_STREAM_KEY, count=2000)
    for message_id, fields in rows:
        payload = _decode_payload(fields)
        if (payload.get("accession_number") or "").strip() == accession_norm:
            return message_id, payload
    return None, None


async def _publish_review_audit(
    redis_client,
    accession_number: str,
    decision: str,
    notes: str | None,
    source_message_id: str | None,
    payload: dict[str, Any],
) -> None:
    audit_payload = {
        "accession_number": accession_number,
        "decision": decision,
        "notes": notes,
        "source_message_id": source_message_id,
        "reviewed_at": datetime.utcnow().isoformat(),
        "payload": payload,
    }
    await redis_client.xadd(
        REVIEWED_STREAM_KEY,
        {"data": json.dumps(audit_payload)},
        maxlen=10000,
        approximate=True,
    )


def _decode_payload(fields: dict[str, Any]) -> dict[str, Any]:
    raw = fields.get("data")
    if not raw:
        return {}
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


async def _build_redis_client():
    if settings.redis_password:
        redis_url = (
            f"redis://:{settings.redis_password}@"
            f"{settings.redis_host}:{settings.redis_port}/{settings.redis_db}"
        )
    else:
        redis_url = f"redis://{settings.redis_host}:{settings.redis_port}/{settings.redis_db}"
    return await aioredis.from_url(redis_url, encoding="utf-8", decode_responses=True)
