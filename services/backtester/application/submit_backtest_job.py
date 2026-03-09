"""Submit a backtest job to the queue."""
from __future__ import annotations

import time
import uuid
from typing import Any

from application.ports import IJobQueue, IJobRepository


def submit_backtest_job(
    repo: IJobRepository,
    queue: IJobQueue,
    job_type: str,
    payload: dict[str, Any],
    user_id: str | None = None,
    max_concurrent_per_user: int = 2,
    max_per_day_per_user: int = 0,
) -> str:
    if user_id:
        running = getattr(repo, "count_running", lambda u: 0)(user_id)
        if running >= max_concurrent_per_user:
            raise ValueError(
                f"Too many concurrent backtests (limit={max_concurrent_per_user}). "
                "Wait for one to finish."
            )
        if max_per_day_per_user > 0:
            today = getattr(repo, "count_jobs_today", lambda u: 0)(user_id)
            if today >= max_per_day_per_user:
                raise ValueError(
                    f"Daily limit reached ({max_per_day_per_user} jobs per day)."
                )
    job_id = str(uuid.uuid4())
    created_at = time.time()
    meta = {
        "job_id": job_id,
        "status": "queued",
        "type": job_type,
        "user_id": user_id,
        "progress_pct": 0,
        "message": "Queued",
        "created_at": created_at,
    }
    repo.set_job(job_id, meta)
    if user_id and hasattr(repo, "add_job_to_user"):
        repo.add_job_to_user(user_id, job_id, created_at)
    queue.enqueue(job_id, {"type": job_type, "payload": payload})
    return job_id
