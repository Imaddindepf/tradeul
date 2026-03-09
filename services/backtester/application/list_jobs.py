"""List and delete jobs for a user."""
from __future__ import annotations

from typing import Any

from application.ports import IJobRepository


def list_jobs(
    repo: IJobRepository,
    user_id: str,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    if not hasattr(repo, "list_job_ids_for_user"):
        return []
    job_ids = repo.list_job_ids_for_user(user_id, limit=limit, offset=offset)
    out = []
    for jid in job_ids:
        meta = repo.get_job(jid)
        if meta is not None:
            out.append(meta)
    return out


def delete_job(repo: IJobRepository, job_id: str, user_id: str | None) -> bool:
    meta = repo.get_job(job_id)
    if meta is None:
        return False
    if user_id is not None and meta.get("user_id") != user_id:
        return False
    repo.update_job(job_id, {"status": "cancelled", "message": "Deleted by user"})
    if hasattr(repo, "delete_result"):
        repo.delete_result(job_id)
    return True
