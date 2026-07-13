"""
Earnings Routes — Perplexity Finance source
============================================
Serves the earnings calendar (day / week / per-ticker / per-event detail /
transcript / documents) directly from Perplexity's free finance feed,
replacing the paid Benzinga/Polygon TimescaleDB pipeline.

All timestamps returned by Perplexity are UTC; every endpoint accepts a
`timezone` query param (the user's `theme.timezone`, default America/New_York)
so day bucketing and the local "HH:MM" clock match what the user sees. The
BMO/AMC/DURING slot is always derived from the US Eastern session.

These routes are mounted with prefix `/api/v1/earnings` and are registered
BEFORE the legacy TimescaleDB handlers in main.py, so they take precedence for
the shared paths (`/calendar`, `/upcoming`, `/ticker/{symbol}`).
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query, HTTPException
import structlog

import perplexity_earnings as pe

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/earnings", tags=["earnings"])

_DEFAULT_TZ = "America/New_York"


def _valid_date(d: str) -> bool:
    try:
        datetime.strptime(d, "%Y-%m-%d")
        return True
    except Exception:
        return False


@router.get("/calendar")
async def get_earnings_calendar(
    date: Optional[str] = Query(None, description="YYYY-MM-DD (default: today in tz)"),
    timezone: str = Query(_DEFAULT_TZ, description="User preferred IANA timezone"),
    time_slot: Optional[str] = Query(None, description="Filter: BMO, AMC, DURING"),
    min_importance: Optional[int] = Query(None, ge=0, le=5),
    country: str = Query("US"),
):
    """Earnings for a single day (Perplexity), timezone-aware."""
    try:
        if date and not _valid_date(date):
            raise HTTPException(status_code=400, detail="Invalid date format (YYYY-MM-DD)")
        if not date:
            from zoneinfo import ZoneInfo
            tz = pe._tz_or_default(timezone)
            date = datetime.now(ZoneInfo(tz)).strftime("%Y-%m-%d")

        result = await pe.get_calendar(date, timezone, country)

        if time_slot:
            result["reports"] = [
                r for r in result["reports"]
                if r.get("time_slot", "").upper() == time_slot.upper()
            ]
        if min_importance is not None:
            result["reports"] = [
                r for r in result["reports"]
                if (r.get("importance") or 0) >= min_importance
            ]
        result["total_count"] = len(result["reports"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("earnings_calendar_error", error=str(e))
        raise HTTPException(status_code=502, detail=f"Earnings source error: {e}")


@router.get("/schedule")
async def get_earnings_schedule(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    timezone: str = Query(_DEFAULT_TZ),
    country: str = Query("US"),
):
    """Week-strip: per-day counts + top company logos."""
    try:
        if not _valid_date(start_date) or not _valid_date(end_date):
            raise HTTPException(status_code=400, detail="Invalid date format (YYYY-MM-DD)")
        return await pe.get_schedule(start_date, end_date, timezone, country)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("earnings_schedule_error", error=str(e))
        raise HTTPException(status_code=502, detail=f"Earnings source error: {e}")


@router.get("/upcoming")
async def get_upcoming_earnings(
    days: int = Query(7, ge=1, le=30, description="Days to look ahead"),
    timezone: str = Query(_DEFAULT_TZ),
    min_importance: Optional[int] = Query(None, ge=0, le=5),
    limit: int = Query(500, ge=1, le=1000),
    country: str = Query("US"),
):
    """Earnings for the next N days aggregated into one list."""
    try:
        result = await pe.get_upcoming(days, timezone, country)
        if min_importance is not None:
            result["earnings"] = [
                r for r in result["earnings"]
                if (r.get("importance") or 0) >= min_importance
            ]
        result["earnings"] = result["earnings"][:limit]
        result["total_count"] = len(result["earnings"])
        return result
    except Exception as e:
        logger.error("earnings_upcoming_error", error=str(e))
        raise HTTPException(status_code=502, detail=f"Earnings source error: {e}")


@router.get("/ticker/{symbol}")
async def get_earnings_by_ticker(
    symbol: str,
    timezone: str = Query(_DEFAULT_TZ),
    limit: int = Query(40, ge=1, le=100),
):
    """Per-ticker earnings history (estimates + actuals + price reaction)."""
    try:
        result = await pe.get_ticker_history(symbol, timezone)
        result["earnings"] = result["earnings"][:limit]
        return result
    except Exception as e:
        logger.error("earnings_by_ticker_error", error=str(e), symbol=symbol)
        raise HTTPException(status_code=502, detail=f"Earnings source error: {e}")


@router.get("/ticker/{symbol}/dates")
async def get_earnings_dates(
    symbol: str,
    timezone: str = Query(_DEFAULT_TZ),
    limit: int = Query(100, ge=1, le=500),
):
    """Lightweight endpoint for chart earnings markers: dates + time_slot only."""
    try:
        history = await pe.get_ticker_history(symbol, timezone)
        dates = [
            {"date": e.get("report_date"), "time_slot": e.get("time_slot", "TBD")}
            for e in history["earnings"][:limit]
            if e.get("report_date")
        ]
        return {"symbol": symbol.upper(), "count": len(dates), "dates": dates}
    except Exception as e:
        logger.error("earnings_dates_error", error=str(e), symbol=symbol)
        raise HTTPException(status_code=502, detail=f"Earnings source error: {e}")


@router.get("/event/{symbol}/{event_id}")
async def get_event_detail(symbol: str, event_id: int, timezone: str = Query(_DEFAULT_TZ)):
    """Per-event detail: estimates, actuals, surprise, price reaction, and
    whether a transcript is available."""
    try:
        detail = await pe.build_event_detail(symbol, event_id, timezone)
        if detail is None:
            raise HTTPException(status_code=404, detail="Earnings event not found")
        return detail
    except HTTPException:
        raise
    except Exception as e:
        logger.error("earnings_event_error", error=str(e), symbol=symbol, event_id=event_id)
        raise HTTPException(status_code=502, detail=f"Earnings source error: {e}")


@router.get("/event/{symbol}/{event_id}/transcript")
async def get_event_transcript(symbol: str, event_id: int, timezone: str = Query(_DEFAULT_TZ)):
    """Full earnings-call transcript (paragraphs + speakers + chapters + audio)."""
    try:
        transcript = await pe.get_transcript(symbol, event_id, timezone)
        if transcript is None:
            raise HTTPException(status_code=404, detail="Transcript not available")
        return transcript
    except HTTPException:
        raise
    except Exception as e:
        logger.error("earnings_transcript_error", error=str(e), symbol=symbol, event_id=event_id)
        raise HTTPException(status_code=502, detail=f"Earnings source error: {e}")


@router.get("/event/{symbol}/{event_id}/documents")
async def get_event_documents(symbol: str, event_id: int):
    """Filing documents attached to the earnings event (8-K, 10-Q, etc.)."""
    try:
        return await pe.get_documents(symbol, event_id)
    except Exception as e:
        logger.error("earnings_documents_error", error=str(e), symbol=symbol, event_id=event_id)
        raise HTTPException(status_code=502, detail=f"Earnings source error: {e}")
