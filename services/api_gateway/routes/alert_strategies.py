"""
Alert Strategies Router - CRUD for user alert strategies (Trade Ideas style)
"""

import json
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Depends
import structlog
from auth import get_current_user, AuthenticatedUser

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/alert-strategies", tags=["alert-strategies"])

class StrategyCreate(BaseModel):
    name: str = Field(..., max_length=100)
    description: Optional[str] = None
    category: str = Field("custom", max_length=30)
    event_types: List[str] = Field(default_factory=list)
    filters: Dict[str, Any] = Field(default_factory=dict)
    is_favorite: bool = False

class StrategyUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    category: Optional[str] = Field(None, max_length=30)
    event_types: Optional[List[str]] = None
    filters: Optional[Dict[str, Any]] = None
    is_favorite: Optional[bool] = None

class StrategyResponse(BaseModel):
    id: int
    userId: str
    name: str
    description: Optional[str]
    category: str
    eventTypes: List[str]
    filters: Dict[str, Any]
    isFavorite: bool
    useCount: int
    lastUsedAt: Optional[str]
    createdAt: str
    updatedAt: str

class StrategyListResponse(BaseModel):
    strategies: List[StrategyResponse]
    total: int

_timescale_client = None

def set_timescale_client(client):
    global _timescale_client
    _timescale_client = client

def get_timescale():
    if _timescale_client is None:
        raise HTTPException(status_code=503, detail="Database not available")
    return _timescale_client

def parse_jsonb(val):
    if isinstance(val, str):
        return json.loads(val)
    return val

COLS = "id, user_id, name, description, category, event_types, filters, is_favorite, use_count, last_used_at, created_at, updated_at"

def row_to_resp(row) -> StrategyResponse:
    return StrategyResponse(
        id=row["id"], userId=row["user_id"], name=row["name"],
        description=row["description"], category=row["category"] or "custom",
        eventTypes=parse_jsonb(row["event_types"]) if row["event_types"] else [],
        filters=parse_jsonb(row["filters"]) if row["filters"] else {},
        isFavorite=row["is_favorite"], useCount=row["use_count"],
        lastUsedAt=row["last_used_at"].isoformat() if row["last_used_at"] else None,
        createdAt=row["created_at"].isoformat(), updatedAt=row["updated_at"].isoformat(),
    )

