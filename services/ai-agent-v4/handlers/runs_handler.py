"""
REST API para runs y artifacts — el backend del inspector de nodo.

GET /api/runs/{run_id}                          → metadatos + índice de nodos
GET /api/runs/{run_id}/nodes/{node}/artifacts   → artifacts completos del nodo
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from auth import request_user_id
from runs.store import get_run_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.get("/{run_id}")
async def get_run(run_id: str, user_id: str = Depends(request_user_id)):
    store = get_run_store()
    run = await store.get_run(run_id, user_id=user_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/{run_id}/nodes/{node}/artifacts")
async def get_node_artifacts(
    run_id: str, node: str, user_id: str = Depends(request_user_id),
):
    store = get_run_store()
    artifacts = await store.get_artifacts(run_id, node, user_id=user_id)
    return {"run_id": run_id, "node": node, "artifacts": artifacts}
