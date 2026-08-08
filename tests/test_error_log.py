"""Tests cho log_error — ghi request /chat thất bại vào JSONL.

Bối cảnh: `log_conversation` chỉ chạy ở đường thành công, nên khách bị 503/500 trước
đây không để lại dấu vết nào ngoài `docker logs` (mất khi recreate container, không
đếm được). Record `type="error"` lấp chỗ đó — và KHÔNG được phá sync MySQL.
"""
import json

import pytest

from logs import conversation_store, sync_to_mysql


class _InlineThread:
    """Thay threading.Thread: chạy target ngay, để test khỏi phải chờ thread daemon."""

    def __init__(self, target, daemon=None, **kwargs) -> None:
        self._target = target

    def start(self) -> None:
        self._target()


@pytest.fixture
def store(tmp_path, monkeypatch):
    """JSONL tạm + ghi đồng bộ, tránh phụ thuộc thời gian."""
    path = tmp_path / "conversations.jsonl"
    monkeypatch.setattr(conversation_store, "_STORE_PATH", path)
    monkeypatch.setattr(conversation_store.threading, "Thread", _InlineThread)
    return path


def _records(path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


# ── log_error ────────────────────────────────────────────────────────────────

def test_log_error_writes_full_debug_context(store):
    conversation_store.log_error(
        session_id="sess-1",
        question="giá điều hòa Daikin bao nhiêu?",
        error_type="ServerError",
        detail="503 UNAVAILABLE. Model is overloaded.",
        status_code=503,
        latency_ms=812,
    )

    rec = _records(store)[0]
    assert rec["type"] == "error"
    assert rec["session_id"] == "sess-1"
    assert rec["question"] == "giá điều hòa Daikin bao nhiêu?"
    assert rec["error_type"] == "ServerError"
    assert rec["status_code"] == 503
    assert rec["latency_ms"] == 812
    assert rec["synced"] is False
    assert "UNAVAILABLE" in rec["detail"]
    # timestamp cùng format với record message: ISO 8601, timespec="seconds"
    assert len(rec["timestamp"]) == 19 and rec["timestamp"][10] == "T"


def test_log_error_truncates_long_detail(store):
    conversation_store.log_error(
        session_id="s",
        question="q",
        error_type="ValueError",
        detail="x" * 5000,  # traceback/payload upstream có thể rất dài
        status_code=500,
    )

    assert len(_records(store)[0]["detail"]) == 1000


def test_log_error_write_failure_does_not_raise(tmp_path, monkeypatch):
    """Ghi log không bao giờ được làm hỏng request đang phục vụ khách."""
    monkeypatch.setattr(conversation_store, "_STORE_PATH", tmp_path / "x.jsonl")
    monkeypatch.setattr(conversation_store.threading, "Thread", _InlineThread)
    monkeypatch.setattr(
        conversation_store, "_ensure_dir", lambda: (_ for _ in ()).throw(OSError("đĩa đầy"))
    )

    conversation_store.log_error("s", "q", "OSError", "d", 500)  # không được ném


# ── error record không được phá sync MySQL ───────────────────────────────────

def test_error_records_are_not_synced_to_mysql(store, monkeypatch):
    conversation_store.log_conversation("sess-1", "câu hỏi ok", "trả lời", [], 100, "m1")
    conversation_store.log_error("sess-1", "câu hỏi lỗi", "ServerError", "503", 503)

    monkeypatch.setattr(sync_to_mysql, "_STORE_PATH", store)
    records, indices = sync_to_mysql._read_pending()

    assert [r["question"] for r in records] == ["câu hỏi ok"]
    assert indices == [0]


def test_all_three_record_types_coexist(store):
    """message + feedback + error nằm chung một file, đọc lại được cả ba."""
    conversation_store.log_conversation("s", "q", "a", [], 10, "m1")
    conversation_store.log_feedback("m1", "s", "up", "tốt")
    conversation_store.log_error("s", "q2", "RuntimeError", "boom", 503)

    assert [r["type"] for r in _records(store)] == ["message", "feedback", "error"]


# ── POST /chat: mọi nhánh lỗi phải để lại record ─────────────────────────────
# TestClient KHÔNG dùng làm context manager để lifespan (nạp index thật) không chạy.

def _client_raising(monkeypatch, exc: Exception):
    from fastapi.testclient import TestClient

    import api.main as main

    async def _boom(question, session_id, *, skip_log=False):
        raise exc

    monkeypatch.setattr(main, "answer_async", _boom)
    return TestClient(main.app, raise_server_exceptions=False)


@pytest.mark.parametrize(
    "exc, expected_status",
    [
        (RuntimeError("Gemini hết chain"), 503),
        (FileNotFoundError("Index not found"), 503),
        (ValueError("lỗi lạ"), 500),
    ],
)
def test_chat_failure_writes_error_record(store, monkeypatch, exc, expected_status):
    client = _client_raising(monkeypatch, exc)

    resp = client.post("/chat", json={"question": "giá tivi Samsung?", "session_id": "s-1"})

    assert resp.status_code == expected_status
    rec = _records(store)[0]
    assert rec["type"] == "error"
    assert rec["status_code"] == expected_status
    assert rec["error_type"] == type(exc).__name__
    assert rec["question"] == "giá tivi Samsung?"
    assert rec["session_id"] == "s-1"


def test_chat_failure_respects_test_flag(store, monkeypatch):
    """`test: true` đã bỏ log ở đường thành công thì đường lỗi cũng phải bỏ."""
    client = _client_raising(monkeypatch, RuntimeError("boom"))

    resp = client.post("/chat", json={"question": "thử thôi", "test": True})

    assert resp.status_code == 503
    assert not store.exists() or _records(store) == []
