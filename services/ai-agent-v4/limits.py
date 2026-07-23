"""
Per-user request limits — throttle + input bounds for an expensive service.

The agent fans out to multiple LLM providers per query, so an unbounded caller
is a real cost/DoS vector. Two cheap guards:

  - `check_rate(user_id)` — Redis sliding-window counter shared across replicas.
    Fail-open: if Redis is unreachable we allow the request (never lock users
    out on an infra hiccup).
  - `MAX_QUERY_CHARS` — hard cap on query length (prompt-stuffing / cost).

Limits are generous by default and tunable via env; the point is a ceiling on
abuse, not friction for normal use.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

MAX_QUERY_CHARS = int(os.getenv("AGENT_MAX_QUERY_CHARS", "8000"))
_RATE_MAX = int(os.getenv("AGENT_RATE_MAX_PER_WINDOW", "30"))
_RATE_WINDOW_S = int(os.getenv("AGENT_RATE_WINDOW_S", "60"))


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after
        super().__init__(f"rate limit exceeded; retry after {retry_after}s")


async def check_rate(redis, user_id: str) -> None:
    """Raise RateLimitExceeded if `user_id` is over budget in the window.

    Uses a fixed-window counter keyed to the current window bucket. Cheap
    (INCR + EXPIRE) and good enough as an abuse ceiling. Fail-open on any
    Redis error.
    """
    if redis is None or not user_id:
        return
    try:
        bucket = int(time.time()) // _RATE_WINDOW_S
        key = f"ratelimit:agent:{user_id}:{bucket}"
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, _RATE_WINDOW_S * 2)
        if count > _RATE_MAX:
            retry_after = _RATE_WINDOW_S - (int(time.time()) % _RATE_WINDOW_S)
            raise RateLimitExceeded(max(1, retry_after))
    except RateLimitExceeded:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("rate limit check failed (fail-open): %s", exc)


def clamp_query(query: str) -> tuple[str, Optional[str]]:
    """Return (query, error). error is set if the query exceeds MAX_QUERY_CHARS."""
    if query is not None and len(query) > MAX_QUERY_CHARS:
        return query[:MAX_QUERY_CHARS], (
            f"La consulta supera el máximo de {MAX_QUERY_CHARS} caracteres."
        )
    return query, None
