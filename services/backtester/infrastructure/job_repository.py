"""Redis-backed job repository."""
from __future__ import annotations

import json
import time
from typing import Any

import redis

from core.models import BacktestResponse


def _key_meta(job_id: str) -> str:
    return f"backtester:job:{job_id}:meta"


def _key_result(job_id: str) -> str:
    return f"backtester:job:{job_id}:result"


def _key_user_jobs(user_id: str) -> str:
    return f"backtester:user:{user_id}:jobs"


def _key_user_running(user_id: str) -> str:
    return f"backtester:user:{user_id}:running"


class RedisJobRepository:
    def __init__(self, redis_url: str, result_ttl_seconds: int = 7 * 24 * 3600):
        self._client = redis.from_url(redis_url, decode_responses=True)
        self._result_ttl = result_ttl_seconds

    def set_job(self, job_id: str, data: dict[str, Any], ttl_seconds: int | None = None) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self._result_ttl
        key = _key_meta(job_id)
        self._client.setex(key, ttl, json.dumps(data))

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        key = _key_meta(job_id)
        raw = self._client.get(key)
        if raw is None:
            return None
        return json.loads(raw)

    def update_job(self, job_id: str, updates: dict[str, Any]) -> None:
        data = self.get_job(job_id)
        if data is None:
            return
        data.update(updates)
        ttl = self._client.ttl(_key_meta(job_id))
        if ttl <= 0:
            ttl = self._result_ttl
        self._client.setex(_key_meta(job_id), ttl, json.dumps(data))

    def set_result(self, job_id: str, response: BacktestResponse, ttl_seconds: int | None = None) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self._result_ttl
        key = _key_result(job_id)
        self._client.setex(key, ttl, response.model_dump_json())

    def get_result(self, job_id: str) -> BacktestResponse | None:
        key = _key_result(job_id)
        raw = self._client.get(key)
        if raw is None:
            return None
        return BacktestResponse.model_validate_json(raw)

    def set_error(self, job_id: str, error_message: str, ttl_seconds: int | None = None) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self._result_ttl
        key = _key_meta(job_id)
        existing = self.get_job(job_id)
        if existing is not None:
            uid = existing.get("user_id")
            if uid:
                self._client.srem(_key_user_running(uid), job_id)
            existing["status"] = "failed"
            existing["error"] = error_message
            self._client.setex(key, ttl, json.dumps(existing))

    def add_job_to_user(self, user_id: str, job_id: str, created_at: float) -> None:
        key = _key_user_jobs(user_id)
        self._client.zadd(key, {job_id: created_at})
        self._client.expire(key, self._result_ttl)

    def add_to_running(self, user_id: str, job_id: str) -> None:
        self._client.sadd(_key_user_running(user_id), job_id)
        self._client.expire(_key_user_running(user_id), 24 * 3600)

    def remove_from_running(self, user_id: str, job_id: str) -> None:
        self._client.srem(_key_user_running(user_id), job_id)

    def count_running(self, user_id: str) -> int:
        return self._client.scard(_key_user_running(user_id))

    def count_jobs_today(self, user_id: str) -> int:
        key = _key_user_jobs(user_id)
        now = time.time()
        day_start = now - (now % 86400)
        return self._client.zcount(key, day_start, "+inf")

    def list_job_ids_for_user(
        self, user_id: str, limit: int = 50, offset: int = 0
    ) -> list[str]:
        key = _key_user_jobs(user_id)
        ids = self._client.zrevrange(key, offset, offset + limit - 1)
        return list(ids) if ids else []

    def delete_result(self, job_id: str) -> None:
        self._client.delete(_key_result(job_id))