@router.get("", response_model=StrategyListResponse)
async def list_strategies(user: AuthenticatedUser = Depends(get_current_user), db=Depends(get_timescale)):
    try:
        rows = await db.fetch(
            f"SELECT {COLS} FROM user_alert_strategies WHERE user_id = $1 ORDER BY is_favorite DESC, last_used_at DESC NULLS LAST, created_at DESC",
            user.id)
        items = [row_to_resp(r) for r in rows]
        return StrategyListResponse(strategies=items, total=len(items))
    except Exception as e:
        logger.error("list_strategies_error", user_id=user.id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{sid}", response_model=StrategyResponse)
async def get_strategy(sid: int, user: AuthenticatedUser = Depends(get_current_user), db=Depends(get_timescale)):
    try:
        row = await db.fetchrow(f"SELECT {COLS} FROM user_alert_strategies WHERE id = $1 AND user_id = $2", sid, user.id)
        if not row: raise HTTPException(status_code=404, detail="Not found")
        return row_to_resp(row)
    except HTTPException: raise
    except Exception as e:
        logger.error("get_strategy_error", sid=sid, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@router.post("", response_model=StrategyResponse, status_code=201)
async def create_strategy(data: StrategyCreate, user: AuthenticatedUser = Depends(get_current_user), db=Depends(get_timescale)):
    try:
        dup = await db.fetchrow("SELECT id FROM user_alert_strategies WHERE user_id = $1 AND name = $2", user.id, data.name.strip())
        if dup: raise HTTPException(status_code=409, detail="Name already exists")
        row = await db.fetchrow(
            f"INSERT INTO user_alert_strategies (user_id, name, description, category, event_types, filters, is_favorite) VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7) RETURNING {COLS}",
            user.id, data.name.strip(), data.description, data.category or "custom",
            json.dumps(data.event_types), json.dumps(data.filters), data.is_favorite)
        logger.info("strategy_created", user_id=user.id, name=data.name)
        return row_to_resp(row)
    except HTTPException: raise
    except Exception as e:
        logger.error("create_strategy_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{sid}", response_model=StrategyResponse)
async def update_strategy(sid: int, data: StrategyUpdate, user: AuthenticatedUser = Depends(get_current_user), db=Depends(get_timescale)):
    try:
        existing = await db.fetchrow("SELECT id FROM user_alert_strategies WHERE id = $1 AND user_id = $2", sid, user.id)
        if not existing: raise HTTPException(status_code=404, detail="Not found")
        if data.name is not None:
            dup = await db.fetchrow("SELECT id FROM user_alert_strategies WHERE user_id = $1 AND name = $2 AND id != $3", user.id, data.name.strip(), sid)
            if dup: raise HTTPException(status_code=409, detail="Name already exists")
        sets = ["updated_at = NOW()"]
        params = []
        idx = 1
        if data.name is not None: sets.append(f"name = ${idx}"); params.append(data.name.strip()); idx += 1
        if data.description is not None: sets.append(f"description = ${idx}"); params.append(data.description); idx += 1
        if data.category is not None: sets.append(f"category = ${idx}"); params.append(data.category); idx += 1
        if data.event_types is not None: sets.append(f"event_types = ${idx}::jsonb"); params.append(json.dumps(data.event_types)); idx += 1
        if data.filters is not None: sets.append(f"filters = ${idx}::jsonb"); params.append(json.dumps(data.filters)); idx += 1
        if data.is_favorite is not None: sets.append(f"is_favorite = ${idx}"); params.append(data.is_favorite); idx += 1
        params.extend([sid, user.id])
        row = await db.fetchrow(f"UPDATE user_alert_strategies SET {', '.join(sets)} WHERE id = ${idx} AND user_id = ${idx + 1} RETURNING {COLS}", *params)
        logger.info("strategy_updated", user_id=user.id, sid=sid)
        return row_to_resp(row)
    except HTTPException: raise
    except Exception as e:
        logger.error("update_strategy_error", sid=sid, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{sid}", status_code=204)
async def delete_strategy(sid: int, user: AuthenticatedUser = Depends(get_current_user), db=Depends(get_timescale)):
    try:
        result = await db.execute("DELETE FROM user_alert_strategies WHERE id = $1 AND user_id = $2", sid, user.id)
        if result == "DELETE 0": raise HTTPException(status_code=404, detail="Not found")
        logger.info("strategy_deleted", user_id=user.id, sid=sid)
    except HTTPException: raise
    except Exception as e:
        logger.error("delete_strategy_error", sid=sid, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{sid}/use", response_model=StrategyResponse)
async def use_strategy(sid: int, user: AuthenticatedUser = Depends(get_current_user), db=Depends(get_timescale)):
    try:
        row = await db.fetchrow(f"UPDATE user_alert_strategies SET use_count = use_count + 1, last_used_at = NOW(), updated_at = NOW() WHERE id = $1 AND user_id = $2 RETURNING {COLS}", sid, user.id)
        if not row: raise HTTPException(status_code=404, detail="Not found")
        return row_to_resp(row)
    except HTTPException: raise
    except Exception as e:
        logger.error("use_strategy_error", sid=sid, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{sid}/duplicate", response_model=StrategyResponse, status_code=201)
async def duplicate_strategy(sid: int, user: AuthenticatedUser = Depends(get_current_user), db=Depends(get_timescale)):
    try:
        orig = await db.fetchrow(f"SELECT {COLS} FROM user_alert_strategies WHERE id = $1 AND user_id = $2", sid, user.id)
        if not orig: raise HTTPException(status_code=404, detail="Not found")
        base = orig["name"]
        new_name = f"{base} (copy)"
        c = 1
        while True:
            d = await db.fetchrow("SELECT id FROM user_alert_strategies WHERE user_id = $1 AND name = $2", user.id, new_name)
            if not d: break
            c += 1; new_name = f"{base} (copy {c})"
        row = await db.fetchrow(
            f"INSERT INTO user_alert_strategies (user_id, name, description, category, event_types, filters, is_favorite) VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7) RETURNING {COLS}",
            user.id, new_name, orig["description"], orig["category"],
            json.dumps(parse_jsonb(orig["event_types"])), json.dumps(parse_jsonb(orig["filters"])), False)
        logger.info("strategy_duplicated", user_id=user.id, original=sid)
        return row_to_resp(row)
    except HTTPException: raise
    except Exception as e:
        logger.error("duplicate_strategy_error", sid=sid, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
