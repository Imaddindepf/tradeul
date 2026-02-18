"""
Trigger Handler - FastAPI REST endpoints for trigger management.

Endpoints:
  POST   /api/triggers                    -> Create a new trigger
  GET    /api/triggers                    -> List triggers for a user
  PUT    /api/triggers/{trigger_id}       -> Update an existing trigger
  DELETE /api/triggers/{trigger_id}       -> Delete a trigger
  POST   /api/triggers/{trigger_id}/toggle -> Enable / disable a trigger
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from triggers.engine import TriggerEngine
from triggers.models import ActionType, TriggerConditions

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/triggers", tags=["triggers"])

# ── Module-level engine reference (set during app startup) ───────

_engine: Optional[TriggerEngine] = None


def set_engine(engine: TriggerEngine) -> None:
    """Bind the trigger engine instance to this handler module."""
    global _engine
    _engine = engine


def _get_engine() -> TriggerEngine:
    if _engine is None:
        raise HTTPException(
            status_code=503,
            detail="Trigger engine is not initialised yet.",
        )
    return _engine


# ── Request / Response models ────────────────────────────────────


class CreateTriggerRequest(BaseModel):
    user_id: str = Field(..., description="Owner user ID")
    name: str = Field(..., min_length=1, max_length=256, description="Trigger name")
    conditions: TriggerConditions = Field(default_factory=TriggerConditions)

    action_type: ActionType = Field(..., description="Action type: workflow or alert")
    workflow_id: Optional[str] = Field(None, description="Workflow UUID (required for workflow type)")
    message_template: Optional[str] = Field(None, description="Alert message template")

    cooldown_seconds: int = Field(300, ge=0, description="Cooldown in seconds")
    enabled: bool = Field(True, description="Whether the trigger is initially enabled")


class UpdateTriggerRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=256)
    conditions: Optional[TriggerConditions] = None
    action_type: Optional[ActionType] = None
    workflow_id: Optional[str] = None
    message_template: Optional[str] = None
    cooldown_seconds: Optional[int] = Field(None, ge=0)
    enabled: Optional[bool] = None


class TriggerResponse(BaseModel):
    id: str
    user_id: str
    name: str
    enabled: bool
    conditions: dict[str, Any]
    action: dict[str, Any]
    cooldown_seconds: int
    last_triggered: Optional[float]


class TriggerListResponse(BaseModel):
    triggers: list[TriggerResponse]
    count: int


# ── Helpers ──────────────────────────────────────────────────────


def _build_trigger_dict(req: CreateTriggerRequest, trigger_id: str | None = None) -> dict[str, Any]:
    """Build a raw trigger config dict from a create/update request."""
    return {
        "id": trigger_id or uuid.uuid4().hex,
        "user_id": req.user_id,
        "name": req.name,
        "enabled": req.enabled,
        "conditions": req.conditions.model_dump(),
        "action": {
            "type": req.action_type.value,
            "workflow_id": req.workflow_id,
            "message_template": req.message_template,
        },
        "cooldown_seconds": req.cooldown_seconds,
        "last_triggered": None,
    }


def _trigger_to_response(cfg: Any) -> TriggerResponse:
    """Convert a TriggerConfig (or dict) into a TriggerResponse."""
    data = cfg.model_dump() if hasattr(cfg, "model_dump") else dict(cfg)
    action = data.get("action", {})
    conditions = data.get("conditions", {})
    return TriggerResponse(
        id=data["id"],
        user_id=data["user_id"],
        name=data["name"],
        enabled=data["enabled"],
        conditions=conditions if isinstance(conditions, dict) else conditions.model_dump(),
        action=action if isinstance(action, dict) else action.model_dump(),
        cooldown_seconds=data["cooldown_seconds"],
        last_triggered=data.get("last_triggered"),
    )


# ── Endpoints ────────────────────────────────────────────────────


@router.post("", response_model=TriggerResponse, status_code=201)
async def create_trigger(request: CreateTriggerRequest) -> TriggerResponse:
    """Create a new reactive trigger for a user."""
    engine = _get_engine()
    trigger_dict = _build_trigger_dict(request)

    try:
        config = await engine.register_trigger(request.user_id, trigger_dict)
    except Exception as exc:
        logger.error("Failed to create trigger: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to create trigger: {exc}")

    return _trigger_to_response(config)


@router.get("", response_model=TriggerListResponse)
async def list_triggers(
    user_id: str = Query(..., description="User ID to list triggers for"),
) -> TriggerListResponse:
    """List all triggers belonging to a user."""
    engine = _get_engine()

    # Fetch from Redis (source of truth, includes disabled triggers)
    redis_triggers = await engine.get_all_user_triggers_from_redis(user_id)
    triggers: dict[str, TriggerResponse] = {}

    for tid, data in redis_triggers.items():
        triggers[tid] = _trigger_to_response(data)

    # Overlay in-memory cache (may have fresher last_triggered)
    for tid, cfg in engine.get_user_triggers(user_id).items():
        triggers[tid] = _trigger_to_response(cfg)

    items = list(triggers.values())
    return TriggerListResponse(triggers=items, count=len(items))


@router.put("/{trigger_id}", response_model=TriggerResponse)
async def update_trigger(
    trigger_id: str,
    request: UpdateTriggerRequest,
    user_id: str = Query(..., description="User ID"),
) -> TriggerResponse:
    """Update an existing trigger."""
    engine = _get_engine()

    # Load current trigger from Redis
    import orjson
    r = await engine._get_redis()
    key = f"triggers:active:{user_id}"
    raw = await r.hget(key, trigger_id)

    if raw is None:
        raise HTTPException(status_code=404, detail="Trigger not found")

    current = orjson.loads(raw)

    # Apply updates
    updates = request.model_dump(exclude_none=True)

    if "name" in updates:
        current["name"] = updates["name"]
    if "enabled" in updates:
        current["enabled"] = updates["enabled"]
    if "cooldown_seconds" in updates:
        current["cooldown_seconds"] = updates["cooldown_seconds"]
    if "conditions" in updates:
        current["conditions"] = updates["conditions"].model_dump() if hasattr(updates["conditions"], "model_dump") else updates["conditions"]
    if "action_type" in updates or "workflow_id" in updates or "message_template" in updates:
        action = current.get("action", {})
        if "action_type" in updates:
            action["type"] = updates["action_type"]
        if "workflow_id" in updates:
            action["workflow_id"] = updates["workflow_id"]
        if "message_template" in updates:
            action["message_template"] = updates["message_template"]
        current["action"] = action

    try:
        config = await engine.register_trigger(user_id, current)
    except Exception as exc:
        logger.error("Failed to update trigger %s: %s", trigger_id, exc)
        raise HTTPException(status_code=500, detail=f"Failed to update trigger: {exc}")

    return _trigger_to_response(config)


@router.delete("/{trigger_id}", status_code=204)
async def delete_trigger(
    trigger_id: str,
    user_id: str = Query(..., description="User ID"),
) -> None:
    """Delete a trigger."""
    engine = _get_engine()
    removed = await engine.unregister_trigger(user_id, trigger_id)

    if not removed:
        raise HTTPException(status_code=404, detail="Trigger not found")


@router.post("/{trigger_id}/toggle", response_model=TriggerResponse)
async def toggle_trigger(
    trigger_id: str,
    user_id: str = Query(..., description="User ID"),
) -> TriggerResponse:
    """Toggle a trigger's enabled/disabled state."""
    engine = _get_engine()

    import orjson
    r = await engine._get_redis()
    key = f"triggers:active:{user_id}"
    raw = await r.hget(key, trigger_id)

    if raw is None:
        raise HTTPException(status_code=404, detail="Trigger not found")

    current = orjson.loads(raw)
    current["enabled"] = not current.get("enabled", True)

    try:
        config = await engine.register_trigger(user_id, current)
    except Exception as exc:
        logger.error("Failed to toggle trigger %s: %s", trigger_id, exc)
        raise HTTPException(status_code=500, detail=f"Failed to toggle trigger: {exc}")

    return _trigger_to_response(config)
