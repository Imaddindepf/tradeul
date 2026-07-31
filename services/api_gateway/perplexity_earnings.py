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

    GET /rest/finance/earnings/<SYMBOL>/analysis/<eventId>?version=2.18&source=default
        -> {eventId, analysis(md bullets), created, status, date, wentLiveAt,
            preview}
           The *key highlights* of the call — the long bullets the card shows
           under "Momentos destacados". NOT the same as the day feed's
           `summary`, which is the short preview blurb. Both are Perplexity's,
           and their numbers can disagree: the highlights quote the company's
           own non-GAAP EPS, the structured `actualEps` is Perplexity's
           normalised adjusted figure (SWKS 2026-Q3: $1.85 vs 1.08).

    GET /rest/finance/earnings/<SYMBOL>/transcript/<eventId>
        -> {date, wentLiveAt, status, audio(m3u8),
            paragraphs:[{time, text, speakers:[...]}],
            chapters:[{id, title, startTimestamp, endTimestamp, level}]}
           This feed is LIVE while the call is happening: `status` is "live",
           `wentLiveAt` marks the real start (which can precede the scheduled
           `date`), and paragraphs appear as people speak. Two properties,
           measured against a call in progress, drive the design here:
             * The LAST paragraph is provisional. It is rewritten in place as
               the sentence completes — same `time`, longer `text` — so the list
               must be re-rendered wholesale, never appended to by index.
             * `speakers` and `chapters` stay empty until post-processing; they
               only populate once `status` becomes "final".
           Observed `status` values: "live" (in progress), "final" (processed)
           and "failed" (the source could not capture the call — null audio,
           null `wentLiveAt`, zero paragraphs). See `_is_live_transcript`.

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

# Live-call cadence. Upstream serves the transcript with `Cache-Control:
# max-age=5, stale-while-revalidate=60`, so a few seconds is the granularity the
# source itself offers; anything faster only burns requests. `_LIVE_POLL_SECONDS`
# is handed to the client as `poll_after_seconds` so the cadence lives here, in
# one place, instead of being hardcoded in the UI.
_LIVE_CACHE_SECONDS = 3
_LIVE_POLL_SECONDS = 8

# Transcript states that will never change again. "failed" matters as much as
# "final": the source emits it for calls it could not capture, and those rows
# carry a null `wentLiveAt` with zero paragraphs — indistinguishable from a live
# call if you only test `status != "final"`, which is how a first cut of the live
# scan reported a handful of silent placeholders as being on the air.
_TERMINAL_TRANSCRIPT_STATES = frozenset({"final", "failed"})


def _is_live_transcript(raw: Optional[Dict[str, Any]]) -> bool:
    """True only for a call actually being transcribed right now.

    Defined by `wentLiveAt` being set — the source's own marker that the call
    started — plus a non-terminal state. Deliberately not a positive match on
    `status == "live"`, so an unforeseen in-progress label still counts.
    """
    if not raw:
        return False
    if not raw.get("wentLiveAt"):
        return False
    return (raw.get("status") or "") not in _TERMINAL_TRANSCRIPT_STATES

