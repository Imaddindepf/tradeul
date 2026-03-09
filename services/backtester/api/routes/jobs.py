"""Jobs API: submit, status, result, list, delete."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi import Header

from api.schemas import JobStatusResponse, SubmitJobRequest, SubmitJobResponse
from application.get_job_status import get_job_result, get_job_status
from application.submit_backtest_job import submit_backtest_job
from application.list_jobs import list_jobs as list_jobs_uc, delete_job as delete_job_uc

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


def _get_repo(request: Request):
    repo = getattr(request.app.state, "job_repository", None)
    if repo is None:
        raise HTTPException(503, "Job repository not available")
    return repo


def _get_queue(request: Request):
    queue = getattr(request.app.state, "job_queue", None)
    if queue is None:
        raise HTTPException(503, "Job queue not available")
    return queue


def _get_settings():
    from config import settings
    return settings


@router.post("", response_model=SubmitJobResponse)
def post_job(
    body: SubmitJobRequest,
    request: Request,
    x_user_id: str | None = Header(None, alias="X-User-Id"),
):
    """Enqueue a backtest job. Returns job_id for polling. Optional X-User-Id for limits."""
    repo = _get_repo(request)
    queue = _get_queue(request)
    settings = _get_settings()
    user_id = body.user_id or x_user_id
    job_type = body.type
    payload = body.request
    if job_type not in ("template", "code"):
        raise HTTPException(400, "type must be 'template' or 'code'")
    try:
        job_id = submit_backtest_job(
            repo,
            queue,
            job_type,
            payload,
            user_id=user_id,
            max_concurrent_per_user=settings.max_concurrent_jobs_per_user,
            max_per_day_per_user=settings.max_jobs_per_day_per_user or 0,
        )
    except ValueError as e:
        raise HTTPException(429, str(e))
    return SubmitJobResponse(job_id=job_id)


@router.get("", response_model=list)
def list_jobs(
    request: Request,
    user_id: str | None = None,
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    limit: int = 50,
    offset: int = 0,
):
    """List jobs for a user. Requires user_id query param or X-User-Id header."""
    uid = user_id or x_user_id
    if not uid:
        raise HTTPException(400, "user_id or X-User-Id required")
    repo = _get_repo(request)
    return list_jobs_uc(repo, uid, limit=limit, offset=offset)


@router.get("/{job_id}", response_model=JobStatusResponse)
def get_job(job_id: str, request: Request):
    """Get job status and, if completed, the result."""
    repo = _get_repo(request)
    meta = get_job_status(repo, job_id)
    if meta is None:
        raise HTTPException(404, "Job not found")
    result = None
    if meta.get("status") == "completed":
        bt_resp = get_job_result(repo, job_id)
        if bt_resp and bt_resp.result is not None:
            result = bt_resp.model_dump().get("result")
    return JobStatusResponse(
        job_id=meta.get("job_id", job_id),
        status=meta.get("status", "unknown"),
        type=meta.get("type"),
        user_id=meta.get("user_id"),
        progress_pct=meta.get("progress_pct", 0),
        message=meta.get("message"),
        result=result,
        error=meta.get("error"),
    )


@router.get("/{job_id}/result")
def get_job_result_endpoint(job_id: str, request: Request):
    """Get only the backtest result (when completed)."""
    repo = _get_repo(request)
    meta = get_job_status(repo, job_id)
    if meta is None:
        raise HTTPException(404, "Job not found")
    if meta.get("status") != "completed":
        raise HTTPException(409, f"Job not completed (status={meta.get('status')})")
    bt_resp = get_job_result(repo, job_id)
    if bt_resp is None:
        raise HTTPException(404, "Result not found")
    return bt_resp.model_dump()


@router.delete("/{job_id}", status_code=204)
def delete_job(
    job_id: str,
    request: Request,
    x_user_id: str | None = Header(None, alias="X-User-Id"),
):
    """Cancel or delete a job. With X-User-Id, only own jobs can be deleted."""
    repo = _get_repo(request)
    ok = delete_job_uc(repo, job_id, x_user_id)
    if not ok:
        raise HTTPException(404, "Job not found or not owned by you")
