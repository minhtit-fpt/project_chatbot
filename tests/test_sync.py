"""Tests cho logs/sync_to_mysql — không kết nối MySQL thật.

Bug được bao phủ (phát hiện khi review production):
- Record ``type="feedback"`` (không có key ``question``/``answer``) lọt vào vòng
  insert → KeyError thoát khỏi ``sync()`` TRƯỚC ``conn.commit()`` → cả batch rollback,
  ``_mark_synced`` không chạy, record đó chặn mọi lần sync sau đó vĩnh viễn.
"""
import json

import pytest

from logs import sync_to_mysql


def _write_jsonl(path, records: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
        encoding="utf-8",
    )


def _message(qid: str, synced: bool = False) -> dict:
    return {
        "type": "message",
        "message_id": qid,
        "session_id": "sess-1",
        "timestamp": "2026-08-08T08:18:02",
        "question": f"câu hỏi {qid}",
        "answer": f"trả lời {qid}",
        "sources": [],
        "latency_ms": 1234,
        "synced": synced,
    }


def _feedback(qid: str) -> dict:
    # Cố ý KHÔNG có question/answer — đúng như log_feedback() ghi ra.
    return {
        "type": "feedback",
        "message_id": qid,
        "session_id": "sess-1",
        "timestamp": "2026-08-08T08:18:05",
        "rating": "up",
        "comment": "",
        "synced": False,
    }


# ── _read_pending ────────────────────────────────────────────────────────────

def test_read_pending_skips_feedback_records(tmp_path, monkeypatch):
    store = tmp_path / "conversations.jsonl"
    _write_jsonl(store, [_message("m1"), _feedback("m1"), _message("m2")])
    monkeypatch.setattr(sync_to_mysql, "_STORE_PATH", store)

    records, indices = sync_to_mysql._read_pending()

    assert [r["message_id"] for r in records] == ["m1", "m2"]
    assert all(r["type"] == "message" for r in records)
    assert indices == [0, 2]  # dòng 1 (feedback) bị bỏ qua, index vẫn khớp dòng file


def test_read_pending_treats_missing_type_as_message(tmp_path, monkeypatch):
    """Record cũ ghi trước khi có field `type` vẫn phải được sync (tương thích ngược)."""
    store = tmp_path / "conversations.jsonl"
    legacy = _message("cu")
    del legacy["type"]
    _write_jsonl(store, [legacy])
    monkeypatch.setattr(sync_to_mysql, "_STORE_PATH", store)

    records, _ = sync_to_mysql._read_pending()

    assert [r["message_id"] for r in records] == ["cu"]


def test_read_pending_ignores_already_synced(tmp_path, monkeypatch):
    store = tmp_path / "conversations.jsonl"
    _write_jsonl(store, [_message("da-sync", synced=True), _message("chua-sync")])
    monkeypatch.setattr(sync_to_mysql, "_STORE_PATH", store)

    records, indices = sync_to_mysql._read_pending()

    assert [r["message_id"] for r in records] == ["chua-sync"]
    assert indices == [1]


# ── sync(): một record méo không được kéo sập cả batch ────────────────────────

class _FakeCursor:
    def __init__(self, sink: list) -> None:
        self._sink = sink

    def execute(self, sql: str, params: tuple | None = None) -> None:
        if params is None:  # CREATE TABLE
            return
        self._sink.append(params)

    def close(self) -> None:
        pass


class _FakeConn:
    def __init__(self, sink: list) -> None:
        self._sink = sink
        self.committed = False
        self.closed = False

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self._sink)

    def commit(self) -> None:
        self.committed = True

    def close(self) -> None:
        self.closed = True


def test_sync_survives_malformed_record_and_still_commits(tmp_path, monkeypatch):
    """Record thiếu key chỉ làm hỏng chính nó — batch vẫn commit và mark synced."""
    store = tmp_path / "conversations.jsonl"
    broken = _message("hong")
    del broken["question"]  # mô phỏng record méo lọt qua được bộ lọc type
    _write_jsonl(store, [_message("ok1"), broken, _message("ok2")])
    monkeypatch.setattr(sync_to_mysql, "_STORE_PATH", store)

    inserted: list[tuple] = []
    conn = _FakeConn(inserted)
    monkeypatch.setattr(sync_to_mysql, "_get_conn", lambda: conn)

    marked: list[set] = []
    monkeypatch.setattr(sync_to_mysql, "_mark_synced", lambda idx: marked.append(idx))

    sync_to_mysql.sync()

    assert [p[2] for p in inserted] == ["câu hỏi ok1", "câu hỏi ok2"]
    assert conn.committed, "commit phải chạy dù có record méo"
    assert marked == [{0, 2}], "chỉ dòng insert thành công được đánh dấu synced"


def test_sync_with_feedback_in_file_does_not_raise(tmp_path, monkeypatch):
    """Regression: một feedback duy nhất từng đủ để chặn sync vĩnh viễn."""
    store = tmp_path / "conversations.jsonl"
    _write_jsonl(store, [_message("m1"), _feedback("m1")])
    monkeypatch.setattr(sync_to_mysql, "_STORE_PATH", store)

    inserted: list[tuple] = []
    conn = _FakeConn(inserted)
    monkeypatch.setattr(sync_to_mysql, "_get_conn", lambda: conn)
    monkeypatch.setattr(sync_to_mysql, "_mark_synced", lambda idx: None)

    sync_to_mysql.sync()  # trước fix: KeyError

    assert len(inserted) == 1
    assert conn.committed


def test_sync_no_pending_does_not_connect(tmp_path, monkeypatch):
    store = tmp_path / "conversations.jsonl"
    _write_jsonl(store, [_feedback("m1")])  # chỉ có feedback → không có gì để insert
    monkeypatch.setattr(sync_to_mysql, "_STORE_PATH", store)

    def _boom():
        pytest.fail("không được mở kết nối MySQL khi không có bản ghi cần sync")

    monkeypatch.setattr(sync_to_mysql, "_get_conn", _boom)

    sync_to_mysql.sync()
