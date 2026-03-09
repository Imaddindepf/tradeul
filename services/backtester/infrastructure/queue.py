"""Redis-backed job queue (LPUSH / BRPOP)."""
from __future__ import annotations

import json
from typing import Any

import redis


class RedisJobQueue:
    def __init__(self, redis_url: str, queue_name: str = "backtester:jobs"):
        self._client = redis.from_url(redis_url, decode_responses=True)
        self._queue = queue_name

    def enqueue(self, job_id: str, payload: dict[str, Any]) -> None:
        msg = json.dumps({"job_id": job_id, "payload": payload})
        self._client.lpush(self._queue, msg)

    def dequeue(self, timeout_seconds: int = 0) -> tuple[str, dict[str, Any]] | None:
        if timeout_seconds <= 0:
            raw = self._client.rpop(self._queue)
        else:
            pair = self._client.brpop(self._queue, timeout=timeout_seconds)
            raw = pair[1] if pair else None
        if raw is None:
            return None
        data = json.loads(raw)
        return data["job_id"], data["payload"]
