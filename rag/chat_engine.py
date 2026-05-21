import asyncio
import time
import unicodedata
from collections import OrderedDict

from google import genai
from google.genai import types

import config
from rag.retriever import Retriever
from rag.prompt_builder import SYSTEM_PROMPT, build_prompt
from rag.retry import call_with_retry

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

# ── Sync API (dùng bởi api/main.py) ─────────────────────────────────────────

def get_retriever() -> Retriever:
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

    messages = build_prompt(question, context_docs)

    def _call() -> str:
        resp = _client.models.generate_content(
            model=config.CHAT_MODEL,
            contents=messages,
            config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
        )
        return resp.text

    answer_text = call_with_retry(_call, max_retries=4, base_wait=2.0)

    latency_ms = int((time.time() - t0) * 1000)
    sources = [
        {"title": d["title"], "path": d["path"], "score": round(d["score"], 4)}
        for d in context_docs
    ]
    return {"answer": answer_text, "sources": sources, "latency_ms": latency_ms}


# ── Async API (dùng bởi eval/run_deepeval.py) ────────────────────────────────

async def _get_retriever() -> Retriever:
    """Async wrapper — load index lần đầu trong thread pool để không block event loop."""
    return await asyncio.to_thread(get_retriever)


async def init_retriever() -> None:
    """Pre-warm retriever vào RAM trước khi chạy eval."""
    await _get_retriever()


async def answer_async(question: str) -> dict:
    """Async wrapper của answer() — chạy sync call trong thread pool."""
    return await asyncio.to_thread(answer, question)
