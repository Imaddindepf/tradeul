"""
Agent command endpoints for dilution v2 write-path.
"""

import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

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
from shared.utils.logger import get_logger
from shared.utils.timescale_client import TimescaleClient

logger = get_logger(__name__)
router = APIRouter(prefix="/api/dilution-v2/actions", tags=["dilution-v2-actions"])


@router.post("/apply", response_model=ApplyActionsResponse)
async def apply_agent_actions(
    request: ApplyActionsRequest,
    _: str = Depends(require_dilution_admin_email),
):
    """
    Apply or dry-run an agent decision batch for one filing.
    """
    db = TimescaleClient()
    try:
        await db.connect(min_size=1, max_size=2)
        service = AgentActionServiceV2(db)
        return await service.apply(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("apply_agent_actions_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to apply actions") from exc
    finally:
        await db.disconnect()
