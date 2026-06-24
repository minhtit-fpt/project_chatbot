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
from rag.history_store import SessionHistoryStore, SessionDocCache
from rag.query_rewriter import plan_search_queries


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
    # Planner gọi LLM thật → stub trả [question] để test không chạm mạng.
    monkeypatch.setattr(chat_engine, "plan_search_queries", lambda q, h, **kw: [q])
    chat_engine._response_cache = chat_engine._TTLCache(max_size=16, ttl=300)
    chat_engine._history_store = SessionHistoryStore(
        max_turns=10, ttl=300, max_sessions=10
    )
    chat_engine._doc_cache = SessionDocCache(ttl=300, max_sessions=10)


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


# ── SessionDocCache ──────────────────────────────────────────────────────────

def _doc(path):
    return {"title": path, "path": path, "content": "x", "score": 0.9, "metadata": {}}


def test_doc_cache_set_get_roundtrip():
    cache = SessionDocCache(ttl=100.0, max_sessions=10)
    cache.set("a", [_doc("p1.md")])
    assert [d["path"] for d in cache.get("a")] == ["p1.md"]


def test_doc_cache_missing_returns_empty():
    cache = SessionDocCache(ttl=100.0, max_sessions=10)
    assert cache.get("khong-ton-tai") == []


def test_doc_cache_expires_after_ttl():
    clock = {"t": 0.0}
    cache = SessionDocCache(ttl=100.0, max_sessions=10, time_func=lambda: clock["t"])
    cache.set("a", [_doc("p1.md")])
    clock["t"] = 100.1  # quá TTL
    assert cache.get("a") == []


def test_doc_cache_evicts_oldest_over_max_sessions():
    cache = SessionDocCache(ttl=100.0, max_sessions=2)
    cache.set("s1", [_doc("p.md")])
    cache.set("s2", [_doc("p.md")])
    cache.set("s3", [_doc("p.md")])  # vượt trần → s1 (cũ nhất) bị bỏ
    assert cache.get("s1") == []
    assert cache.get("s2") != []
    assert cache.get("s3") != []


# ── _merge_query_results ─────────────────────────────────────────────────────

def test_merge_single_query_then_fills_with_prev():
    new = [_doc("n1.md"), _doc("n2.md")]
    prev = [_doc("p1.md")]
    merged = chat_engine._merge_query_results([new], prev, limit=8)
    assert [d["path"] for d in merged] == ["n1.md", "n2.md", "p1.md"]


def test_merge_round_robin_balances_two_queries():
    """Hai truy vấn (2 hãng) → interleave hạng 0 mỗi bên trước, không bên nào lấn át."""
    daikin = [_doc("dk1.md"), _doc("dk2.md"), _doc("dk3.md")]
    gree = [_doc("gr1.md"), _doc("gr2.md")]
    merged = chat_engine._merge_query_results([daikin, gree], [], limit=8)
    assert [d["path"] for d in merged] == [
        "dk1.md", "gr1.md", "dk2.md", "gr2.md", "dk3.md"
    ]


def test_merge_dedupes_by_path_across_queries():
    q1 = [_doc("x.md")]
    q2 = [_doc("x.md"), _doc("y.md")]
    merged = chat_engine._merge_query_results([q1, q2], [], limit=8)
    assert [d["path"] for d in merged] == ["x.md", "y.md"]


def test_merge_dedupes_prev_against_new():
    new = [_doc("x.md")]
    prev = [_doc("x.md"), _doc("y.md")]
    merged = chat_engine._merge_query_results([new], prev, limit=8)
    assert [d["path"] for d in merged] == ["x.md", "y.md"]


def test_merge_respects_limit():
    q1 = [_doc(f"n{i}.md") for i in range(5)]
    prev = [_doc(f"p{i}.md") for i in range(5)]
    merged = chat_engine._merge_query_results([q1], prev, limit=3)
    assert [d["path"] for d in merged] == ["n0.md", "n1.md", "n2.md"]


def test_merge_empty_results_returns_empty():
    assert chat_engine._merge_query_results([], [], limit=8) == []


# ── plan_search_queries (cổng gọi LLM + fail-open) ───────────────────────────

class _RespClient:
    """Client giả ghi lại số lần gọi, trả về text cố định."""

    def __init__(self, text):
        self._text = text
        self.calls = 0

    class _Resp:
        def __init__(self, text):
            self.text = text

    @property
    def models(self):
        outer = self

        class _Models:
            @staticmethod
            def generate_content(**kw):
                outer.calls += 1
                return _RespClient._Resp(outer._text)

        return _Models()


def test_plan_queries_normal_first_turn_no_llm():
    # Lượt đầu, không ý so sánh → trả [question], KHÔNG gọi client (truyền None để chứng minh).
    assert plan_search_queries("giá điều hòa Daikin?", [], client=None) == [
        "giá điều hòa Daikin?"
    ]


def test_plan_queries_comparison_first_turn_calls_planner():
    client = _RespClient('["điều hòa cây Daikin", "điều hòa cây Gree"]')
    out = plan_search_queries("so sánh điều hòa cây Daikin và Gree", [], client=client)
    assert client.calls == 1
    assert out == ["điều hòa cây Daikin", "điều hòa cây Gree"]


