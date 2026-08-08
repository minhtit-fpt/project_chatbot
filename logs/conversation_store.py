"""Local conversation store — ghi Q&A ra file JSONL.

Chatbot chỉ dùng module này, không cần biết MySQL tồn tại.
File JSONL sẽ được sync lên MySQL bởi script riêng (logs/sync_to_mysql.py).

Format mỗi dòng (type="message"):
    {"type": "message", "message_id": "...", "session_id": "...",
     "timestamp": "...", "question": "...", "answer": "...",
     "sources": [...], "latency_ms": 123, "synced": false}

Format mỗi dòng (type="feedback"):
    {"type": "feedback", "message_id": "...", "session_id": "...",
     "timestamp": "...", "rating": "up"|"down", "comment": "...", "synced": false}
"""
import json
import logging
import threading
from pathlib import Path
from typing import Any

import config

logger = logging.getLogger(__name__)

_STORE_PATH = config.INDEX_PATH.parent.parent / "logs" / "conversations.jsonl"
_write_lock = threading.Lock()


def get_write_lock() -> threading.Lock:
    """Lock bảo vệ ghi vào JSONL store.

    sync_to_mysql._mark_synced() phải dùng CÙNG lock này khi đọc-sửa-ghi đè
    cả file, nếu không dòng vừa append từ chatbot có thể bị mất.
    """
    return _write_lock


def _ensure_dir() -> None:
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)


def _append_record(record: dict, what: str) -> None:
    """Ghi 1 record xuống cuối JSONL trong thread riêng — thread-safe, non-blocking.

    Ghi log không bao giờ được làm hỏng request đang phục vụ khách, nên lỗi ghi chỉ
    được cảnh báo chứ không ném lên. ``what`` chỉ dùng cho thông điệp cảnh báo.
    """
    def _write() -> None:
        try:
            _ensure_dir()
            with _write_lock:
                with _STORE_PATH.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as exc:
            logger.warning("conversation_store %s write failed: %s", what, exc)

    threading.Thread(target=_write, daemon=True).start()


def log_conversation(
    session_id: str,
    question: str,
    answer: str,
    sources: list[Any],
    latency_ms: int,
    message_id: str | None = None,
) -> None:
    """Ghi 1 bản ghi Q&A vào cuối file JSONL — thread-safe, non-blocking."""
    record = {
        "type": "message",
        "message_id": message_id or "",
        "session_id": session_id,
        "timestamp": config.now_local().isoformat(timespec="seconds"),
        "question": question,
        "answer": answer,
        "sources": sources,
        "latency_ms": latency_ms,
        "synced": False,
    }
    _append_record(record, "message")


def log_feedback(
    message_id: str,
    session_id: str,
    rating: str,
    comment: str | None = None,
) -> None:
    """Ghi feedback (thumbs up/down) của user vào JSONL — thread-safe, non-blocking."""
    record = {
        "type": "feedback",
        "message_id": message_id,
        "session_id": session_id,
        "timestamp": config.now_local().isoformat(timespec="seconds"),
        "rating": rating,
        "comment": comment or "",
        "synced": False,
    }
    _append_record(record, "feedback")


def log_error(
    session_id: str,
    question: str,
    error_type: str,
    detail: str,
    status_code: int,
    latency_ms: int = 0,
) -> None:
    """Ghi 1 request /chat THẤT BẠI vào JSONL — thread-safe, non-blocking.

    Vì sao cần: ``log_conversation`` chỉ chạy khi trả lời thành công, nên khách bị
    503/500 trước đây không để lại dấu vết nào ngoài ``docker logs`` (mất khi recreate
    container, không đếm được). Có record này mới trả lời được "hôm qua bao nhiêu khách
    bị lỗi, hỏi câu gì".

    ``detail`` là thông điệp gốc từ upstream (Gemini) — chỉ dùng nội bộ, KHÔNG trả về
    cho khách. Record ``type="error"`` bị ``sync_to_mysql._read_pending`` bỏ qua nên
    không vào bảng ``conversations``; đọc bằng grep/jq trên JSONL.
    """
    record = {
        "type": "error",
        "session_id": session_id,
        "timestamp": config.now_local().isoformat(timespec="seconds"),
        "question": question,
        "error_type": error_type,
        "detail": detail[:1000],  # chặn trần: traceback/payload upstream có thể rất dài
        "status_code": status_code,
        "latency_ms": latency_ms,
        "synced": False,
    }
    _append_record(record, "error")


def get_store_path() -> Path:
    return _STORE_PATH
