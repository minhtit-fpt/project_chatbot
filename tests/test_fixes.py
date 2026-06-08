"""Unit tests cho các bug đã sửa từ vòng review (không gọi API thật).

Bao phủ:
- to_vault_relative: watcher dùng path tương đối khớp build_index (bug CRITICAL).
- _generate_answer: guard resp.text=None + rớt model chain + fallback (bug HIGH).
- answer() cache: lượt hỏi trùng dùng cache, mỗi lượt vẫn sinh message_id riêng (Fix #4).
"""
import pytest

import config
from indexer import obsidian_loader
from rag import chat_engine


# ── to_vault_relative ────────────────────────────────────────────────────────

def test_to_vault_relative_in_vault_returns_relative():
    abs_path = config.OBSIDIAN_VAULT_PATH / "tivi" / "Samsung-X.md"
    rel = obsidian_loader.to_vault_relative(abs_path)
    # Không còn prefix vault — path tương đối ngắn gọn, khớp load_vault.
    assert "Samsung-X.md" in rel
    assert str(config.OBSIDIAN_VAULT_PATH) not in rel


def test_to_vault_relative_outside_vault_falls_back_absolute(tmp_path):
    outside = tmp_path / "ngoai-vault.md"
    rel = obsidian_loader.to_vault_relative(outside)
    assert rel == str(outside)


# ── _generate_answer (model chain + None guard) ──────────────────────────────

class _FakeResp:
    def __init__(self, text):
        self.text = text


def _patch_chain(monkeypatch, models):
    monkeypatch.setattr(config, "CHAT_MODEL_CHAIN", models)


def test_generate_answer_returns_text_on_success(monkeypatch):
    _patch_chain(monkeypatch, ["m1"])
    monkeypatch.setattr(
        chat_engine._client.models,
        "generate_content",
        lambda **kw: _FakeResp("Xin chào"),
    )
    assert chat_engine._generate_answer("hỏi") == "Xin chào"


def test_generate_answer_none_text_falls_back(monkeypatch):
    """resp.text=None ở mọi model → trả FALLBACK_ANSWER chứ không crash."""
    _patch_chain(monkeypatch, ["m1", "m2"])
    monkeypatch.setattr(
        chat_engine._client.models,
        "generate_content",
        lambda **kw: _FakeResp(None),
    )
    assert chat_engine._generate_answer("hỏi") == chat_engine.FALLBACK_ANSWER


def test_generate_answer_skips_to_next_model_on_empty(monkeypatch):
    """Model đầu trả rỗng → rớt sang model sau trả nội dung."""
    _patch_chain(monkeypatch, ["bad", "good"])
    calls = []

    def fake_generate(**kw):
        calls.append(kw["model"])
        return _FakeResp("" if kw["model"] == "bad" else "OK")

    monkeypatch.setattr(chat_engine._client.models, "generate_content", fake_generate)
    assert chat_engine._generate_answer("hỏi") == "OK"
    assert calls == ["bad", "good"]


def test_generate_answer_raises_on_persistent_transient(monkeypatch):
    """Lỗi transient (429) ở mọi model → raise để API trả 503."""
    _patch_chain(monkeypatch, ["m1"])
    monkeypatch.setattr(chat_engine, "_PER_MODEL_RETRIES", 0)

    def boom(**kw):
        raise RuntimeError("429 rate limit exceeded")

    monkeypatch.setattr(chat_engine._client.models, "generate_content", boom)
    with pytest.raises(RuntimeError):
        chat_engine._generate_answer("hỏi")


# ── answer() cache ───────────────────────────────────────────────────────────

class _StubRetriever:
    def search(self, question):
        return [{"title": "Bảo hành", "path": "Chinh-sach-bao-hanh.md",
                 "content": "x", "score": 0.9, "metadata": {}}]


def test_answer_uses_cache_on_repeat(monkeypatch):
    # Tránh phụ thuộc index.json / API / log thật.
    monkeypatch.setattr(chat_engine, "get_retriever", lambda: _StubRetriever())
    gen_calls = []
    monkeypatch.setattr(
        chat_engine,
        "_generate_answer",
        lambda messages: gen_calls.append(1) or "Đáp án",
    )
    monkeypatch.setattr(chat_engine, "log_conversation", lambda *a, **k: None)
    monkeypatch.setattr(chat_engine, "notify_message", lambda *a, **k: None)
    chat_engine._response_cache = chat_engine._TTLCache(max_size=16, ttl=300)

    r1 = chat_engine.answer("Bảo hành mấy năm?", "sess-1")
    r2 = chat_engine.answer("  bảo hành mấy NĂM?  ", "sess-2")  # khác hoa/thường + space

    assert len(gen_calls) == 1                    # lượt 2 không gọi lại model
    assert r1["cached"] is False
    assert r2["cached"] is True
    assert r1["message_id"] != r2["message_id"]   # message_id riêng từng lượt
    assert r1["answer"] == r2["answer"] == "Đáp án"
