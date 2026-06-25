"""Tests cho rag/followup.is_referential_followup + cổng cache trong chat_engine.

Bug thực tế: câu follow-up cụt "thế nên mua loại nào" (sau khi hỏi điều hòa) lọt vào
engine lúc history rỗng (FE không giữ session_id) → trúng đáp án máy giặt đã cache của
phiên khác. Guard này nhận diện câu phụ thuộc ngữ cảnh để BỎ QUA cache chung.
"""
import pytest

from rag import chat_engine
from rag.followup import is_referential_followup


# ── Heuristic nhận diện ──────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "question",
    [
        "thế nên mua loại nào",
        "vậy mua loại nào",
        "thế thì nên lấy cái nào",
        "nên mua loại nào",
        "loại nào tốt hơn",
        "cái nào rẻ hơn",
        "giá bao nhiêu",
        "bao nhiêu tiền",
        "giá cả thế nào",
        "còn cái kia thì sao",
        "mẫu đó còn hàng không",
        "loại đó bảo hành mấy năm",
    ],
)
def test_referential_followups_detected(question):
    assert is_referential_followup(question) is True


@pytest.mark.parametrize(
    "question",
    [
        "tôi đang hỏi về điều hoà, nên mua điều hòa cây loại nào",
        "điều hòa cây Daikin loại nào tốt",
        "máy giặt Samsung giá bao nhiêu",
        "bảo hành mấy năm",
        "tư vấn điều hòa",
        "chính sách đổi trả thế nào",
        "",
    ],
)
def test_self_contained_questions_not_flagged(question):
    # Có nêu rõ sản phẩm/chủ đề → tự đứng được → vẫn cache được bình thường.
    assert is_referential_followup(question) is False


# ── Cổng cache trong chat_engine.answer ──────────────────────────────────────

class _ACRetriever:
    """Retrieve trả tài liệu ĐIỀU HÒA (đúng nhóm khách đang hỏi)."""

    def search(self, question):
        return [{"title": "Điều hòa cây Daikin", "path": "dieu-hoa/Daikin-FVA.md",
                 "content": "x", "score": 0.9, "metadata": {}}]


def test_referential_followup_bypasses_poisoned_cache(monkeypatch):
    """History rỗng + câu follow-up cụt → KHÔNG phục vụ đáp án nhiễm chéo phiên."""
    monkeypatch.setattr(chat_engine, "get_retriever", lambda: _ACRetriever())
    monkeypatch.setattr(chat_engine, "plan_search_queries", lambda q, h, **kw: [q])
    monkeypatch.setattr(chat_engine, "log_conversation", lambda *a, **k: None)
    monkeypatch.setattr(chat_engine, "notify_message", lambda *a, **k: None)
    gen_calls = []
    monkeypatch.setattr(
        chat_engine,
        "_generate_answer",
        lambda messages, history=None: gen_calls.append(1) or "Đáp án điều hòa",
    )
    chat_engine._response_cache = chat_engine._TTLCache(max_size=16, ttl=300)
    # "Nhiễm" cache: một phiên máy giặt trước đó đã cache câu cụt này.
    chat_engine._response_cache.set(
        "thế nên mua loại nào",
        {"answer": "Đáp án MÁY GIẶT", "sources": [], "suggestions": []},
    )

    result = chat_engine.answer("thế nên mua loại nào", "sess-moi")

    assert result["cached"] is False                 # không lấy từ cache
    assert result["answer"] == "Đáp án điều hòa"      # retrieve lại, đúng nhóm
    assert len(gen_calls) == 1                        # đã gọi model thật
    # Cache cũ KHÔNG bị ghi đè bằng đáp án phụ thuộc ngữ cảnh.
    assert chat_engine._response_cache.get("thế nên mua loại nào")["answer"] == "Đáp án MÁY GIẶT"


def test_self_contained_question_still_cached(monkeypatch):
    """Câu tự đứng (nêu rõ sản phẩm) vẫn dùng cache chung như trước."""
    monkeypatch.setattr(chat_engine, "get_retriever", lambda: _ACRetriever())
    monkeypatch.setattr(chat_engine, "plan_search_queries", lambda q, h, **kw: [q])
    monkeypatch.setattr(chat_engine, "log_conversation", lambda *a, **k: None)
    monkeypatch.setattr(chat_engine, "notify_message", lambda *a, **k: None)
    gen_calls = []
    monkeypatch.setattr(
        chat_engine,
        "_generate_answer",
        lambda messages, history=None: gen_calls.append(1) or "Đáp án",
    )
    chat_engine._response_cache = chat_engine._TTLCache(max_size=16, ttl=300)

    r1 = chat_engine.answer("điều hòa cây Daikin loại nào tốt", "s1")
    r2 = chat_engine.answer("điều hòa cây Daikin loại nào tốt", "s2")

    assert len(gen_calls) == 1        # lượt 2 ăn cache, không gọi lại model
    assert r1["cached"] is False
    assert r2["cached"] is True
