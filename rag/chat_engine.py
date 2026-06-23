import asyncio
import logging
import threading
import time
import uuid
from collections import OrderedDict

from google import genai
from google.genai import types

import config
from rag.retriever import Retriever
from rag.prompt_builder import SYSTEM_PROMPT, build_prompt
from rag.retry import call_with_retry, is_retryable
from rag.history_store import SessionHistoryStore
from logs.conversation_store import log_conversation
from logs.auto_sync import notify_message

logger = logging.getLogger(__name__)

_client = genai.Client(api_key=config.GEMINI_API_KEY)
_retriever: Retriever | None = None
_retriever_lock = threading.Lock()  # sync lock — get_retriever() là hàm đồng bộ

# Câu trả lời mặc định khi model bị chặn an toàn / trả về rỗng.
FALLBACK_ANSWER = (
    "Hiện tại bên mình chưa có thông tin về vấn đề này. "
    "Quý khách vui lòng liên hệ hotline hoặc đến trực tiếp cửa hàng để được hỗ trợ nhé."
)

# Số lần retry transient cho MỖI model trước khi rớt sang model kế trong chain.
_PER_MODEL_RETRIES = 2


# ---------------------------------------------------------------------------
# TTL cache đơn giản (thread-safe với GIL của CPython)
# ---------------------------------------------------------------------------

class _TTLCache:
    """OrderedDict-based LRU cache với TTL."""

    def __init__(self, max_size: int, ttl: float) -> None:
        self._store: OrderedDict[str, tuple[dict, float]] = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl

    def get(self, key: str) -> dict | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, ts = entry
        if time.time() - ts > self._ttl:
            del self._store[key]
            return None
        self._store.move_to_end(key)
        return value

    def set(self, key: str, value: dict) -> None:
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = (value, time.time())
        while len(self._store) > self._max_size:
            self._store.popitem(last=False)


_response_cache = _TTLCache(
    max_size=config.RESPONSE_CACHE_MAX_SIZE,
    ttl=config.RESPONSE_CACHE_TTL,
)

# Kho nhớ hội thoại per-session — giúp model nhớ ngữ cảnh các lượt trước trong phiên.
_history_store = SessionHistoryStore(
    max_turns=config.HISTORY_MAX_TURNS,
    ttl=config.HISTORY_TTL,
    max_sessions=config.HISTORY_MAX_SESSIONS,
)


def _build_contents(current_prompt: str, history: list[dict]) -> list[types.Content]:
    """Ghép lịch sử hội thoại + câu hỏi hiện tại thành contents đa lượt cho Gemini.

    Mỗi lượt cũ → 1 message role="user" (câu hỏi gốc) + 1 message role="model"
    (câu trả lời). Tài liệu RAG chỉ chèn vào lượt hiện tại (current_prompt) để lịch
    sử gọn nhẹ, không nhân bản context qua từng lượt.
    """
    contents: list[types.Content] = []
    for turn in history:
        contents.append(
            types.Content(role="user", parts=[types.Part(text=turn["question"])])
        )
        contents.append(
            types.Content(role="model", parts=[types.Part(text=turn["answer"])])
        )
    contents.append(
        types.Content(role="user", parts=[types.Part(text=current_prompt)])
    )
    return contents


def _generate_answer(messages: str, history: list[dict] | None = None) -> str:
    """Sinh câu trả lời, thử lần lượt các model trong CHAT_MODEL_CHAIN.

    Gửi kèm lịch sử hội thoại (nếu có) để model nhớ ngữ cảnh các lượt trước.
    Mỗi model được retry transient (exponential backoff); nếu vẫn lỗi hoặc trả
    rỗng → rớt sang model kế tiếp. Hết chain:
      - còn lỗi transient → raise (để API trả 503),
      - chỉ trả rỗng (vd bị chặn an toàn) → trả FALLBACK_ANSWER thay vì None.
    """
    contents = _build_contents(messages, history or [])
    last_exc: Exception | None = None
    for model in config.CHAT_MODEL_CHAIN:
        def _call(model: str = model) -> str:
            resp = _client.models.generate_content(
                model=model,
                contents=contents,
                config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
            )
            return resp.text or ""

        try:
            text = call_with_retry(
                _call,
                max_retries=_PER_MODEL_RETRIES,
                base_wait=config.GEMINI_RETRY_BASE_WAIT,
            )
            if text:
                return text
            logger.warning("Model %s trả về nội dung rỗng, thử model kế tiếp", model)
            last_exc = RuntimeError(f"Model {model} trả về nội dung rỗng")
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning("Model %s lỗi (%s), thử model kế tiếp", model, exc)

    if last_exc is not None and is_retryable(last_exc):
        raise last_exc
    return FALLBACK_ANSWER


# ── Sync API (dùng bởi api/main.py) ─────────────────────────────────────────

def get_retriever() -> Retriever:
    global _retriever
    if _retriever is not None:
        return _retriever
    with _retriever_lock:
        if _retriever is None:
            _retriever = Retriever()
    return _retriever


def answer(question: str, session_id: str) -> dict:
    t0 = time.time()
    history = _history_store.get(session_id)
    # Chỉ cache câu hỏi KHÔNG phụ thuộc ngữ cảnh (lượt đầu của phiên). Khi đã có
    # lịch sử, câu trả lời phụ thuộc các lượt trước → không đọc/không ghi cache chung;
    # nếu không, lượt sau cùng câu chữ sẽ bị trả nhầm đáp án đã cache của phiên khác.
    use_cache = not history
    cache_key = question.strip().lower()
    cached_entry = _response_cache.get(cache_key) if use_cache else None

    if cached_entry is not None:
        answer_text = cached_entry["answer"]
        sources = cached_entry["sources"]
        cached = True
    else:
        retriever = get_retriever()
        context_docs = retriever.search(question)
        messages = build_prompt(question, context_docs)
        answer_text = _generate_answer(messages, history)
        sources = [
            {"title": d["title"], "path": d["path"], "score": round(d["score"], 4)}
            for d in context_docs
        ]
        # Lưu cache không kèm message_id — mỗi lần trả vẫn sinh message_id mới
        # và ghi log riêng để feedback ánh xạ đúng từng lượt hỏi.
        if use_cache:
            _response_cache.set(cache_key, {"answer": answer_text, "sources": sources})
        cached = False

    # Ghi lượt vừa rồi vào lịch sử để các lượt sau trong cùng phiên có ngữ cảnh.
    _history_store.append(session_id, question, answer_text)

    latency_ms = int((time.time() - t0) * 1000)
    message_id = str(uuid.uuid4())
    log_conversation(session_id, question, answer_text, sources, latency_ms, message_id)
    notify_message(session_id)
    return {
        "message_id": message_id,
        "session_id": session_id,
        "answer": answer_text,
        "sources": sources,
        "latency_ms": latency_ms,
        "cached": cached,
    }


# ── Async API (dùng bởi eval/run_deepeval.py) ────────────────────────────────

async def _get_retriever() -> Retriever:
    """Async wrapper — load index lần đầu trong thread pool để không block event loop."""
    return await asyncio.to_thread(get_retriever)


async def init_retriever() -> None:
    """Pre-warm retriever vào RAM trước khi chạy eval."""
    await _get_retriever()


async def answer_async(question: str, session_id: str | None = None) -> dict:
    """Async wrapper của answer() — chạy sync call trong thread pool."""
    sid = session_id or str(uuid.uuid4())
    return await asyncio.to_thread(answer, question, sid)
