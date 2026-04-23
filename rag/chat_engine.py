import time
import google.generativeai as genai
import config
from rag.retriever import Retriever
from rag.prompt_builder import SYSTEM_PROMPT, build_prompt

genai.configure(api_key=config.GEMINI_API_KEY)

_retriever: Retriever | None = None


def get_retriever() -> Retriever:
    global _retriever
    if _retriever is None:
        _retriever = Retriever()
    return _retriever


def answer(question: str) -> dict:
    """Run the full RAG pipeline and return answer + sources + latency.

    Returns:
        {
            "answer": str,
            "sources": [{"title": str, "path": str, "score": float}],
            "latency_ms": int,
        }
    """
    t0 = time.time()
    retriever = get_retriever()
    context_docs = retriever.search(question)

    messages = build_prompt(question, context_docs)
    model = genai.GenerativeModel(
        model_name=config.CHAT_MODEL,
        system_instruction=SYSTEM_PROMPT,
    )
    response = model.generate_content(messages)
    answer_text = response.text

    latency_ms = int((time.time() - t0) * 1000)
    sources = [
        {"title": d["title"], "path": d["path"], "score": round(d["score"], 4)}
        for d in context_docs
    ]

    return {
        "answer": answer_text,
        "sources": sources,
        "latency_ms": latency_ms,
    }
