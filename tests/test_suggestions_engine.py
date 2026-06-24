"""Tests wiring gợi ý hỏi tiếp vào chat_engine.answer (Phase 2).

Bao phủ:
- stub model trả text có marker → result["suggestions"] đúng, result["answer"] sạch
  (không chứa marker), history-turn giữ lại phần gợi ý (để planner lượt sau thấy).
- stub không marker → suggestions = [].
- Cache: lượt đầu câu rộng được cache → cache hit trả lại cả suggestions.

Không gọi API thật — mock _generate_answer / retriever / log (giống test_history).
"""
import config
from rag import chat_engine
from rag.history_store import SessionDocCache, SessionHistoryStore


class _StubRetriever:
    def search(self, question):
        return [{"title": "T", "path": "p.md", "content": "x", "score": 0.9, "metadata": {}}]


def _patch_answer_env(monkeypatch):
    monkeypatch.setattr(chat_engine, "get_retriever", lambda: _StubRetriever())
    monkeypatch.setattr(chat_engine, "log_conversation", lambda *a, **k: None)
    monkeypatch.setattr(chat_engine, "notify_message", lambda *a, **k: None)
    monkeypatch.setattr(chat_engine, "plan_search_queries", lambda q, h, **kw: [q])
    chat_engine._response_cache = chat_engine._TTLCache(max_size=16, ttl=300)
    chat_engine._history_store = SessionHistoryStore(
        max_turns=10, ttl=300, max_sessions=10
    )
    chat_engine._doc_cache = SessionDocCache(ttl=300, max_sessions=10)


_RAW_WITH_MARKER = (
    "1. Điều hòa Daikin\n- Giá: 10.000.000 đ\n\n"
    f"{config.SUGGESTIONS_MARKER}\n"
    "- Phòng mình rộng khoảng bao nhiêu m² ạ?\n"
    "- Ngân sách dự kiến tầm bao nhiêu ạ?"
)


def test_answer_extracts_suggestions_and_cleans_answer(monkeypatch):
    _patch_answer_env(monkeypatch)
    monkeypatch.setattr(
        chat_engine, "_generate_answer", lambda messages, history=None: _RAW_WITH_MARKER
    )

    result = chat_engine.answer("tư vấn điều hòa", "broad")

    assert result["suggestions"] == [
        "Phòng mình rộng khoảng bao nhiêu m² ạ?",
        "Ngân sách dự kiến tầm bao nhiêu ạ?",
    ]
    assert config.SUGGESTIONS_MARKER not in result["answer"]
    assert result["answer"] == "1. Điều hòa Daikin\n- Giá: 10.000.000 đ"


def test_answer_history_turn_keeps_suggestions(monkeypatch):
    _patch_answer_env(monkeypatch)
    monkeypatch.setattr(
        chat_engine, "_generate_answer", lambda messages, history=None: _RAW_WITH_MARKER
    )

    chat_engine.answer("tư vấn điều hòa", "broad")
    history = chat_engine._history_store.get("broad")

    assert len(history) == 1
    assert config.SUGGESTIONS_MARKER in history[0]["answer"]
    assert "Phòng mình rộng khoảng bao nhiêu m² ạ?" in history[0]["answer"]


def test_answer_specific_question_no_suggestions(monkeypatch):
    _patch_answer_env(monkeypatch)
    monkeypatch.setattr(
        chat_engine,
        "_generate_answer",
        lambda messages, history=None: "Giá Daikin FVA100 là 25.000.000 đ.",
    )

    result = chat_engine.answer("giá Daikin FVA100", "specific")

    assert result["suggestions"] == []
    assert result["answer"] == "Giá Daikin FVA100 là 25.000.000 đ."


def test_cache_hit_returns_suggestions(monkeypatch):
    _patch_answer_env(monkeypatch)
    calls = []
    monkeypatch.setattr(
        chat_engine,
        "_generate_answer",
        lambda messages, history=None: calls.append(1) or _RAW_WITH_MARKER,
    )

    r1 = chat_engine.answer("tư vấn điều hòa", "s1")   # lượt đầu → set cache
    r2 = chat_engine.answer("tư vấn điều hòa", "s2")   # session khác, cùng câu → cache hit

    assert r1["cached"] is False
    assert r2["cached"] is True
    assert len(calls) == 1
    assert r2["suggestions"] == r1["suggestions"]
    assert r2["suggestions"] == [
        "Phòng mình rộng khoảng bao nhiêu m² ạ?",
        "Ngân sách dự kiến tầm bao nhiêu ạ?",
    ]
