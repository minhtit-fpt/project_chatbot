"""Unit tests cho tính năng nhớ hội thoại (conversation memory).

Bao phủ:
- SessionHistoryStore: append/get đúng thứ tự, giới hạn max_turns, TTL hết hạn,
  cô lập giữa các session, get trả bản sao (immutability), evict khi quá max_sessions.
- chat_engine._build_contents: ghép lịch sử + câu hỏi hiện tại thành contents đa lượt.
- chat_engine.answer: lượt sau trong cùng session được truyền lịch sử + bỏ qua
  cache chung (câu trả lời phụ thuộc ngữ cảnh).

Không gọi API thật — mock _generate_answer / retriever / log.
"""
from rag import chat_engine
from rag.history_store import SessionHistoryStore


# ── Helpers ──────────────────────────────────────────────────────────────────

def _store(max_turns=3, ttl=100.0, max_sessions=10):
    """Tạo store với đồng hồ giả để test TTL không cần sleep."""
    clock = {"t": 0.0}
    store = SessionHistoryStore(
        max_turns=max_turns,
        ttl=ttl,
        max_sessions=max_sessions,
        time_func=lambda: clock["t"],
    )
    return store, clock


class _StubRetriever:
    def search(self, question):
        return [{"title": "T", "path": "p.md", "content": "x", "score": 0.9, "metadata": {}}]


# ── SessionHistoryStore ──────────────────────────────────────────────────────

def test_history_append_and_get_in_order():
    store, _ = _store()
    store.append("a", "q1", "a1")
    store.append("a", "q2", "a2")
    hist = store.get("a")
    assert [t["question"] for t in hist] == ["q1", "q2"]
    assert [t["answer"] for t in hist] == ["a1", "a2"]


def test_history_missing_session_returns_empty():
    store, _ = _store()
    assert store.get("khong-ton-tai") == []


def test_history_keeps_only_last_max_turns():
    store, _ = _store(max_turns=2)
    for i in range(5):
        store.append("a", f"q{i}", f"a{i}")
    assert [t["question"] for t in store.get("a")] == ["q3", "q4"]


def test_history_sessions_are_isolated():
    store, _ = _store()
    store.append("a", "qa", "aa")
    store.append("b", "qb", "ab")
    assert [t["question"] for t in store.get("a")] == ["qa"]
    assert [t["question"] for t in store.get("b")] == ["qb"]


def test_history_expires_after_ttl():
    store, clock = _store(ttl=100.0)
    store.append("a", "q1", "a1")
    clock["t"] = 100.1  # quá TTL
    assert store.get("a") == []


def test_history_get_returns_copy_not_internal_state():
    store, _ = _store()
    store.append("a", "q1", "a1")
    hist = store.get("a")
    hist.append({"question": "x", "answer": "y"})  # mutate bản trả về
    hist[0]["question"] = "MUTATED"
    fresh = store.get("a")
    assert [t["question"] for t in fresh] == ["q1"]  # state nội bộ không đổi


def test_history_evicts_oldest_when_over_max_sessions():
    store, _ = _store(max_sessions=2)
    store.append("s1", "q", "a")
    store.append("s2", "q", "a")
    store.append("s3", "q", "a")  # vượt trần → s1 (cũ nhất) bị bỏ
    assert store.get("s1") == []
    assert [t["question"] for t in store.get("s2")] == ["q"]
    assert [t["question"] for t in store.get("s3")] == ["q"]


# ── _build_contents ──────────────────────────────────────────────────────────

def test_build_contents_includes_history_then_current():
    history = [{"question": "q1", "answer": "a1"}]
    contents = chat_engine._build_contents("CUR", history)
    assert [c.role for c in contents] == ["user", "model", "user"]
    assert [c.parts[0].text for c in contents] == ["q1", "a1", "CUR"]


def test_build_contents_empty_history_just_current():
    contents = chat_engine._build_contents("CUR", [])
    assert [c.role for c in contents] == ["user"]
    assert contents[0].parts[0].text == "CUR"


# ── answer() — truyền lịch sử + cache theo ngữ cảnh ──────────────────────────

def _patch_answer_env(monkeypatch):
    monkeypatch.setattr(chat_engine, "get_retriever", lambda: _StubRetriever())
    monkeypatch.setattr(chat_engine, "log_conversation", lambda *a, **k: None)
    monkeypatch.setattr(chat_engine, "notify_message", lambda *a, **k: None)
    chat_engine._response_cache = chat_engine._TTLCache(max_size=16, ttl=300)
    chat_engine._history_store = SessionHistoryStore(
        max_turns=10, ttl=300, max_sessions=10
    )


def test_answer_passes_history_on_followup(monkeypatch):
    _patch_answer_env(monkeypatch)
    seen = []

    def fake_gen(messages, history=None):
        seen.append(list(history or []))
        return f"ans-{len(seen)}"

    monkeypatch.setattr(chat_engine, "_generate_answer", fake_gen)

    chat_engine.answer("câu 1", "sess-X")
    chat_engine.answer("câu 2", "sess-X")

    assert seen[0] == []  # lượt đầu: chưa có lịch sử
    assert [t["question"] for t in seen[1]] == ["câu 1"]
    assert [t["answer"] for t in seen[1]] == ["ans-1"]


def test_answer_followup_bypasses_global_cache(monkeypatch):
    """Cùng câu chữ nhưng ở lượt có ngữ cảnh → phải gọi lại model, không lấy cache."""
    _patch_answer_env(monkeypatch)
    calls = []
    monkeypatch.setattr(
        chat_engine,
        "_generate_answer",
        lambda messages, history=None: calls.append(1) or "X",
    )

    r0 = chat_engine.answer("trùng", "other")  # lượt đầu session khác → set cache "trùng"
    chat_engine.answer("mở đầu", "sess-Y")      # tạo lịch sử cho sess-Y
    r2 = chat_engine.answer("trùng", "sess-Y")  # có lịch sử → bypass cache

    assert r0["cached"] is False
    assert r2["cached"] is False
    assert len(calls) == 3


def test_answer_first_turn_still_uses_cache(monkeypatch):
    """Lượt đầu (không ngữ cảnh) vẫn cache như cũ giữa các session khác nhau."""
    _patch_answer_env(monkeypatch)
    calls = []
    monkeypatch.setattr(
        chat_engine,
        "_generate_answer",
        lambda messages, history=None: calls.append(1) or "X",
    )

    r1 = chat_engine.answer("bảo hành mấy năm?", "s1")
    r2 = chat_engine.answer("  BẢO HÀNH mấy năm? ", "s2")  # khác hoa/thường + space

    assert r1["cached"] is False
    assert r2["cached"] is True
    assert len(calls) == 1
