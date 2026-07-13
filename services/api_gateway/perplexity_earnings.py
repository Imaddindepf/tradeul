"""
Perplexity Finance — Earnings Calendar source
=============================================
Reverse-engineered client for the same private REST API that powers
https://www.perplexity.ai/finance/earnings. Replaces the paid Benzinga/Polygon
earnings feed with Perplexity's free feed (rich AI summaries + transcripts +
filing documents + post-earnings price reaction).

Upstream endpoints (all bypass Cloudflare via curl_cffi Chrome impersonation,
no login required):

    GET /rest/finance/earnings?date=YYYY-MM-DD&timezone=<tz>&country=US
        -> day list: [{symbol, companyName, date(UTC ISO), id(eventId),
                       fiscalYear, fiscalPeriod, actualEps, actualRevenue,
                       estimatedEps, estimatedRevenue, summary(md bullets),
                       image, imageDark, mktCap, currency, status,
                       expectedMovePerc, postEarningsMove1D, requiresLogin}]

    GET /rest/finance/earnings/schedule?start_date=&end_date=&timezone=&country=
        -> [{date(YYYY-MM-DD), count, topCompanies:[{symbol,image,imageDark}]}]

    GET /rest/finance/earnings/<SYMBOL>
        -> per-quarter history WITH estimates + price reaction:
           [{date, id, fiscalYear, fiscalPeriod, actualRevenue, estimatedRevenue,
             actualEps, estimatedEps, postEarningsMove1D, expectedMovePerc,
             averagePostEarningsMove1D}]

    GET /rest/finance/earnings/<SYMBOL>/transcript/<eventId>
        -> {date, wentLiveAt, status, audio(m3u8),
            paragraphs:[{time, text, speakers:[...]}],
            chapters:[{id, title, startTimestamp, endTimestamp, level}]}

    GET /rest/finance/earnings/<SYMBOL>/documents/<eventId>
        -> [{id, fileUrl, type, updatedAt, createdAt,
             metadata:{name, description, form, category}}]

IMPORTANT — timezone handling:
  * The `timezone` query param only changes how Perplexity buckets events into
    calendar days. The `date` field it returns is ALWAYS a UTC ISO timestamp.
  * We therefore pass the *user's* preferred timezone (theme.timezone in the
    app, default America/New_York) so day bucketing matches what the user sees,
    and we additionally convert each UTC timestamp into that timezone to render
    a local "HH:MM" clock.
  * The BMO / AMC / DURING slot is a property of the US session, so it is ALWAYS
    derived from the Eastern Time (America/New_York) wall-clock, independent of
    the user's display timezone.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from shared.utils.logger import get_logger
from bounded_cache import BoundedTTLCache

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# HTTP fetching (curl_cffi with Chrome impersonation + retries)
# ---------------------------------------------------------------------------

_BASE = "https://www.perplexity.ai/rest/finance/earnings"
_BASE_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.perplexity.ai",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "Referer": "https://www.perplexity.ai/finance/earnings",
}
_IMPERSONATE_TARGETS = ("chrome", "chrome120", "chrome124", "chrome110", "safari17_0")

_ET = ZoneInfo("America/New_York")
_DEFAULT_TZ = "America/New_York"

_cffi_session = None


def _get_session(target: str = "chrome"):
    global _cffi_session
    if _cffi_session is None:
        from curl_cffi import requests as cffi_requests
        _cffi_session = cffi_requests.Session(impersonate=target)
    return _cffi_session


def _fetch_json_sync(url: str) -> Optional[Any]:
    """Blocking GET with Cloudflare-resilient impersonation rotation."""
    from curl_cffi import requests as cffi_requests

    global _cffi_session

    try:
        resp = _get_session().get(url, timeout=20, headers=_BASE_HEADERS)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass

    for target in _IMPERSONATE_TARGETS:
        try:
            _cffi_session = cffi_requests.Session(impersonate=target)
            resp = _cffi_session.get(url, timeout=20, headers=_BASE_HEADERS)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            continue

    _cffi_session = cffi_requests.Session(impersonate="chrome")
    logger.warning("perplexity_earnings_fetch_blocked", extra={"url": url})
    return None


# ---------------------------------------------------------------------------
# In-memory caches (per payload type, short TTL because earnings updates live)
# ---------------------------------------------------------------------------

_day_cache = BoundedTTLCache(maxsize=256, ttl_seconds=120)       # 2 min
_schedule_cache = BoundedTTLCache(maxsize=64, ttl_seconds=120)   # 2 min
_symbol_cache = BoundedTTLCache(maxsize=512, ttl_seconds=600)    # 10 min
_transcript_cache = BoundedTTLCache(maxsize=256, ttl_seconds=3600)  # 1 h
_documents_cache = BoundedTTLCache(maxsize=256, ttl_seconds=3600)  # 1 h


def _tz_or_default(tz: Optional[str]) -> str:
    if not tz:
        return _DEFAULT_TZ
    try:
        ZoneInfo(tz)
        return tz
    except Exception:
        return _DEFAULT_TZ


# ---------------------------------------------------------------------------
# Raw fetchers (async wrappers + cache)
# ---------------------------------------------------------------------------


async def fetch_day_raw(date: str, tz: str, country: str = "US") -> List[Dict[str, Any]]:
    tz = _tz_or_default(tz)
    key = f"{date}:{tz}:{country}"
    cached = _day_cache.get(key)
    if cached is not None:
        return cached
    url = f"{_BASE}?date={date}&timezone={tz}&country={country}"
    data = await asyncio.to_thread(_fetch_json_sync, url)
    data = data if isinstance(data, list) else []
    _day_cache.set(key, data)
    return data


async def fetch_schedule_raw(
    start_date: str, end_date: str, tz: str, country: str = "US"
) -> List[Dict[str, Any]]:
    tz = _tz_or_default(tz)
    key = f"{start_date}:{end_date}:{tz}:{country}"
    cached = _schedule_cache.get(key)
    if cached is not None:
        return cached
    url = (
        f"{_BASE}/schedule?start_date={start_date}&end_date={end_date}"
        f"&timezone={tz}&country={country}"
    )
    data = await asyncio.to_thread(_fetch_json_sync, url)
    data = data if isinstance(data, list) else []
    _schedule_cache.set(key, data)
    return data


async def fetch_symbol_raw(symbol: str) -> List[Dict[str, Any]]:
    symbol = symbol.upper().strip()
    cached = _symbol_cache.get(symbol)
    if cached is not None:
        return cached
    url = f"{_BASE}/{symbol}"
    data = await asyncio.to_thread(_fetch_json_sync, url)
    data = data if isinstance(data, list) else []
    _symbol_cache.set(symbol, data)
    return data


async def fetch_transcript_raw(symbol: str, event_id: int) -> Optional[Dict[str, Any]]:
    symbol = symbol.upper().strip()
    key = f"{symbol}:{event_id}"
    cached = _transcript_cache.get(key)
    if cached is not None:
        return cached
    url = f"{_BASE}/{symbol}/transcript/{event_id}"
    data = await asyncio.to_thread(_fetch_json_sync, url)
    if isinstance(data, dict):
        _transcript_cache.set(key, data)
        return data
    return None


async def fetch_documents_raw(symbol: str, event_id: int) -> List[Dict[str, Any]]:
    symbol = symbol.upper().strip()
    key = f"{symbol}:{event_id}"
    cached = _documents_cache.get(key)
    if cached is not None:
        return cached
    url = f"{_BASE}/{symbol}/documents/{event_id}"
    data = await asyncio.to_thread(_fetch_json_sync, url)
    data = data if isinstance(data, list) else []
    _documents_cache.set(key, data)
    return data


# ---------------------------------------------------------------------------
# Transform helpers
# ---------------------------------------------------------------------------


def _parse_utc(iso: Optional[str]) -> Optional[datetime]:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def _derive_time_slot(dt_utc: Optional[datetime]) -> str:
    """BMO / AMC / DURING from the US Eastern session wall-clock."""
    if dt_utc is None:
        return "TBD"
    et = dt_utc.astimezone(_ET)
    # Perplexity uses 00:00 ET as a "time unknown" sentinel for some rows.
    hm = et.hour * 60 + et.minute
    if hm == 0:
        return "TBD"
    if hm < 9 * 60 + 30:
        return "BMO"
    if hm >= 16 * 60:
        return "AMC"
    return "DURING"


def _local_clock(dt_utc: Optional[datetime], tz: str) -> Optional[str]:
    if dt_utc is None:
        return None
    try:
        local = dt_utc.astimezone(ZoneInfo(tz))
        if local.hour == 0 and local.minute == 0:
            return None
        return local.strftime("%H:%M")
    except Exception:
        return None


def _local_date(dt_utc: Optional[datetime], tz: str) -> Optional[str]:
    if dt_utc is None:
        return None
    try:
        return dt_utc.astimezone(ZoneInfo(tz)).strftime("%Y-%m-%d")
    except Exception:
        return None


def _strip_vendor_ref(url: Optional[str]) -> Optional[str]:
    """Remove the upstream attribution query param from asset URLs so the
    provider is not identifiable in the browser (the `ref` value base64-decodes
    to the upstream vendor name). The asset still serves without it."""
    if not url:
        return url
    from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() != "ref"]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _summary_bullets(summary: Optional[str]) -> List[str]:
    """Perplexity `summary` is markdown bullets separated by newlines."""
    if not summary:
        return []
    out: List[str] = []
    for line in summary.splitlines():
        s = line.strip()
        if not s:
            continue
        # Strip leading markdown bullet markers.
        while s and s[0] in "-*•":
            s = s[1:].strip()
        if s:
            out.append(s)
    return out


def _beat(actual: Optional[float], estimate: Optional[float]) -> Optional[bool]:
    if actual is None or estimate is None:
        return None
    return actual >= estimate


def _surprise_pct(actual: Optional[float], estimate: Optional[float]) -> Optional[float]:
    if actual is None or estimate is None or estimate == 0:
        return None
    return round((actual - estimate) / abs(estimate) * 100, 2)


def _fiscal_label(row: Dict[str, Any]) -> Optional[str]:
    fy = row.get("fiscalYear")
    fp = row.get("fiscalPeriod")
    if fp and fy:
        return f"{fp} {fy}"
    return fp or (str(fy) if fy else None)


def transform_day_item(row: Dict[str, Any], tz: str) -> Dict[str, Any]:
    """Map a raw Perplexity day item into the frontend EarningsReport shape
    (backward compatible with the old Benzinga fields, plus new rich fields)."""
    dt_utc = _parse_utc(row.get("date"))
    actual_eps = row.get("actualEps")
    actual_rev = row.get("actualRevenue")
    est_eps = row.get("estimatedEps")
    est_rev = row.get("estimatedRevenue")
    reported = row.get("status") == "final" or actual_eps is not None or actual_rev is not None

    return {
        # --- identity ---
        "symbol": row.get("symbol"),
        "company_name": row.get("companyName"),
        "event_id": row.get("id"),
        # --- timing ---
        "report_date": _local_date(dt_utc, tz),
        "report_time": _local_clock(dt_utc, tz),           # local HH:MM (user tz)
        "utc_time": row.get("date"),                         # raw UTC ISO
        "time_slot": _derive_time_slot(dt_utc),              # ET-based BMO/AMC/DURING
        # --- fiscal ---
        "fiscal_year": row.get("fiscalYear"),
        "fiscal_period": row.get("fiscalPeriod"),
        "fiscal_quarter": row.get("fiscalPeriod"),
        # --- EPS ---
        "eps_estimate": est_eps,
        "eps_actual": actual_eps,
        "eps_surprise_pct": _surprise_pct(actual_eps, est_eps),
        "beat_eps": _beat(actual_eps, est_eps),
        # --- Revenue ---
        "revenue_estimate": est_rev,
        "revenue_actual": actual_rev,
        "revenue_surprise_pct": _surprise_pct(actual_rev, est_rev),
        "beat_revenue": _beat(actual_rev, est_rev),
        # --- AI content ---
        "summary": row.get("summary"),
        "key_highlights": _summary_bullets(row.get("summary")),
        # --- price reaction ---
        "expected_move_pct": row.get("expectedMovePerc"),
        "post_earnings_move_1d": row.get("postEarningsMove1D"),
        # --- misc ---
        "market_cap": row.get("mktCap"),
        "currency": row.get("currency"),
        "status": "reported" if reported else "scheduled",
        "date_status": "confirmed",
        "requires_login": row.get("requiresLogin", False),
        # Fields the old frontend references but Perplexity does not expose.
        "guidance_direction": None,
        "guidance_commentary": None,
        "eps_method": None,
        "revenue_method": None,
        "previous_eps": None,
        "previous_revenue": None,
        "sector": None,
        "importance": _importance_from_mktcap(row.get("mktCap")),
        "notes": None,
        "source": "tradeul",
    }


def _importance_from_mktcap(mktcap: Optional[float]) -> int:
    """Derive a 0-5 importance score from market cap so the existing
    importance filter/sort keeps working (Perplexity has no importance field)."""
    if not mktcap:
        return 0
    if mktcap >= 500e9:
        return 5
    if mktcap >= 100e9:
        return 4
    if mktcap >= 10e9:
        return 3
    if mktcap >= 2e9:
        return 2
    if mktcap >= 300e6:
        return 1
    return 0


def _time_order(slot: str) -> int:
    return {"BMO": 0, "DURING": 1, "AMC": 2, "TBD": 3}.get(slot, 3)


def build_calendar(rows: List[Dict[str, Any]], date: str, tz: str) -> Dict[str, Any]:
    """Build the CalendarResponse the frontend day view consumes."""
    reports = [transform_day_item(r, tz) for r in rows]
    reports.sort(key=lambda r: (-(r.get("importance") or 0), _time_order(r.get("time_slot", "TBD")), r.get("symbol") or ""))

    total_bmo = sum(1 for r in reports if r["time_slot"] == "BMO")
    total_amc = sum(1 for r in reports if r["time_slot"] == "AMC")
    total_during = sum(1 for r in reports if r["time_slot"] == "DURING")
    total_reported = sum(1 for r in reports if r["status"] == "reported")

    return {
        "date": date,
        "timezone": tz,
        "reports": reports,
        "total_count": len(reports),
        "total_bmo": total_bmo,
        "total_amc": total_amc,
        "total_during": total_during,
        "total_reported": total_reported,
        "total_scheduled": len(reports) - total_reported,
        "total_confirmed": len(reports),
        "total_projected": 0,
    }


def build_schedule(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Week-strip payload: per-day counts + top company logos."""
    days = []
    for r in rows:
        days.append({
            "date": r.get("date"),
            "count": r.get("count", 0),
            "top_companies": [
                {"symbol": c.get("symbol")}
                for c in (r.get("topCompanies") or [])
            ],
        })
    return {"days": days}


