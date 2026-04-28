"""
Chat engine — orchestrate retriever → Gemini → response.

Cải thiện so với v1:
- answer() là async, không block FastAPI event loop
- Retry với exponential backoff + jitter cho 503/429
- Fallback sang model nhẹ hơn nếu model chính liên tục lỗi
- TTL cache in-memory để tránh gọi API lặp với câu hỏi giống nhau
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
from rag.retry import async_call_with_retry

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


def get_retriever() -> Retriever | None:
    """Sync accessor dùng cho startup event."""
    return _retriever


async def init_retriever() -> None:
    """Gọi lúc startup để pre-load index vào RAM."""
    await _get_retriever()


# ---------------------------------------------------------------------------
# Gemini call helpers
# ---------------------------------------------------------------------------

def _generate(model: str, messages: list, system: str) -> str:
    response = _client.models.generate_content(
        model=model,
        contents=messages,
        config=types.GenerateContentConfig(system_instruction=system),
    )
    return response.text


async def _call_gemini(messages: list, system: str) -> str:
    """Gọi Gemini với retry. Fallback sang model nhẹ hơn nếu model chính lỗi liên tục."""
    try:
        return await async_call_with_retry(
            lambda: _generate(config.CHAT_MODEL, messages, system)
        )
    except RuntimeError:
        logger.warning(
            "Model chính (%s) thất bại, fallback sang %s",
            config.CHAT_MODEL,
            config.CHAT_FALLBACK_MODEL,
        )
        return await async_call_with_retry(
            lambda: _generate(config.CHAT_FALLBACK_MODEL, messages, system)
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def answer(question: str) -> dict:
    """
    Trả về dict {answer, sources, latency_ms, cached}.
    Hoàn toàn async — an toàn để gọi trong FastAPI handler.
    """
    # Cache hit
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
    result = {"answer": answer_text, "sources": sources, "latency_ms": latency_ms, "cached": False}

    _cache.set(question, result)
    return result
