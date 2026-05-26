"""Local conversation store — ghi Q&A ra file JSONL.

Chatbot chỉ dùng module này, không cần biết MySQL tồn tại.
File JSONL sẽ được sync lên MySQL bởi script riêng (logs/sync_to_mysql.py).

Format mỗi dòng:
    {"timestamp": "...", "question": "...", "answer": "...",
     "sources": [...], "latency_ms": 123, "synced": false}
"""
import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

import config

logger = logging.getLogger(__name__)

_STORE_PATH = config.INDEX_PATH.parent.parent / "logs" / "conversations.jsonl"
_write_lock = threading.Lock()


def _ensure_dir() -> None:
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_conversation(
    session_id: str,
    question: str,
    answer: str,
    sources: list[Any],
    latency_ms: int,
) -> None:
    """Ghi 1 bản ghi Q&A vào cuối file JSONL — thread-safe, non-blocking."""
    record = {
        "session_id": session_id,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "question": question,
        "answer": answer,
        "sources": sources,
        "latency_ms": latency_ms,
        "synced": False,
    }

    def _write() -> None:
        try:
            _ensure_dir()
            with _write_lock:
                with _STORE_PATH.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as exc:
            logger.warning("conversation_store write failed: %s", exc)

    threading.Thread(target=_write, daemon=True).start()


def get_store_path() -> Path:
    return _STORE_PATH