# Audio proxy. The call audio is an HLS stream on the upstream vendor's CDN, so
# it cannot be handed to the browser as-is: the hostname identifies the provider.
# Everything is relayed through our own /audio routes instead, and only these
# hosts may ever be fetched — without the allowlist the relay would be an open
# proxy usable against any address, including this network's internals.
_AUDIO_HOST_ALLOWLIST = frozenset({"files.quartr.com"})
# Playlist base per event, so segment requests carry only a relative path and
# never a caller-supplied URL. Keyed "SYMBOL:eventId".
_audio_base_cache = BoundedTTLCache(maxsize=256, ttl_seconds=3600)

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
# Transcripts come in two flavours and must NOT share a TTL. A finished call is
# immutable, so an hour is free. A call in progress grows every few seconds —
# caching that for an hour freezes the live transcript for everyone watching, so
# it gets a few seconds only: enough to coalesce a burst of concurrent viewers
# into one upstream request, never enough to show stale speech.
_transcript_cache = BoundedTTLCache(maxsize=256, ttl_seconds=3600)  # final: 1 h
_transcript_live_cache = BoundedTTLCache(maxsize=256, ttl_seconds=_LIVE_CACHE_SECONDS)
_documents_cache = BoundedTTLCache(maxsize=256, ttl_seconds=3600)  # 1 h
# Call analysis ("key highlights"): written once the call is processed, then
# immutable — but cache short while status != "final" so a pending event picks
# the real text up on the next view.
_analysis_cache = BoundedTTLCache(maxsize=256, ttl_seconds=3600)  # 1 h


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
    """Fetch the transcript, honouring the live/final split described above.

    While the call is in progress upstream appends new paragraphs AND rewrites
    the last one in place (the trailing paragraph is a partial that keeps
    growing as the speaker talks, same `time`, longer `text`). Callers must
    therefore treat the returned list as the whole truth and re-render it, never
    append it to a previously held copy.
    """
    symbol = symbol.upper().strip()
    key = f"{symbol}:{event_id}"
    cached = _transcript_cache.get(key)
    if cached is not None:
        return cached
    cached = _transcript_live_cache.get(key)
    if cached is not None:
        return cached
    url = f"{_BASE}/{symbol}/transcript/{event_id}"
    data = await asyncio.to_thread(_fetch_json_sync, url)
    if isinstance(data, dict):
        # Terminal states are immutable, so they get the long TTL. Anything else
        # may still change and gets seconds. A "failed" row belongs in the long
        # cache too, or every poller would re-fetch it forever.
        if (data.get("status") or "") in _TERMINAL_TRANSCRIPT_STATES:
            _transcript_cache.set(key, data)
        else:
            _transcript_live_cache.set(key, data)
        return data
    return None


async def fetch_analysis_raw(symbol: str, event_id: int) -> Optional[Dict[str, Any]]:
    """Key highlights of the earnings call ("Momentos destacados" in the UI).

    This is a *different* payload from the day feed's `summary`: 5-ish long
    bullets written from the call itself. Only reachable through this endpoint.
    """
    symbol = symbol.upper().strip()
    key = f"{symbol}:{event_id}"
    cached = _analysis_cache.get(key)
    if cached is not None:
        return cached
    url = f"{_BASE}/{symbol}/analysis/{event_id}?version=2.18&source=default"
    data = await asyncio.to_thread(_fetch_json_sync, url)
    if isinstance(data, dict):
        # Only memoise the finished text; a pending call would get pinned for 1h.
        if data.get("status") == "final":
            _analysis_cache.set(key, data)
        return data
    return None


# ---------------------------------------------------------------------------
# Audio relay (HLS)
# ---------------------------------------------------------------------------


def _fetch_bytes_sync(url: str) -> Optional[tuple]:
    """Blocking GET returning (content_type, body). Used for HLS relaying."""
    from curl_cffi import requests as cffi_requests

    global _cffi_session
    for attempt, target in enumerate(("chrome",) + _IMPERSONATE_TARGETS):
        try:
            session = _get_session() if attempt == 0 else cffi_requests.Session(impersonate=target)
            resp = session.get(url, timeout=25, headers=_BASE_HEADERS)
            if resp.status_code == 200:
                return resp.headers.get("Content-Type", "application/octet-stream"), resp.content
        except Exception:
            continue
    logger.warning("perplexity_audio_fetch_blocked", extra={"url": url})
    return None


def _audio_url_allowed(url: Optional[str]) -> bool:
    """Only https URLs on the known media CDN may be relayed."""
    if not url:
        return False
    from urllib.parse import urlsplit
    parts = urlsplit(url)
    return parts.scheme == "https" and parts.hostname in _AUDIO_HOST_ALLOWLIST