def build_ticker_history(symbol: str, rows: List[Dict[str, Any]], tz: str) -> Dict[str, Any]:
    """Per-symbol quarterly history (estimates + actuals + price reaction)."""
    out: List[Dict[str, Any]] = []
    for r in rows:
        dt_utc = _parse_utc(r.get("date"))
        actual_eps = r.get("actualEps")
        actual_rev = r.get("actualRevenue")
        est_eps = r.get("estimatedEps")
        est_rev = r.get("estimatedRevenue")
        out.append({
            "symbol": symbol.upper(),
            "event_id": r.get("id"),
            "report_date": _local_date(dt_utc, tz),
            "report_time": _local_clock(dt_utc, tz),
            "utc_time": r.get("date"),
            "time_slot": _derive_time_slot(dt_utc),
            "fiscal_year": r.get("fiscalYear"),
            "fiscal_period": r.get("fiscalPeriod"),
            "fiscal_quarter": r.get("fiscalPeriod"),
            "eps_estimate": est_eps,
            "eps_actual": actual_eps,
            "eps_surprise_pct": _surprise_pct(actual_eps, est_eps),
            "beat_eps": _beat(actual_eps, est_eps),
            "revenue_estimate": est_rev,
            "revenue_actual": actual_rev,
            "revenue_surprise_pct": _surprise_pct(actual_rev, est_rev),
            "beat_revenue": _beat(actual_rev, est_rev),
            "expected_move_pct": r.get("expectedMovePerc"),
            "post_earnings_move_1d": r.get("postEarningsMove1D"),
            "avg_post_earnings_move_1d": r.get("averagePostEarningsMove1D"),
            "status": "reported" if actual_eps is not None else "scheduled",
            "source": "tradeul",
        })
    # Newest first
    out.sort(key=lambda r: (r.get("utc_time") or ""), reverse=True)

    reported = [r for r in out if r["eps_actual"] is not None]
    beats = sum(1 for r in reported if r["beat_eps"] is True)
    misses = sum(1 for r in reported if r["beat_eps"] is False)
    beat_rate = round(beats / len(reported) * 100, 1) if reported else None

    return {
        "symbol": symbol.upper(),
        "earnings": out,
        "count": len(out),
        "stats": {
            "total_reported": len(reported),
            "beats": beats,
            "misses": misses,
            "beat_rate": beat_rate,
        },
    }