def test_plan_queries_followup_calls_planner_and_rewrites():
    client = _RespClient('["công nghệ điều hòa cây Daikin Inverter"]')
    history = [{"question": "q1", "answer": "a1"}]
    out = plan_search_queries("công nghệ loại đó?", history, client=client)
    assert client.calls == 1
    assert out == ["công nghệ điều hòa cây Daikin Inverter"]


def test_plan_queries_parses_json_in_code_fence():
    client = _RespClient('```json\n["điều hòa cây Gree 48000btu"]\n```')
    history = [{"question": "q1", "answer": "a1"}]
    out = plan_search_queries("còn loại nào?", history, client=client)
    assert out == ["điều hòa cây Gree 48000btu"]


def test_plan_queries_caps_at_max_subqueries():
    client = _RespClient('["a", "b", "c", "d", "e"]')
    history = [{"question": "q1", "answer": "a1"}]
    out = plan_search_queries("so sánh nhiều hãng", history, client=client)
    assert out == ["a", "b", "c"]  # config.MAX_SUBQUERIES = 3


def test_plan_queries_falls_back_on_bad_json():
    client = _RespClient("Đây không phải JSON gì cả.")
    history = [{"question": "q1", "answer": "a1"}]
    out = plan_search_queries("loại đó giá bao nhiêu?", history, client=client)
    assert out == ["loại đó giá bao nhiêu?"]  # fallback nguyên câu hỏi gốc


def test_plan_queries_falls_back_on_error():
    class _BoomClient:
        class models:
            @staticmethod
            def generate_content(**kw):
                raise RuntimeError("API down")

    history = [{"question": "q1", "answer": "a1"}]
    out = plan_search_queries("loại đó giá bao nhiêu?", history, client=_BoomClient())
    assert out == ["loại đó giá bao nhiêu?"]  # fallback fail-open


# ── answer() — context-aware retrieval cho follow-up ─────────────────────────

class _RecordingRetriever:
    """Ghi lại query nhận được; trả doc khác nhau theo query để kiểm carry-forward."""

    def __init__(self):
        self.queries = []

    def search(self, question):
        self.queries.append(question)
        path = "A.md" if question == "câu 1" else "B.md"
        return [{"title": path, "path": path, "content": "x", "score": 0.9, "metadata": {}}]


def test_answer_followup_uses_planned_query_and_carries_prev_docs(monkeypatch):
    _patch_answer_env(monkeypatch)
    retriever = _RecordingRetriever()
    monkeypatch.setattr(chat_engine, "get_retriever", lambda: retriever)
    monkeypatch.setattr(
        chat_engine, "_generate_answer", lambda messages, history=None: "ans"
    )
    # Planner: lượt đầu giữ nguyên câu hỏi; follow-up viết lại thành query có ngữ cảnh.
    monkeypatch.setattr(
        chat_engine, "plan_search_queries",
        lambda q, h, **kw: ["điều hòa cây Daikin công nghệ"] if h else [q],
    )

    chat_engine.answer("câu 1", "S")            # lượt đầu → search("câu 1") → doc A
    r2 = chat_engine.answer("công nghệ?", "S")  # follow-up

    # Retrieval lượt 2 dùng query ĐÃ VIẾT LẠI, không phải câu hỏi gốc.
    assert retriever.queries == ["câu 1", "điều hòa cây Daikin công nghệ"]
    assert r2["search_queries"] == ["điều hòa cây Daikin công nghệ"]
    # Tài liệu lượt 2 gộp cả doc mới (B) lẫn doc lượt trước (A) — lưới an toàn.
    assert {s["path"] for s in r2["sources"]} == {"B.md", "A.md"}


def test_answer_comparison_first_turn_searches_each_entity(monkeypatch):
    """Câu so sánh lượt đầu → planner tách 2 truy vấn → sources có cả 2 hãng."""
    _patch_answer_env(monkeypatch)

    class _BrandRetriever:
        def __init__(self):
            self.queries = []

        def search(self, q):
            self.queries.append(q)
            path = "daikin.md" if "Daikin" in q else "gree.md"
            return [{"title": path, "path": path, "content": "x", "score": 0.9, "metadata": {}}]

    retriever = _BrandRetriever()
    monkeypatch.setattr(chat_engine, "get_retriever", lambda: retriever)
    monkeypatch.setattr(
        chat_engine, "_generate_answer", lambda messages, history=None: "ans"
    )
    monkeypatch.setattr(
        chat_engine, "plan_search_queries",
        lambda q, h, **kw: ["điều hòa cây Daikin", "điều hòa cây Gree"],
    )

    r = chat_engine.answer("so sánh điều hòa cây Daikin và Gree", "C")

    assert retriever.queries == ["điều hòa cây Daikin", "điều hòa cây Gree"]
    assert {s["path"] for s in r["sources"]} == {"daikin.md", "gree.md"}
    assert r["search_queries"] == ["điều hòa cây Daikin", "điều hòa cây Gree"]


def test_answer_first_turn_normal_keeps_raw_query(monkeypatch):
    _patch_answer_env(monkeypatch)
    monkeypatch.setattr(
        chat_engine, "_generate_answer", lambda messages, history=None: "ans"
    )
    r = chat_engine.answer("câu đầu", "solo")
    # Lượt thường lượt đầu (stub planner trả [q]) → query đúng nguyên câu hỏi.
    assert r["search_queries"] == ["câu đầu"]