def _pack_audio_url(url: str) -> str:
    from base64 import urlsafe_b64encode
    return urlsafe_b64encode(url.encode()).decode().rstrip("=")


def unpack_audio_url(token: str) -> Optional[str]:
    """Decode a relay token back to an upstream URL, or None if it is not one we
    are willing to fetch. Every relay request goes through this check."""
    from base64 import urlsafe_b64decode
    try:
        padded = token + "=" * (-len(token) % 4)
        url = urlsafe_b64decode(padded.encode()).decode()
    except Exception:
        return None
    return url if _audio_url_allowed(url) else None


async def resolve_audio_source(symbol: str, event_id: int) -> Optional[str]:
    """Absolute upstream URL of the event's HLS playlist, if it has one."""
    key = f"{symbol.upper()}:{event_id}"
    cached = _audio_base_cache.get(key)
    if cached is not None:
        return cached or None
    raw = await fetch_transcript_raw(symbol, event_id)
    url = (raw or {}).get("audio")
    if not _audio_url_allowed(url):
        # Cache the negative too, so a call without audio is not re-fetched.
        _audio_base_cache.set(key, "")
        return None
    _audio_base_cache.set(key, url)
    return url


def _rewrite_playlist(body: bytes, base_url: str) -> str:
    """Rewrite every URI in an HLS playlist to point back at our own relay.

    Handles media playlists, master playlists (whose entries are themselves
    playlists) and the URI="..." attributes of EXT-X-KEY / EXT-X-MAP. Anything
    that does not resolve onto the allowlisted CDN is dropped rather than passed
    through, so a rewritten playlist can never send the browser off-site.

    The emitted URIs are RELATIVE ("segment?u=..."), which the player resolves
    against the playlist's own URL. Absolute ones would have to be built from
    the inbound request, and behind the reverse proxy that yields the internal
    address — a playlist full of localhost URLs the browser cannot fetch. Both
    relay routes live in the same path segment, so relative always resolves.
    """
    from urllib.parse import urljoin, urlsplit
    import re

    def relay_for(raw_uri: str) -> Optional[str]:
        absolute = urljoin(base_url, raw_uri.strip())
        if not _audio_url_allowed(absolute):
            return None
        kind = "playlist.m3u8" if urlsplit(absolute).path.endswith(".m3u8") else "segment"
        return f"{kind}?u={_pack_audio_url(absolute)}"

    out: List[str] = []
    for line in body.decode("utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped:
            out.append(line)
            continue
        if stripped.startswith("#"):
            # Tags carry their target inside URI="...".
            match = re.search(r'URI="([^"]+)"', stripped)
            if match:
                relay = relay_for(match.group(1))
                if relay is None:
                    continue
                line = stripped.replace(match.group(1), relay)
            out.append(line)
            continue
        relay = relay_for(stripped)
        if relay is None:
            continue
        out.append(relay)
    return "\n".join(out) + "\n"


async def get_audio_playlist(
    symbol: str, event_id: int, token: Optional[str] = None
) -> Optional[str]:
    """Rewritten HLS playlist. `token` selects a nested playlist from a master;
    without it, the event's root playlist is served."""
    url = unpack_audio_url(token) if token else await resolve_audio_source(symbol, event_id)
    if not url:
        return None
    fetched = await asyncio.to_thread(_fetch_bytes_sync, url)
    if fetched is None:
        return None
    return _rewrite_playlist(fetched[1], url)


async def get_audio_segment(token: str) -> Optional[tuple]:
    """Relay one media segment as (content_type, bytes)."""
    url = unpack_audio_url(token)
    if not url:
        return None
    return await asyncio.to_thread(_fetch_bytes_sync, url)


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
    """Split Perplexity's `summary` (markdown bullets) into a list.

    This is the *preview summary* the day feed carries — the handful of bullets
    Perplexity shows before you open an earnings card. It is NOT the longer
    "key highlights" of the call that the card renders inside; those come from
    a request we do not make (no public endpoint found, and `requiresLogin` is
    false, so it is not a session issue either).

    Never read figures out of this prose as data. It quotes the company's own
    non-GAAP numbers, which can differ from the normalised `actualEps` in the
    same payload — e.g. SWKS 2026-Q3: the prose says EPS $1.85, `actualEps` is
    1.08. Both come from Perplexity; only the structured field is comparable
    against `estimatedEps`.
    """
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
        # --- AI content (preview summary, NOT the call's key highlights) ---
        "summary": row.get("summary"),
        "summary_bullets": _summary_bullets(row.get("summary")),
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
    paragraphs = raw.get("paragraphs") or []
    is_live = _is_live_transcript(raw)
    return {
        "symbol": symbol.upper(),
        "event_id": event_id,
        "status": raw.get("status"),
        "is_live": is_live,
        # How long the client should wait before asking again. Only meaningful
        # while live; None tells the client there is nothing left to follow.
        "poll_after_seconds": _LIVE_POLL_SECONDS if is_live else None,
        "date": raw.get("date"),
        "report_date": _local_date(dt_utc, tz),
        "report_time": _local_clock(dt_utc, tz),
        # Real start of the call, which can precede the scheduled `date`.
        "went_live_at": raw.get("wentLiveAt"),
        "paragraph_count": len(paragraphs),
        # Seconds of call transcribed so far — the live progress indicator.
        "last_paragraph_time": (paragraphs[-1].get("time") if paragraphs else None),
        # RELATIVE path on our own API, not the upstream URL: the audio is an
        # HLS stream on the vendor's CDN and its hostname would identify the
        # provider, so it is relayed. Clients must prefix their API base.
        "audio_url": (
            f"/api/v1/earnings/audio/{symbol.upper()}/{event_id}/playlist.m3u8"
            if _audio_url_allowed(raw.get("audio"))
            else None
        ),
        # HLS needs a player (hls.js) outside Safari — a plain <audio src> is
        # silent in Chrome. Flagged so the client does not have to sniff the
        # extension.
        "audio_is_hls": _audio_url_allowed(raw.get("audio")),
        # Speaker labels and chapters arrive only with the post-processed final
        # transcript; expect both empty while live.
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
    history, transcript, analysis = await asyncio.gather(
        fetch_symbol_raw(symbol),
        fetch_transcript_raw(symbol, event_id),
        fetch_analysis_raw(symbol, event_id),
    )
    match = next((r for r in history if r.get("id") == event_id), None)
    if match is None and not transcript:
        return None

    match = match or {}
    dt_utc = _parse_utc(match.get("date") or (transcript or {}).get("date"))
    report_date = _local_date(dt_utc, tz)
    actual_eps = match.get("actualEps")
    actual_rev = match.get("actualRevenue")
    est_eps = match.get("estimatedEps")
    est_rev = match.get("estimatedRevenue")

    # The preview-summary bullets live on the *day* feed, not the per-symbol
    # history feed. See _summary_bullets: this is the summary, not the call's
    # key highlights.
    summary: Optional[str] = None
    summary_bullets: List[str] = []
    if report_date:
        day_rows = await fetch_day_raw(report_date, tz)
        for row in day_rows:
            if row.get("id") == event_id and (row.get("symbol") or "").upper() == symbol:
                summary = row.get("summary")
                summary_bullets = _summary_bullets(summary)
                break

    return {
        "symbol": symbol,
        "event_id": event_id,
        "report_date": report_date,
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
        # Preview summary (short, from the day feed).
        "summary": summary,
        "summary_bullets": summary_bullets,
        # Key highlights of the call (long, from the /analysis endpoint).
        "key_highlights": _summary_bullets((analysis or {}).get("analysis")),
        "key_highlights_status": (analysis or {}).get("status"),
        "has_transcript": transcript is not None,
        "transcript_status": (transcript or {}).get("status"),
        # Lets the card show a live badge and open straight on the transcript
        # without having to fetch the transcript itself first.
        "transcript_is_live": _is_live_transcript(transcript),
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


# ---------------------------------------------------------------------------
# Live-call discovery
# ---------------------------------------------------------------------------

_live_scan_cache = BoundedTTLCache(maxsize=8, ttl_seconds=30)
# A transcript probe is one upstream request per event, and the day feed carries
# ~200 events. Only events scheduled inside this window around "now" can
# plausibly be on a call, which cuts a scan to a handful of probes: calls start
# at the scheduled time and run about an hour, with the source lagging behind.
_LIVE_WINDOW_BEFORE = timedelta(hours=5)
_LIVE_WINDOW_AFTER = timedelta(minutes=30)
_LIVE_SCAN_CONCURRENCY = 8


async def get_live_calls(tz: str, country: str = "US") -> Dict[str, Any]:
    """Which earnings calls are being transcribed right now.

    The day feed has no live flag — its status only ever says reported or
    scheduled — so being live is a property of the transcript, and the only way
    to know is to ask. Kept affordable by probing just the events whose
    scheduled time is near now, and by caching the whole scan briefly so N
    viewers cost one scan.
    """
    tz = _tz_or_default(tz)
    key = f"{tz}:{country}"
    cached = _live_scan_cache.get(key)
    if cached is not None:
        return cached

    now = datetime.now(timezone.utc)
    # Yesterday too: a late call still running past midnight UTC lands on the
    # previous calendar day.
    days = {
        (now - timedelta(days=1)).astimezone(ZoneInfo(tz)).strftime("%Y-%m-%d"),
        now.astimezone(ZoneInfo(tz)).strftime("%Y-%m-%d"),
    }
    feeds = await asyncio.gather(*[fetch_day_raw(d, tz, country) for d in sorted(days)])

    candidates: List[Dict[str, Any]] = []
    seen_ids = set()
    for rows in feeds:
        for row in rows:
            event_id = row.get("id")
            if event_id in seen_ids:
                continue
            scheduled = _parse_utc(row.get("date"))
            if scheduled is None:
                continue
            if now - _LIVE_WINDOW_BEFORE <= scheduled <= now + _LIVE_WINDOW_AFTER:
                seen_ids.add(event_id)
                candidates.append(row)

    semaphore = asyncio.Semaphore(_LIVE_SCAN_CONCURRENCY)

    async def probe(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        async with semaphore:
            raw = await fetch_transcript_raw(row.get("symbol") or "", row.get("id"))
        if not _is_live_transcript(raw):
            return None
        paragraphs = raw.get("paragraphs") or []
        dt_utc = _parse_utc(row.get("date"))
        return {
            "symbol": row.get("symbol"),
            "company_name": row.get("companyName"),
            "event_id": row.get("id"),
            "report_date": _local_date(dt_utc, tz),
            "report_time": _local_clock(dt_utc, tz),
            "time_slot": _derive_time_slot(dt_utc),
            "fiscal_period": row.get("fiscalPeriod"),
            "fiscal_year": row.get("fiscalYear"),
            "market_cap": row.get("mktCap"),
            "went_live_at": raw.get("wentLiveAt"),
            "paragraph_count": len(paragraphs),
            "last_paragraph_time": (paragraphs[-1].get("time") if paragraphs else None),
        }

    probed = await asyncio.gather(*[probe(r) for r in candidates], return_exceptions=True)
    live = [p for p in probed if isinstance(p, dict)]
    live.sort(key=lambda r: -(r.get("market_cap") or 0))

    result = {
        "timezone": tz,
        "live": live,
        "count": len(live),
        "scanned": len(candidates),
    }
    _live_scan_cache.set(key, result)
    return result
