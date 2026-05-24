"""Session-end auto-sync — debounce pattern.

Thay vì polling định kỳ, sync được trigger sau khi session kết thúc:
- Mỗi tin nhắn mới → reset timer N giây
- Khi im lặng đủ N giây (khách đã rời) → sync JSONL → MySQL

Không tốn tài nguyên khi không có hoạt động.
"""
import logging
import threading

logger = logging.getLogger(__name__)

SESSION_IDLE_SECONDS = 180  # sync sau N giây session im lặng

# session_id → Timer riêng cho từng session
_timers: dict[str, threading.Timer] = {}
_lock = threading.Lock()


def _do_sync(session_id: str) -> None:
    from logs.sync_to_mysql import sync
    logger.info("Session '%s' idle — triggering sync...", session_id[:8])
    with _lock:
        _timers.pop(session_id, None)
    try:
        sync()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Auto-sync failed (session %s): %s", session_id[:8], exc)


def notify_message(session_id: str) -> None:
    """Gọi mỗi khi chatbot xử lý xong 1 tin nhắn của session.

    Mỗi session có timer riêng — reset khi có tin nhắn mới trong session đó.
    Nhiều session song song hoạt động độc lập với nhau.
    """
    with _lock:
        old = _timers.get(session_id)
        if old is not None:
            old.cancel()
        t = threading.Timer(SESSION_IDLE_SECONDS, _do_sync, args=(session_id,))
        t.daemon = True
        t.start()
        _timers[session_id] = t
