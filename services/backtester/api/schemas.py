"""Request/response schemas for jobs API."""
from typing import Any, Literal

from pydantic import BaseModel, Field


class SubmitJobRequest(BaseModel):
    type: Literal["template", "code"]
    request: dict[str, Any] = Field(..., description="BacktestRequest or CodeBacktestRequest as dict")
    user_id: str | None = Field(None, description="Optional user id for multi-tenant")


class SubmitJobResponse(BaseModel):
    job_id: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    type: str | None = None
    user_id: str | None = None
    progress_pct: float = 0
    message: str | None = None
    result: dict | None = None
    error: str | None = None
