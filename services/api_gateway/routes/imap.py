"""
IMAP — World Venue Map

Serves a curated world venue list (identity from ISO 10383 MIC register;
coordinates geocoded; trading hours are each venue's published local session)
with live open/pre/post/break status derived from each venue's local clock.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query
from shared.utils.logger import get_logger

from routes.world_venues import WORLD_VENUES

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/imap", tags=["imap"])

# Weekend conventions by ISO country: which weekday numbers are NON-trading.
# Python weekday(): Mon=0 … Sun=6. Default markets rest Sat(5)+Sun(6).
_GULF = {5, 6}  # Fri handled below where markets rest Fri+Sat
_FRI_SAT = {4, 5}  # Fri+Sat weekend (Gulf, Israel, Egypt)
_WEEKEND_BY_COUNTRY: Dict[str, set] = {
    "SA": _FRI_SAT, "AE": _FRI_SAT, "QA": _FRI_SAT, "KW": _FRI_SAT,
    "BH": _FRI_SAT, "OM": _FRI_SAT, "IL": _FRI_SAT, "EG": _FRI_SAT,
    "JO": _FRI_SAT,
}
_DEFAULT_WEEKEND = {5, 6}


def _hm(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def _seg(a: str, b: str, typ: str) -> Dict[str, Any]:
    return {"startMin": _hm(a), "endMin": _hm(b), "type": typ}


def _build_sessions(
    rth_open: str,
    rth_close: str,
    lunch: Optional[tuple],
    pre: Optional[tuple],
    post: Optional[tuple],
) -> List[Dict[str, Any]]:
    """Ordered intraday sessions: pre → regular (split by lunch) → post."""
    sessions: List[Dict[str, Any]] = []
    if pre:
        sessions.append(_seg(pre[0], pre[1], "pre"))
    if lunch:
        sessions.append(_seg(rth_open, lunch[0], "regular"))
        sessions.append(_seg(lunch[0], lunch[1], "lunch"))
        sessions.append(_seg(lunch[1], rth_close, "regular"))
    else:
        sessions.append(_seg(rth_open, rth_close, "regular"))
    if post:
        sessions.append(_seg(post[0], post[1], "post"))
    sessions.sort(key=lambda s: s["startMin"])
    return sessions


def _now_parts(tz: str, now_utc: datetime):
    try:
        local = now_utc.astimezone(ZoneInfo(tz))
        return local.hour * 60 + local.minute, local.weekday()
    except Exception:
        return None, None


def _status_for(
    country: str,
    tz: str,
    sessions: List[Dict[str, Any]],
    now_utc: datetime,
) -> str:
    now_m, weekday = _now_parts(tz, now_utc)
    if now_m is None:
        return "closed"
    weekend = _WEEKEND_BY_COUNTRY.get(country, _DEFAULT_WEEKEND)
    if weekday in weekend:
        return "closed"
    for s in sessions:
        if s["startMin"] <= now_m < s["endMin"]:
            if s["type"] == "lunch":
                return "break"
            if s["type"] in ("pre", "post"):
                return s["type"]
            return "open"
    return "closed"


def _build_venues(now_utc: datetime) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for mic, t in WORLD_VENUES.items():
        (lat, lng, tz, region, ro, rc, lunch, pre, post, name, city, country) = t
        sessions = _build_sessions(ro, rc, lunch, pre, post)
        status = _status_for(country, tz, sessions, now_utc)
        out.append({
            "exchange": mic,
            "mic": mic,
            "name": name,
            "timezone": tz,
            "isMarketOpen": status == "open",
            "status": status,
            "lat": lat,
            "lng": lng,
            "city": city,
            "region": region,
            "country": country,
            "sessions": sessions,
            "hasSchedule": True,
        })
    out.sort(key=lambda v: (v["region"], v["mic"]))
    return out


@router.get("/exchanges")
async def list_exchanges(
    region: Optional[str] = Query(None, description="Filter by region"),
    status: Optional[str] = Query(None, description="open | closed | break | pre | post"),
    q: Optional[str] = Query(None, description="Search MIC, name or city"),
):
    """All venues with geo + session segments for the World Venue Map."""
    now_utc = datetime.now(ZoneInfo("UTC"))
    venues = _build_venues(now_utc)

    if region:
        venues = [v for v in venues if v["region"].lower() == region.lower()]
    if status:
        venues = [v for v in venues if v["status"] == status.lower()]
    if q:
        needle = q.strip().lower()
        venues = [
            v for v in venues
            if needle in v["mic"].lower()
            or needle in (v["name"] or "").lower()
            or needle in (v["city"] or "").lower()
        ]

    return {
        "total": len(venues),
        "open": sum(1 for v in venues if v["status"] == "open"),
        "closed": sum(1 for v in venues if v["status"] == "closed"),
        "break": sum(1 for v in venues if v["status"] == "break"),
        "extended": sum(1 for v in venues if v["status"] in ("pre", "post")),
        "updated_at": now_utc.isoformat().replace("+00:00", "Z"),
        "venues": venues,
    }


@router.get("/exchanges/{exchange}")
async def get_exchange(exchange: str):
    """Single venue detail by MIC."""
    now_utc = datetime.now(ZoneInfo("UTC"))
    code = exchange.upper().strip()
    for v in _build_venues(now_utc):
        if v["mic"] == code:
            return v
    raise HTTPException(status_code=404, detail=f"Venue not found: {code}")
