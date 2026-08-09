"""Guard chặn input rác trước pipeline (plan-prod-log-fixes B.2).

Bất biến quan trọng nhất: THÀ BỎ SÓT CÒN HƠN CHẶN NHẦM. Nửa dưới của file là các
câu THẬT trong log production phải lọt qua — câu cụt hợp lệ và câu hỏi theo mã SKU.

Test thuần — không gọi API, không load index.
"""
import pytest

from rag import chat_engine
from rag.input_guard import GIBBERISH_REPLY, is_gibberish


# ── Rác thật trong log production (phải bị chặn) ───────────────────────────
@pytest.mark.parametrize("junk", [
    "Ehfubrfuehfbrfuehf",
    "Vhrfurhfurvfurhufrhfuhrufhrfu",
    "Beheuysydgh3vssgyggsgsy",
    "O",
    "",
    "   ",
    "?!!",
])
def test_junk_is_blocked(junk):
    assert is_gibberish(junk) is True


# ── Câu hỏi thật của khách (KHÔNG được chặn) ───────────────────────────────
@pytest.mark.parametrize("valid", [
    "giá bao nhiêu?",
    "Tôi ở HN",
    "18.000 BTU",
    "5.",
    "014040",
    "SJ-FXP560V-BK",
    "u9bkh khác gì xu9bkh",
    "Model: R-29D2(G/R)VN",
    "Robot Hút Bụi Midea MV15ULTRAAPBK",
    "điều hoà daikin 12000 btu giá bao nhiêu",
    "chinh sach bao hanh the nao",
    "khuyenmaithang nay co gi",
    "dienmaythienphu co ship ra hai phong khong",
])
def test_valid_question_not_blocked(valid):
    assert is_gibberish(valid) is False


# ── Tích hợp answer(): rác không tốn API, nhưng VẪN được log ───────────────
class _ExplodingRetriever:
    """Mọi lần chạm vào retriever đều là lỗi — rác không được đi tới đây."""

    def search(self, question):  # pragma: no cover - chỉ để nổ nếu bị gọi
        raise AssertionError("retriever không được gọi cho input rác")

    def unmatched_model_codes(self, question):  # pragma: no cover
        raise AssertionError("retriever không được gọi cho input rác")


def test_junk_answer_skips_pipeline_but_is_logged(monkeypatch):
    logged = []
    monkeypatch.setattr(chat_engine, "get_retriever", lambda: _ExplodingRetriever())
    monkeypatch.setattr(
        chat_engine, "_generate_answer",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("không được gọi LLM")),
    )
    monkeypatch.setattr(chat_engine, "log_conversation", lambda *a, **k: logged.append(a))
    monkeypatch.setattr(chat_engine, "notify_message", lambda *a, **k: None)

    result = chat_engine.answer("Ehfubrfuehfbrfuehf", "sess-junk")

    assert result["answer"] == GIBBERISH_REPLY
    assert result["sources"] == []
    assert len(logged) == 1  # B.2.3 — vẫn đo được tỉ lệ rác, không nuốt im lặng
    # Rác KHÔNG được vào history, nếu không planner lượt sau bị đầu độc.
    assert chat_engine._history_store.get("sess-junk") == []
