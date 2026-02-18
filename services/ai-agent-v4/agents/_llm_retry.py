"""
Centralized LLM retry logic with exponential backoff.

Google's official recommendation for handling 429 RESOURCE_EXHAUSTED errors:
https://cloud.google.com/blog/products/ai-machine-learning/learn-how-to-handle-429-resource-exhaustion-errors-in-your-llms

Uses tenacity with wait_random_exponential as recommended by Google.
All agents should use `llm_invoke_with_retry` instead of bare `llm.ainvoke()`.
"""
from __future__ import annotations

import logging
from typing import Any

from tenacity import (
    retry,
    wait_random_exponential,
    stop_after_attempt,
    retry_if_exception,
    before_sleep_log,
)

logger = logging.getLogger(__name__)


def _is_retryable(exc: BaseException) -> bool:
    """Check if the exception is a retryable rate limit / transient error."""
    msg = str(exc).lower()
    return any(kw in msg for kw in [
        "429", "resource_exhausted", "resource exhausted",
        "too many requests", "rate limit", "quota",
        "503", "service unavailable", "overloaded",
    ])


async def llm_invoke_with_retry(
    llm: Any,
    messages: list,
    *,
    max_retries: int = 5,
    max_wait: int = 60,
) -> Any:
    """Invoke an LLM with exponential backoff retry on rate limit errors.

    Args:
        llm: LangChain ChatModel instance (ChatGoogleGenerativeAI, etc.)
        messages: List of messages to send
        max_retries: Maximum number of retry attempts (default: 5)
        max_wait: Maximum wait time in seconds between retries (default: 60)

    Returns:
        LLM response object

    Raises:
        Original exception if all retries exhausted or error is not retryable.
    """

    @retry(
        retry=retry_if_exception(_is_retryable),
        wait=wait_random_exponential(multiplier=1, max=max_wait),
        stop=stop_after_attempt(max_retries),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def _invoke():
        return await llm.ainvoke(messages)

    return await _invoke()
