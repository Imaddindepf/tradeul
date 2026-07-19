"""
REST API para runs y artifacts — el backend del inspector de nodo.

GET /api/runs/{run_id}                          → metadatos + índice de nodos
GET /api/runs/{run_id}/nodes/{node}/artifacts   → artifacts completos del nodo
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from runs.store import get_run_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/runs", tags=["runs"])

_USER_ID = "default"  # single-tenant, igual que el resto de la plataforma


@router.get("/{run_id}")
async def get_run(run_id: str):
    store = get_run_store()
    run = await store.get_run(run_id, user_id=_USER_ID)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/{run_id}/nodes/{node}/artifacts")
async def get_node_artifacts(run_id: str, node: str):
    store = get_run_store()
    artifacts = await store.get_artifacts(run_id, node, user_id=_USER_ID)
    return {"run_id": run_id, "node": node, "artifacts": artifacts}