def build_transcript(symbol: str, event_id: int, raw: Dict[str, Any], tz: str) -> Dict[str, Any]:
    dt_utc = _parse_utc(raw.get("date"))
    speakers = []
    seen = set()
    for p in raw.get("paragraphs") or []:
        for sp in p.get("speakers") or []:
            if sp not in seen:
                seen.add(sp)
                speakers.append(sp)
    return {
        "symbol": symbol.upper(),
        "event_id": event_id,
        "status": raw.get("status"),
        "date": raw.get("date"),
        "report_date": _local_date(dt_utc, tz),
        "report_time": _local_clock(dt_utc, tz),
        "went_live_at": raw.get("wentLiveAt"),
        "audio_url": _strip_vendor_ref(raw.get("audio")),
        "speakers": speakers,
        "chapters": [
            {
                "id": c.get("id"),
                "title": c.get("title"),
                "start": c.get("startTimestamp"),
                "end": c.get("endTimestamp"),
                "level": c.get("level"),
            }
            for c in (raw.get("chapters") or [])
        ],
        "paragraphs": [
            {"time": p.get("time"), "text": p.get("text"), "speakers": p.get("speakers") or []}
            for p in (raw.get("paragraphs") or [])
        ],
    }


def build_documents(symbol: str, event_id: int, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    docs = []
    for r in rows:
        meta = r.get("metadata") or {}
        docs.append({
            "id": r.get("id"),
            "file_url": _strip_vendor_ref(r.get("fileUrl")),
            "type": r.get("type"),
            "name": meta.get("name"),
            "description": meta.get("description"),
            "form": meta.get("form"),
            "category": meta.get("category"),
            "updated_at": r.get("updatedAt"),
            "created_at": r.get("createdAt"),
        })
    return {"symbol": symbol.upper(), "event_id": event_id, "documents": docs, "count": len(docs)}


async def build_event_detail(symbol: str, event_id: int, tz: str) -> Optional[Dict[str, Any]]:
    """Assemble the per-event detail view: the day-item content (summary,
    actuals) merged with per-symbol estimates + price reaction, and the
    availability of transcript / documents."""
    symbol = symbol.upper().strip()
    history, transcript = await asyncio.gather(
        fetch_symbol_raw(symbol),
        fetch_transcript_raw(symbol, event_id),
    )
    match = next((r for r in history if r.get("id") == event_id), None)
    if match is None and not transcript:
        return None

    match = match or {}
    dt_utc = _parse_utc(match.get("date") or (transcript or {}).get("date"))
    actual_eps = match.get("actualEps")
    actual_rev = match.get("actualRevenue")
    est_eps = match.get("estimatedEps")
    est_rev = match.get("estimatedRevenue")

    return {
        "symbol": symbol,
        "event_id": event_id,
        "report_date": _local_date(dt_utc, tz),
        "report_time": _local_clock(dt_utc, tz),
        "utc_time": match.get("date"),
        "time_slot": _derive_time_slot(dt_utc),
        "fiscal_year": match.get("fiscalYear"),
        "fiscal_period": match.get("fiscalPeriod"),
        "fiscal_label": _fiscal_label(match),
        "eps_estimate": est_eps,
        "eps_actual": actual_eps,
        "eps_surprise_pct": _surprise_pct(actual_eps, est_eps),
        "beat_eps": _beat(actual_eps, est_eps),
        "revenue_estimate": est_rev,
        "revenue_actual": actual_rev,
        "revenue_surprise_pct": _surprise_pct(actual_rev, est_rev),
        "beat_revenue": _beat(actual_rev, est_rev),
        "expected_move_pct": match.get("expectedMovePerc"),
        "post_earnings_move_1d": match.get("postEarningsMove1D"),
        "avg_post_earnings_move_1d": match.get("averagePostEarningsMove1D"),
        "has_transcript": transcript is not None,
        "transcript_status": (transcript or {}).get("status"),
        "source": "tradeul",
    }


# ---------------------------------------------------------------------------
# Aggregations
# ---------------------------------------------------------------------------


async def get_calendar(date: str, tz: str, country: str = "US") -> Dict[str, Any]:
    tz = _tz_or_default(tz)
    rows = await fetch_day_raw(date, tz, country)
    return build_calendar(rows, date, tz)


async def get_upcoming(days: int, tz: str, country: str = "US") -> Dict[str, Any]:
    """Aggregate the next N days of earnings into a single list (week view)."""
    tz = _tz_or_default(tz)
    today = datetime.now(ZoneInfo(tz)).date()
    dates = [(today + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days + 1)]

    results = await asyncio.gather(*[fetch_day_raw(d, tz, country) for d in dates])

    all_reports: List[Dict[str, Any]] = []
    by_date: Dict[str, int] = {}
    for d, rows in zip(dates, results):
        transformed = [transform_day_item(r, tz) for r in rows]
        by_date[d] = len(transformed)
        all_reports.extend(transformed)

    all_reports.sort(key=lambda r: (r.get("report_date") or "", _time_order(r.get("time_slot", "TBD")), -(r.get("importance") or 0)))

    end_date = (today + timedelta(days=days)).strftime("%Y-%m-%d")
    return {
        "start_date": today.strftime("%Y-%m-%d"),
        "end_date": end_date,
        "timezone": tz,
        "earnings": all_reports,
        "total_count": len(all_reports),
        "by_date": by_date,
    }


async def get_schedule(start_date: str, end_date: str, tz: str, country: str = "US") -> Dict[str, Any]:
    tz = _tz_or_default(tz)
    rows = await fetch_schedule_raw(start_date, end_date, tz, country)
    return build_schedule(rows)


async def get_ticker_history(symbol: str, tz: str) -> Dict[str, Any]:
    tz = _tz_or_default(tz)
    rows = await fetch_symbol_raw(symbol)
    return build_ticker_history(symbol, rows, tz)


async def get_transcript(symbol: str, event_id: int, tz: str) -> Optional[Dict[str, Any]]:
    tz = _tz_or_default(tz)
    raw = await fetch_transcript_raw(symbol, event_id)
    if raw is None:
        return None
    return build_transcript(symbol, event_id, raw, tz)


async def get_documents(symbol: str, event_id: int) -> Dict[str, Any]:
    rows = await fetch_documents_raw(symbol, event_id)
    return build_documents(symbol, event_id, rows)
