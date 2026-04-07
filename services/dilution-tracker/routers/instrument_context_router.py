"""
Instrument context endpoints backed by dilutiontracker tables.
"""

import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.append(str(SERVICE_ROOT))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))
if "/app" not in sys.path:
    sys.path.append("/app")

from fastapi import APIRouter, HTTPException, Query

from repositories.instrument_context_repository import InstrumentContextRepository
from shared.utils.logger import get_logger
from shared.utils.timescale_client import TimescaleClient

logger = get_logger(__name__)
router = APIRouter(prefix="/api/instrument-context", tags=["instrument-context-v2"])


@router.get("/{ticker}")
async def get_instrument_context(
    ticker: str,
    include_completed_offerings: bool = Query(
        default=True,
        description="Include completed_offerings history in response.",
    ),
):
    """
    Returns strongly-typed instrument context for one ticker.

    Includes:
    - ticker info
    - all instruments with per-type detail models
    - optional completed offerings
    - aggregate stats
    """
    db = TimescaleClient()
    try:
        await db.connect(min_size=1, max_size=2)
        repo = InstrumentContextRepository(db)
        context = await repo.get_ticker_context(
            ticker=ticker,
            include_completed_offerings=include_completed_offerings,
        )
        if context is None:
            raise HTTPException(status_code=404, detail=f"Ticker {ticker.upper()} not found")
        return context.model_dump()
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("instrument_context_fetch_failed", ticker=ticker.upper(), error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to fetch instrument context") from exc
    finally:
        await db.disconnect()
