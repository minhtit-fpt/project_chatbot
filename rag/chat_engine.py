import time
from google import genai
from google.genai import types
import config
from rag.retriever import Retriever
from rag.prompt_builder import SYSTEM_PROMPT, build_prompt

_client = genai.Client(api_key=config.GEMINI_API_KEY)
_retriever: Retriever | None = None


def get_retriever() -> Retriever:
    global _retriever
    if _retriever is None:
        _retriever = Retriever()
    return _retriever


def answer(question: str) -> dict:
    t0 = time.time()
    retriever = get_retriever()
    context_docs = retriever.search(question)

    messages = build_prompt(question, context_docs)
    response = _client.models.generate_content(
        model=config.CHAT_MODEL,
        contents=messages,
        config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
    )
    answer_text = response.text

    latency_ms = int((time.time() - t0) * 1000)
    sources = [
        {"title": d["title"], "path": d["path"], "score": round(d["score"], 4)}
        for d in context_docs
    ]
    return {"answer": answer_text, "sources": sources, "latency_ms": latency_ms}
