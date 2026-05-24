"""
Bug Reports Router

Captures user-submitted bug reports from the dashboard toolbar and
exposes an admin-only management surface to triage, resolve and delete
them.

Storage layout
--------------
Filesystem (canonical source for raw payloads + screenshots):
  ${BUG_REPORTS_DIR:-/data/bug_reports}/<id>/metadata.json
  ${BUG_REPORTS_DIR:-/data/bug_reports}/<id>/image_<n>.<ext>

Redis (fast access for admin UI):
  bug_reports:records      HASH  { <id> -> json-encoded record }
  bug_reports:index        ZSET  ordered by receivedAt timestamp
  bug_reports:queue        LIST  append-only ingest log (last 5000)

Endpoints
---------
Public (any authenticated or anonymous user):
  POST   /api/v1/bug-reports            submit a new bug report

Admin only (require_admin):
  GET    /api/v1/admin/bug-reports                  list (paginated, filterable)
  GET    /api/v1/admin/bug-reports/stats            summary counts
  GET    /api/v1/admin/bug-reports/{id}             detail
  GET    /api/v1/admin/bug-reports/{id}/images/{filename}   serve image (binary)
  PATCH  /api/v1/admin/bug-reports/{id}             update status / note
  DELETE /api/v1/admin/bug-reports/{id}             permanently delete
"""

import asyncio
import base64
import json
import os
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from auth import (
    AuthenticatedUser,
    get_current_user_optional,
    require_admin,
)

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["bug-reports"])

# ----------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------

BUG_REPORTS_DIR = Path(os.environ.get("BUG_REPORTS_DIR", "/data/bug_reports"))
REDIS_QUEUE_KEY = os.environ.get("BUG_REPORTS_REDIS_KEY", "bug_reports:queue")
REDIS_INDEX_KEY = os.environ.get("BUG_REPORTS_INDEX_KEY", "bug_reports:index")
REDIS_RECORDS_KEY = os.environ.get("BUG_REPORTS_RECORDS_KEY", "bug_reports:records")

MAX_DESCRIPTION_LENGTH = 8000
MAX_IMAGES = 5
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB per image
MAX_QUEUE_HISTORY = 5000
DEFAULT_LIST_LIMIT = 50
MAX_LIST_LIMIT = 200

ALLOWED_MIME = {"image/png", "image/jpeg", "image/webp", "image/gif"}
MIME_TO_EXT = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
}
EXT_TO_MIME = {v: k for k, v in MIME_TO_EXT.items()}

ReportStatus = Literal["open", "resolved", "dismissed"]
VALID_STATUSES: set[str] = {"open", "resolved", "dismissed"}


# ----------------------------------------------------------------------------
# Dependency injection
# ----------------------------------------------------------------------------

_redis_client = None


def set_redis_client(client) -> None:
    """Inyectar el cliente Redis (llamado desde main.py)."""
    global _redis_client
    _redis_client = client
    # Hidratar el hash desde filesystem al arrancar (best-effort, non-blocking).
    if client is not None:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_hydrate_records_from_disk(client))
        except RuntimeError:
            # No hay loop activo — la hidratación se hará bajo demanda
            pass


def get_redis():
    return _redis_client


# ----------------------------------------------------------------------------
# Pydantic models
# ----------------------------------------------------------------------------


class BugReportImage(BaseModel):
    name: str = Field(default="screenshot.png", max_length=180)
    dataUrl: str = Field(..., description="data:image/...;base64,... payload")
    size: int = Field(default=0, ge=0)


class BugReportContext(BaseModel):
    url: Optional[str] = None
    userAgent: Optional[str] = None
    viewport: Optional[Dict[str, int]] = None
    timestamp: Optional[str] = None


class BugReportRequest(BaseModel):
    description: str = Field(..., min_length=10, max_length=MAX_DESCRIPTION_LENGTH)
    images: List[BugReportImage] = Field(default_factory=list, max_length=MAX_IMAGES)
    context: Optional[BugReportContext] = None


