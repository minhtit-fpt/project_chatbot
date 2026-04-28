"""
Retry helper cho Gemini API calls.
Xử lý 503 Service Unavailable và 429 Resource Exhausted bằng
exponential backoff + full jitter.
"""

import asyncio
import logging
import random
import time
from collections.abc import Callable
from typing import TypeVar

import config

logger = logging.getLogger(__name__)

T = TypeVar("T")

_RETRYABLE_PHRASES = (
    "503",
    "service unavailable",
    "resource exhausted",
    "429",
    "rate limit",
    "quota",
    "overloaded",
    "server error",
    "internal error",
)


def _is_retryable(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(phrase in msg for phrase in _RETRYABLE_PHRASES)


def _wait_seconds(attempt: int) -> float:
    """Full-jitter exponential backoff."""
    cap = min(config.GEMINI_RETRY_MAX_WAIT, config.GEMINI_RETRY_BASE_WAIT * (2 ** attempt))
    return random.uniform(0, cap)


def call_with_retry(fn: Callable[[], T]) -> T:
    """Gọi fn() đồng bộ với retry. Dùng cho code không phải async."""
    last_exc: Exception | None = None
    for attempt in range(config.GEMINI_MAX_RETRIES):
        try:
            return fn()
        except Exception as exc:
            if not _is_retryable(exc):
                raise
            last_exc = exc
            wait = _wait_seconds(attempt)
            logger.warning(
                "Gemini API lỗi (attempt %d/%d): %s — retry sau %.1fs",
                attempt + 1,
                config.GEMINI_MAX_RETRIES,
                exc,
                wait,
            )
            time.sleep(wait)
    raise RuntimeError(
        f"Gemini API thất bại sau {config.GEMINI_MAX_RETRIES} lần thử"
    ) from last_exc


async def async_call_with_retry(fn: Callable[[], T]) -> T:
    """Gọi fn() trong thread pool với retry async-safe."""
    last_exc: Exception | None = None
    for attempt in range(config.GEMINI_MAX_RETRIES):
        try:
            return await asyncio.to_thread(fn)
        except Exception as exc:
            if not _is_retryable(exc):
                raise
            last_exc = exc
            wait = _wait_seconds(attempt)
            logger.warning(
                "Gemini API lỗi (attempt %d/%d): %s — retry sau %.1fs",
                attempt + 1,
                config.GEMINI_MAX_RETRIES,
                exc,
                wait,
            )
            await asyncio.sleep(wait)
    raise RuntimeError(
        f"Gemini API thất bại sau {config.GEMINI_MAX_RETRIES} lần thử"
    ) from last_exc
