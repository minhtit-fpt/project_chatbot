"""
Retry utilities cho Gemini API calls.
Xử lý 503 Service Unavailable và 429 Resource Exhausted bằng
exponential backoff + full jitter.

Logic chọn model nằm trong chat_engine.py (mỗi retry = 1 model khác).
Module này chỉ cung cấp: is_retryable(), wait_seconds(), call_with_retry().
"""

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


def is_retryable(exc: Exception) -> bool:
    """Trả về True nếu exception là lỗi tạm thời có thể retry."""
    msg = str(exc).lower()
    return any(phrase in msg for phrase in _RETRYABLE_PHRASES)


def wait_seconds(attempt: int) -> float:
    """Full-jitter exponential backoff. attempt bắt đầu từ 0."""
    cap = min(config.GEMINI_RETRY_MAX_WAIT, config.GEMINI_RETRY_BASE_WAIT * (2 ** attempt))
    return random.uniform(0, cap)


def call_with_retry(
    fn: Callable[[], T],
    max_retries: int | None = None,
    base_wait: float | None = None,
) -> T:
    """Gọi fn() đồng bộ với retry (dùng cho embedder, code sync, và eval).

    max_retries / base_wait: nếu None thì lấy từ config (mặc định chatbot).
    Eval nên truyền max_retries=8, base_wait=5.0 để chờ lâu hơn giữa các retry.
    """
    _max = max_retries if max_retries is not None else config.GEMINI_MAX_RETRIES
    _base = base_wait if base_wait is not None else config.GEMINI_RETRY_BASE_WAIT
    last_exc: Exception | None = None
    for attempt in range(_max):
        try:
            return fn()
        except Exception as exc:
            if not is_retryable(exc):
                raise
            last_exc = exc
            cap = min(config.GEMINI_RETRY_MAX_WAIT, _base * (2 ** attempt))
            wait = random.uniform(0, cap)
            logger.warning(
                "Gemini API lỗi (attempt %d/%d): %s — retry sau %.1fs",
                attempt + 1, _max, exc, wait,
            )
            time.sleep(wait)
    raise RuntimeError(f"Gemini API thất bại sau {_max} lần thử") from last_exc