class BugReportResponse(BaseModel):
    id: str
    status: str = "received"
    receivedAt: str


class StoredImage(BaseModel):
    filename: str
    mime: str
    size: int


class StoredReport(BaseModel):
    id: str
    user: Optional[str] = None
    userEmail: Optional[str] = None
    userName: Optional[str] = None
    description: str
    context: Optional[Dict[str, Any]] = None
    images: List[StoredImage] = Field(default_factory=list)
    imageCount: int = 0
    receivedAt: str
    remoteAddr: Optional[str] = None
    status: ReportStatus = "open"
    adminNote: Optional[str] = None
    resolvedAt: Optional[str] = None
    resolvedBy: Optional[str] = None


class BugReportListResponse(BaseModel):
    total: int
    open: int
    resolved: int
    dismissed: int
    items: List[StoredReport]
    limit: int
    offset: int


class BugReportStatsResponse(BaseModel):
    total: int
    open: int
    resolved: int
    dismissed: int
    last24h: int
    last7d: int


class BugReportUpdateRequest(BaseModel):
    status: Optional[ReportStatus] = None
    adminNote: Optional[str] = Field(default=None, max_length=4000)


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------


DATA_URL_RE = re.compile(r"^data:(image/[a-zA-Z+.\-]+);base64,(.+)$", re.DOTALL)
ID_RE = re.compile(r"^[a-f0-9]{12}$")
FILENAME_RE = re.compile(r"^[A-Za-z0-9._\-]{1,200}$")


def _decode_data_url(data_url: str) -> tuple[str, bytes]:
    """Decode a data:image/...;base64,... URL. Raises ValueError on bad input."""
    match = DATA_URL_RE.match(data_url.strip())
    if not match:
        raise ValueError("invalid data URL")
    mime = match.group(1).lower()
    if mime not in ALLOWED_MIME:
        raise ValueError(f"unsupported mime type {mime}")
    try:
        payload = base64.b64decode(match.group(2), validate=True)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"invalid base64 payload: {exc}") from exc
    if len(payload) > MAX_IMAGE_BYTES:
        raise ValueError("image exceeds maximum size of 5 MB")
    return mime, payload


def _safe_filename(name: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._\-]+", "_", name or "").strip("._")
    if not cleaned:
        return fallback
    return cleaned[:120]


def _validate_id(report_id: str) -> None:
    if not report_id or not ID_RE.match(report_id):
        raise HTTPException(status_code=400, detail="invalid report id")


def _record_dir(report_id: str) -> Path:
    return BUG_REPORTS_DIR / report_id


def _write_metadata(record: Dict[str, Any]) -> None:
    target = _record_dir(record["id"]) / "metadata.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record, indent=2), encoding="utf-8")


async def _store_record(redis_client, record: Dict[str, Any]) -> None:
    """Persist record to Redis (hash + sorted index + history list)."""
    if redis_client is None:
        return
    rid = record["id"]
    raw = json.dumps(record)
    received_at = record.get("receivedAt") or datetime.now(timezone.utc).isoformat()
    try:
        score = datetime.fromisoformat(received_at.replace("Z", "+00:00")).timestamp()
    except Exception:  # noqa: BLE001
        score = datetime.now(timezone.utc).timestamp()
    try:
        await redis_client.client.hset(REDIS_RECORDS_KEY, rid, raw)
        await redis_client.client.zadd(REDIS_INDEX_KEY, {rid: score})
        await redis_client.client.lpush(REDIS_QUEUE_KEY, raw)
        await redis_client.client.ltrim(REDIS_QUEUE_KEY, 0, MAX_QUEUE_HISTORY - 1)
    except Exception as exc:  # noqa: BLE001
        logger.warning("bug_report_redis_store_failed", report_id=rid, error=str(exc))


