"""
Chat engine — orchestrate retriever → Gemini → response.

- answer() là async, không block FastAPI event loop
- Mỗi retry dùng model khác theo CHAT_MODEL_CHAIN (tránh 503 cùng model)
- Exponential backoff + full jitter giữa các lần retry
- TTL cache in-memory để câu hỏi giống nhau trả về ngay
"""

import asyncio
import logging
import re
import time
import unicodedata
from collections import OrderedDict

from google import genai
from google.genai import types

import config
from rag.retriever import Retriever
from rag.prompt_builder import SYSTEM_PROMPT, build_prompt
from rag.retry import is_retryable, wait_seconds

logger = logging.getLogger(__name__)

_client = genai.Client(api_key=config.GEMINI_API_KEY)
_retriever: Retriever | None = None
_retriever_lock = asyncio.Lock()


# ---------------------------------------------------------------------------
# TTL cache đơn giản (thread-safe với GIL của CPython)
# ---------------------------------------------------------------------------

class _TTLCache:
    """OrderedDict-based LRU cache với TTL."""

    def __init__(self, max_size: int, ttl: float) -> None:
        self._store: OrderedDict[str, tuple[dict, float]] = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl

    def _normalize(self, question: str) -> str:
        text = unicodedata.normalize("NFC", question.lower().strip())
        return re.sub(r"\s+", " ", text)

    def get(self, question: str) -> dict | None:
        key = self._normalize(question)
        if key not in self._store:
            return None
        value, ts = self._store[key]
        if time.time() - ts > self._ttl:
            del self._store[key]
            return None
        self._store.move_to_end(key)
        return value

    def set(self, question: str, value: dict) -> None:
        key = self._normalize(question)
        self._store[key] = (value, time.time())
        self._store.move_to_end(key)
        while len(self._store) > self._max_size:
            self._store.popitem(last=False)


_cache = _TTLCache(
    max_size=config.RESPONSE_CACHE_MAX_SIZE,
    ttl=config.RESPONSE_CACHE_TTL,
)


# ---------------------------------------------------------------------------
# Retriever singleton (lazy init)
# ---------------------------------------------------------------------------

async def _get_retriever() -> Retriever:
    global _retriever
    if _retriever is not None:
        return _retriever
    async with _retriever_lock:
        if _retriever is None:
            _retriever = await asyncio.to_thread(Retriever)
    return _retriever


async def init_retriever() -> None:
    """Gọi lúc startup để pre-load index vào RAM."""
    await _get_retriever()


# ---------------------------------------------------------------------------
# Gemini call với model cycling
# ---------------------------------------------------------------------------

def _generate(model: str, messages: list, system: str) -> str:
    response = _client.models.generate_content(
        model=model,
        contents=messages,
        config=types.GenerateContentConfig(system_instruction=system),
    )
    return response.text


async def _call_gemini(messages: list, system: str) -> str:
    """
    Gọi Gemini với retry.
    Mỗi lần retry chọn model khác từ CHAT_MODEL_CHAIN.
    Ví dụ với chain = [flash, flash-8b, flash, flash-8b, flash]:
      attempt 0 → gemini-2.5-flash
      attempt 1 → gemini-2.5-flash-8b
      attempt 2 → gemini-2.5-flash
      ...
    """
    chain = config.CHAT_MODEL_CHAIN
    last_exc: Exception | None = None

    for attempt in range(config.GEMINI_MAX_RETRIES):
        model = chain[attempt % len(chain)]
        try:
            # chạy sync SDK trong thread pool để không block event loop
            result = await asyncio.to_thread(
                lambda m=model: _generate(m, messages, system)
            )
            if attempt > 0:
                logger.info(
                    "Thành công với model '%s' sau %d lần thử", model, attempt + 1
                )
            return result
        except Exception as exc:
            if not is_retryable(exc):
                raise
            last_exc = exc
            secs = wait_seconds(attempt)
            logger.warning(
                "[%d/%d] Model '%s' lỗi: %s — đổi model, retry sau %.1fs",
                attempt + 1,
                config.GEMINI_MAX_RETRIES,
                model,
                exc,
                secs,
            )
            await asyncio.sleep(secs)

    raise RuntimeError(
        f"Tất cả models thất bại sau {config.GEMINI_MAX_RETRIES} lần thử"
    ) from last_exc


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def answer(question: str) -> dict:
    """
    Trả về dict {answer, sources, latency_ms, cached}.
    Hoàn toàn async — an toàn để gọi trong FastAPI handler.
    """
    cached = _cache.get(question)
    if cached is not None:
        logger.debug("Cache hit: %s", question[:60])
        return {**cached, "cached": True}

    t0 = time.time()

    retriever = await _get_retriever()
    context_docs = await asyncio.to_thread(retriever.search, question)

    messages = build_prompt(question, context_docs)
    answer_text = await _call_gemini(messages, SYSTEM_PROMPT)

    latency_ms = int((time.time() - t0) * 1000)
    sources = [
        {"title": d["title"], "path": d["path"], "score": round(d["score"], 4)}
        for d in context_docs
    ]
    result = {
        "answer": answer_text,
        "sources": sources,
        "latency_ms": latency_ms,
        "cached": False,
    }

    _cache.set(question, result)
    return result
