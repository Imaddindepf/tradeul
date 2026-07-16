"""
Alerts Handler — REST endpoints for LLM-compiled alert specs.

Two-phase lifecycle: the chat compiles a DRAFT (with dry-run evidence);
these endpoints manage it afterwards.

  GET    /api/alerts                      -> list specs for a user
  GET    /api/alerts/{spec_id}            -> full spec + dry-run
  POST   /api/alerts/{spec_id}/arm        -> arm (T0 specs register a live trigger)
  POST   /api/alerts/{spec_id}/pause      -> pause (unregisters the live trigger)
  POST   /api/alerts/{spec_id}/dry-run    -> re-run the historical preview
  GET    /api/alerts/{spec_id}/fires      -> fire history with evidence
  DELETE /api/alerts/{spec_id}            -> archive (soft delete)
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Request

from alerts.dryrun import run_dry_run
from alerts.spec import AlertSpec, AlertStatus
from alerts.store import get_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


def _store_or_503():
    store = get_store()
    if not store.available:
        raise HTTPException(status_code=503, detail="Alert store is not available")
    return store


async def _spec_or_404(spec_id: str, user_id: str) -> AlertSpec:
    spec = await _store_or_503().get_spec(spec_id, user_id)
    if spec is None:
        raise HTTPException(status_code=404, detail="Alert spec not found")
    return spec


def _trigger_engine(request: Request):
    engine = getattr(request.app.state, "trigger_engine", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="Trigger engine is not initialised")
    return engine


# ── Endpoints ────────────────────────────────────────────────────

@router.get("")
async def list_alerts(
    user_id: str = Query("default"),
    include_archived: bool = Query(False),
) -> dict[str, Any]:
    specs = await _store_or_503().list_specs(user_id, include_archived=include_archived)
    return {"alerts": specs, "count": len(specs)}


@router.get("/{spec_id}")
async def get_alert(spec_id: str, user_id: str = Query("default")) -> dict[str, Any]:
    spec = await _spec_or_404(spec_id, user_id)
    return spec.model_dump(mode="json")


@router.post("/{spec_id}/arm")
async def arm_alert(
    spec_id: str, request: Request, user_id: str = Query("default"),
) -> dict[str, Any]:
    """Arm a draft/paused spec.

    T0 specs (single live event step) register a trigger on the reactive
    engine and fire in real time from this moment. Sequence/day-context
    specs are marked armed but live evaluation lands with the CEP runtime
    (phase 3) — the response is explicit about which case applies.
    """
    store = _store_or_503()
    spec = await _spec_or_404(spec_id, user_id)

    live = False
    kind = "preview_only"
    trigger_id: Optional[str] = spec.trigger_id
    if spec.is_live_armable():
        engine = _trigger_engine(request)
        try:
            trigger_cfg = spec.to_trigger_config()
            config = await engine.register_trigger(user_id, trigger_cfg)
            trigger_id = config.id
            live = True
            if spec.is_t0_armable():
                kind = "event_match"
            elif spec.is_sequence_armable():
                kind = "sequence"
            elif spec.is_membership_armable():
                kind = "membership"
        except Exception as exc:
            logger.error("arm_alert: trigger registration failed for %s: %s", spec_id, exc)
            raise HTTPException(status_code=500, detail=f"Trigger registration failed: {exc}")

    updated = await store.set_status(spec_id, user_id, AlertStatus.ARMED, trigger_id=trigger_id)
    if updated is None:
        raise HTTPException(status_code=500, detail="Failed to persist armed status")

    notes = {
        "event_match": "Live on the reactive engine — fires stream to your alert feed.",
        "sequence": "Live CEP sequence armed — fires when the full A→B path completes.",
        "membership": "Live membership watch armed — fires on scanner enter/exit.",
        "preview_only": (
            "Armed for bookkeeping only: this spec needs day-level context that "
            "isn't known until the session ends. Use dry-run for evidence; live "
            "evaluation for day_conditions lands later."
        ),
    }
    return {
        "spec_id": spec_id,
        "status": "armed",
        "live": live,
        "kind": kind,
        "trigger_id": trigger_id,
        "note": notes[kind],
    }


@router.post("/{spec_id}/pause")
async def pause_alert(
    spec_id: str, request: Request, user_id: str = Query("default"),
) -> dict[str, Any]:
    store = _store_or_503()
    spec = await _spec_or_404(spec_id, user_id)

    if spec.trigger_id:
        try:
            await _trigger_engine(request).unregister_trigger(user_id, spec.trigger_id)
        except Exception as exc:
            logger.warning("pause_alert: trigger unregister failed for %s: %s", spec_id, exc)

    updated = await store.set_status(spec_id, user_id, AlertStatus.PAUSED)
    if updated is None:
        raise HTTPException(status_code=500, detail="Failed to persist paused status")
    return {"spec_id": spec_id, "status": "paused"}


@router.post("/{spec_id}/dry-run")
async def rerun_dry_run(
    spec_id: str,
    user_id: str = Query("default"),
    days: int = Query(5, ge=1, le=10),
) -> dict[str, Any]:
    store = _store_or_503()
    spec = await _spec_or_404(spec_id, user_id)

    result = await run_dry_run(spec, days=days)
    spec.dry_run = {
        "total_fires": result["total_fires"],
        "days_scanned": result["days_scanned"],
        "unique_symbols": result["unique_symbols"][:30],
    }
    await store.save_spec(spec)
    return result


@router.get("/{spec_id}/fires")
async def list_alert_fires(
    spec_id: str,
    user_id: str = Query("default"),
    limit: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    await _spec_or_404(spec_id, user_id)
    fires = await _store_or_503().list_fires(spec_id, user_id, limit=limit)
    return {"spec_id": spec_id, "fires": fires, "count": len(fires)}


@router.delete("/{spec_id}", status_code=200)
async def archive_alert(
    spec_id: str, request: Request, user_id: str = Query("default"),
) -> dict[str, Any]:
    store = _store_or_503()
    spec = await _spec_or_404(spec_id, user_id)

    if spec.trigger_id:
        try:
            await _trigger_engine(request).unregister_trigger(user_id, spec.trigger_id)
        except Exception as exc:
            logger.warning("archive_alert: trigger unregister failed for %s: %s", spec_id, exc)

    updated = await store.set_status(spec_id, user_id, AlertStatus.ARCHIVED)
    if updated is None:
        raise HTTPException(status_code=500, detail="Failed to archive spec")
    return {"spec_id": spec_id, "status": "archived"}