async def _load_record(redis_client, report_id: str) -> Optional[Dict[str, Any]]:
    """Load a single record from Redis or fall back to filesystem."""
    if redis_client is not None:
        try:
            raw = await redis_client.client.hget(REDIS_RECORDS_KEY, report_id)
            if raw:
                return json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            logger.warning("bug_report_redis_load_failed", report_id=report_id, error=str(exc))

    metadata_file = _record_dir(report_id) / "metadata.json"
    if metadata_file.exists():
        try:
            return json.loads(metadata_file.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("bug_report_fs_load_failed", report_id=report_id, error=str(exc))
    return None


async def _delete_record(redis_client, report_id: str) -> None:
    if redis_client is not None:
        try:
            await redis_client.client.hdel(REDIS_RECORDS_KEY, report_id)
            await redis_client.client.zrem(REDIS_INDEX_KEY, report_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("bug_report_redis_delete_failed", report_id=report_id, error=str(exc))

    record_dir = _record_dir(report_id)
    if record_dir.exists():
        try:
            shutil.rmtree(record_dir)
        except Exception as exc:  # noqa: BLE001
            logger.warning("bug_report_fs_delete_failed", report_id=report_id, error=str(exc))


async def _list_record_ids(
    redis_client,
    limit: int,
    offset: int,
) -> List[str]:
    """Return ids ordered by receivedAt DESC. Falls back to filesystem if Redis empty."""
    if redis_client is not None:
        try:
            ids = await redis_client.client.zrevrange(
                REDIS_INDEX_KEY, offset, offset + limit - 1
            )
            if ids:
                return [i.decode() if isinstance(i, bytes) else i for i in ids]
        except Exception as exc:  # noqa: BLE001
            logger.warning("bug_report_redis_list_failed", error=str(exc))

    # Filesystem fallback (rare path — only if Redis is empty).
    if not BUG_REPORTS_DIR.exists():
        return []
    entries: List[tuple[float, str]] = []
    for child in BUG_REPORTS_DIR.iterdir():
        if not child.is_dir() or not ID_RE.match(child.name):
            continue
        metadata = child / "metadata.json"
        if not metadata.exists():
            continue
        try:
            score = metadata.stat().st_mtime
        except OSError:
            score = 0.0
        entries.append((score, child.name))
    entries.sort(reverse=True)
    return [eid for _, eid in entries[offset : offset + limit]]


async def _hydrate_records_from_disk(redis_client) -> None:
    """One-shot best-effort migration: ensure every metadata.json on disk is in Redis."""
    try:
        existing = await redis_client.client.hkeys(REDIS_RECORDS_KEY)
        existing_ids = {(i.decode() if isinstance(i, bytes) else i) for i in (existing or [])}
    except Exception as exc:  # noqa: BLE001
        logger.warning("bug_report_hydrate_inspect_failed", error=str(exc))
        existing_ids = set()

    if not BUG_REPORTS_DIR.exists():
        return

    hydrated = 0
    for child in BUG_REPORTS_DIR.iterdir():
        if not child.is_dir() or not ID_RE.match(child.name):
            continue
        if child.name in existing_ids:
            continue
        metadata_file = child / "metadata.json"
        if not metadata_file.exists():
            continue
        try:
            record = json.loads(metadata_file.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("bug_report_hydrate_parse_failed", report_id=child.name, error=str(exc))
            continue

        # Backfill new fields on legacy records.
        record.setdefault("status", "open")
        record.setdefault("adminNote", None)
        record.setdefault("resolvedAt", None)
        record.setdefault("resolvedBy", None)

        await _store_record(redis_client, record)
        # Refresh disk copy too so it stays in sync with the new schema.
        try:
            _write_metadata(record)
        except Exception:  # noqa: BLE001
            pass
        hydrated += 1

    if hydrated:
        logger.info("bug_report_hydrated_from_disk", count=hydrated)


async def _count_by_status(redis_client) -> Dict[str, int]:
    """Return counts {total, open, resolved, dismissed, last24h, last7d}."""
    counts = {"total": 0, "open": 0, "resolved": 0, "dismissed": 0, "last24h": 0, "last7d": 0}
    if redis_client is None:
        return counts
    try:
        now = datetime.now(timezone.utc).timestamp()
        # total + windowed counts come from the sorted index (cheap).
        counts["total"] = int(await redis_client.client.zcard(REDIS_INDEX_KEY) or 0)
        counts["last24h"] = int(
            await redis_client.client.zcount(REDIS_INDEX_KEY, now - 24 * 3600, now) or 0
        )
        counts["last7d"] = int(
            await redis_client.client.zcount(REDIS_INDEX_KEY, now - 7 * 24 * 3600, now) or 0
        )
        # status breakdown needs to scan the hash. For our volumes this is fine.
        raw_map = await redis_client.client.hgetall(REDIS_RECORDS_KEY)
        for raw in (raw_map or {}).values():
            try:
                rec = json.loads(raw)
            except Exception:  # noqa: BLE001
                continue
            st = rec.get("status", "open")
            if st in counts:
                counts[st] += 1
            else:
                counts["open"] += 1
    except Exception as exc:  # noqa: BLE001
        logger.warning("bug_report_stats_failed", error=str(exc))
    return counts


async def _notify_slack(payload: Dict[str, Any]) -> None:
    """Best-effort Slack webhook notification (env-gated, never raises)."""
    webhook_url = os.environ.get("SLACK_BUG_REPORT_WEBHOOK_URL")
    if not webhook_url:
        return

    summary_lines = [
        f":bug: *New bug report* `{payload['id']}`",
        f"*User:* {payload.get('userEmail') or payload.get('user') or 'anonymous'}",
        f"*URL:* {(payload.get('context') or {}).get('url', 'n/a')}",
        f"*Images:* {payload.get('imageCount', 0)}",
        "",
        "```",
        (payload.get("description") or "")[:1500],
        "```",
    ]
    message = {"text": "\n".join(summary_lines)}

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            await client.post(webhook_url, json=message)
    except Exception as exc:  # noqa: BLE001
        logger.warning("bug_report_slack_failed", error=str(exc))


def _user_label(user: Optional[AuthenticatedUser]) -> Dict[str, Optional[str]]:
    if not user:
        return {"user": None, "userEmail": None, "userName": None}
    name = (user.display_name if hasattr(user, "display_name") else None)
    return {
        "user": user.id,
        "userEmail": getattr(user, "email", None),
        "userName": name,
    }


# ----------------------------------------------------------------------------
# Public endpoint: submit
# ----------------------------------------------------------------------------


@router.post(
    "/api/v1/bug-reports",
    response_model=BugReportResponse,
    status_code=201,
)
async def submit_bug_report(
    request: Request,
    payload: BugReportRequest,
    user: Optional[AuthenticatedUser] = Depends(get_current_user_optional),
    redis=Depends(get_redis),
):
    """
    Accept a structured bug report from the dashboard toolbar.

    Auth is optional: anonymous reports are still stored, but the
    payload records the user id / email / name when available.
    """
    report_id = uuid.uuid4().hex[:12]
    received_at = datetime.now(timezone.utc).isoformat()

    images_meta: List[Dict[str, Any]] = []

    try:
        _record_dir(report_id).mkdir(parents=True, exist_ok=True)
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "bug_report_dir_create_failed",
            path=str(BUG_REPORTS_DIR),
            error=str(exc),
        )
        raise HTTPException(status_code=500, detail="bug report storage unavailable")

    for idx, image in enumerate(payload.images):
        try:
            mime, blob = _decode_data_url(image.dataUrl)
        except ValueError as exc:
            logger.warning(
                "bug_report_image_rejected",
                report_id=report_id,
                idx=idx,
                error=str(exc),
            )
            continue

        ext = MIME_TO_EXT[mime]
        original = _safe_filename(image.name, f"image_{idx}.{ext}")
        filename = f"image_{idx}_{original}"
        if not filename.lower().endswith(f".{ext}"):
            filename = f"{filename}.{ext}"
        filepath = _record_dir(report_id) / filename

        try:
            filepath.write_bytes(blob)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "bug_report_image_write_failed",
                report_id=report_id,
                error=str(exc),
            )
            continue

        images_meta.append(
            {
                "filename": filename,
                "mime": mime,
                "size": len(blob),
            }
        )

    user_info = _user_label(user)
    record: Dict[str, Any] = {
        "id": report_id,
        **user_info,
        "description": payload.description,
        "context": payload.context.model_dump() if payload.context else None,
        "images": images_meta,
        "imageCount": len(images_meta),
        "receivedAt": received_at,
        "remoteAddr": request.client.host if request.client else None,
        "status": "open",
        "adminNote": None,
        "resolvedAt": None,
        "resolvedBy": None,
    }

    try:
        _write_metadata(record)
    except Exception as exc:  # noqa: BLE001
        logger.error("bug_report_metadata_write_failed", report_id=report_id, error=str(exc))

    await _store_record(redis, record)
    await _notify_slack(record)

    logger.info(
        "bug_report_received",
        report_id=report_id,
        user_id=user_info["user"],
        image_count=len(images_meta),
        description_length=len(payload.description),
    )

    return BugReportResponse(id=report_id, receivedAt=received_at)


# ----------------------------------------------------------------------------
# Admin endpoints
# ----------------------------------------------------------------------------


@router.get(
    "/api/v1/admin/bug-reports",
    response_model=BugReportListResponse,
)
async def admin_list_bug_reports(
    limit: int = DEFAULT_LIST_LIMIT,
    offset: int = 0,
    status_filter: Optional[ReportStatus] = None,
    admin: AuthenticatedUser = Depends(require_admin),
    redis=Depends(get_redis),
):
    """Listado paginado de bug reports (newest first)."""
    limit = max(1, min(MAX_LIST_LIMIT, limit))
    offset = max(0, offset)

    counts = await _count_by_status(redis)

    items: List[StoredReport] = []
    if status_filter is None:
        ids = await _list_record_ids(redis, limit, offset)
        for rid in ids:
            rec = await _load_record(redis, rid)
            if not rec:
                continue
            rec.setdefault("status", "open")
            try:
                items.append(StoredReport(**rec))
            except Exception as exc:  # noqa: BLE001
                logger.warning("bug_report_invalid_record", report_id=rid, error=str(exc))
    else:
        # Filtrar por status requiere escanear el hash (volumen bajo, aceptable).
        if redis is not None:
            try:
                raw_map = await redis.client.hgetall(REDIS_RECORDS_KEY)
                # Recolectamos (score, record) y ordenamos por receivedAt DESC.
                rows: List[tuple[float, Dict[str, Any]]] = []
                for raw in (raw_map or {}).values():
                    try:
                        rec = json.loads(raw)
                    except Exception:  # noqa: BLE001
                        continue
                    if rec.get("status", "open") != status_filter:
                        continue
                    try:
                        score = datetime.fromisoformat(
                            (rec.get("receivedAt") or "").replace("Z", "+00:00")
                        ).timestamp()
                    except Exception:  # noqa: BLE001
                        score = 0.0
                    rows.append((score, rec))
                rows.sort(key=lambda x: x[0], reverse=True)
                for _, rec in rows[offset : offset + limit]:
                    rec.setdefault("status", "open")
                    try:
                        items.append(StoredReport(**rec))
                    except Exception:  # noqa: BLE001
                        pass
            except Exception as exc:  # noqa: BLE001
                logger.warning("bug_report_filter_failed", error=str(exc))

    return BugReportListResponse(
        total=counts["total"],
        open=counts["open"],
        resolved=counts["resolved"],
        dismissed=counts["dismissed"],
        items=items,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/api/v1/admin/bug-reports/stats",
    response_model=BugReportStatsResponse,
)
async def admin_bug_reports_stats(
    admin: AuthenticatedUser = Depends(require_admin),
    redis=Depends(get_redis),
):
    counts = await _count_by_status(redis)
    return BugReportStatsResponse(**counts)


@router.get(
    "/api/v1/admin/bug-reports/{report_id}",
    response_model=StoredReport,
)
async def admin_get_bug_report(
    report_id: str,
    admin: AuthenticatedUser = Depends(require_admin),
    redis=Depends(get_redis),
):
    _validate_id(report_id)
    record = await _load_record(redis, report_id)
    if not record:
        raise HTTPException(status_code=404, detail="bug report not found")
    record.setdefault("status", "open")
    return StoredReport(**record)


@router.get("/api/v1/admin/bug-reports/{report_id}/images/{filename}")
async def admin_get_bug_report_image(
    report_id: str,
    filename: str,
    admin: AuthenticatedUser = Depends(require_admin),
):
    _validate_id(report_id)
    if not FILENAME_RE.match(filename):
        raise HTTPException(status_code=400, detail="invalid filename")

    path = _record_dir(report_id) / filename
    # Resolve and ensure we stay within the report directory.
    try:
        resolved = path.resolve()
        resolved.relative_to(_record_dir(report_id).resolve())
    except (ValueError, OSError):
        raise HTTPException(status_code=400, detail="invalid filename")

    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=404, detail="image not found")

    ext = resolved.suffix.lstrip(".").lower()
    media_type = EXT_TO_MIME.get(ext, "application/octet-stream")
    return FileResponse(resolved, media_type=media_type, filename=filename)


