"""Retry utilities cho Gemini API calls — dùng chung bởi chat_engine và eval."""
from __future__ import annotations

import logging
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)

_RETRYABLE_KEYWORDS = (
    "429",
    "503",
    "resource_exhausted",
    "quota",
    "unavailable",
    "rate limit",
    "too many requests",
    "internal error",
)


def is_retryable(exc: Exception) -> bool:
    """Trả về True nếu exception là lỗi transient đáng retry."""
    msg = str(exc).lower()
    return any(kw in msg for kw in _RETRYABLE_KEYWORDS)


def call_with_retry(
    fn: Callable[[], Any],
    max_retries: int = 3,
    base_wait: float = 1.0,
) -> Any:
    """Gọi fn() với exponential backoff khi gặp lỗi transient.

    Args:
        fn: callable không nhận tham số (dùng lambda để truyền args).
        max_retries: số lần retry tối đa (không tính lần đầu).
        base_wait: thời gian chờ giây cho retry đầu tiên; tăng gấp đôi mỗi lần.

    Returns:
        Kết quả của fn() khi thành công.

    Raises:
        Exception cuối cùng nếu vẫn thất bại sau tất cả retry.
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt >= max_retries or not is_retryable(exc):
                raise
            wait = base_wait * (2 ** attempt)
            logger.warning(
                "Retry %d/%d after %.1fs — %s", attempt + 1, max_retries, wait, exc
            )
            time.sleep(wait)
    raise last_exc  # type: ignore[misc]
