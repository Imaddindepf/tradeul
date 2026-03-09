"""Get job status and optionally result."""
from __future__ import annotations

from typing import Any

from core.models import BacktestResponse

from application.ports import IJobRepository


def get_job_status(repo: IJobRepository, job_id: str) -> dict[str, Any] | None:
    return repo.get_job(job_id)


def get_job_result(repo: IJobRepository, job_id: str) -> BacktestResponse | None:
    return repo.get_result(job_id)