@router.patch(
    "/api/v1/admin/bug-reports/{report_id}",
    response_model=StoredReport,
)
async def admin_update_bug_report(
    report_id: str,
    payload: BugReportUpdateRequest,
    admin: AuthenticatedUser = Depends(require_admin),
    redis=Depends(get_redis),
):
    _validate_id(report_id)
    record = await _load_record(redis, report_id)
    if not record:
        raise HTTPException(status_code=404, detail="bug report not found")

    changed = False

    if payload.status is not None:
        if payload.status not in VALID_STATUSES:
            raise HTTPException(status_code=400, detail="invalid status")
        if record.get("status") != payload.status:
            record["status"] = payload.status
            if payload.status in {"resolved", "dismissed"}:
                record["resolvedAt"] = datetime.now(timezone.utc).isoformat()
                record["resolvedBy"] = admin.id
            else:
                record["resolvedAt"] = None
                record["resolvedBy"] = None
            changed = True

    if payload.adminNote is not None:
        # Empty string clears the note.
        new_note = payload.adminNote.strip() or None
        if record.get("adminNote") != new_note:
            record["adminNote"] = new_note
            changed = True

    if changed:
        try:
            _write_metadata(record)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "bug_report_metadata_update_failed", report_id=report_id, error=str(exc)
            )
        await _store_record(redis, record)
        logger.info(
            "bug_report_updated",
            report_id=report_id,
            admin_id=admin.id,
            status=record.get("status"),
            has_note=record.get("adminNote") is not None,
        )

    record.setdefault("status", "open")
    return StoredReport(**record)


@router.delete("/api/v1/admin/bug-reports/{report_id}", status_code=204)
async def admin_delete_bug_report(
    report_id: str,
    admin: AuthenticatedUser = Depends(require_admin),
    redis=Depends(get_redis),
):
    _validate_id(report_id)
    record = await _load_record(redis, report_id)
    if not record:
        raise HTTPException(status_code=404, detail="bug report not found")
    await _delete_record(redis, report_id)
    logger.info("bug_report_deleted", report_id=report_id, admin_id=admin.id)
    return None
