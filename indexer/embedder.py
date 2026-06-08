import time
from google import genai
from google.genai import types
import config

_client = genai.Client(api_key=config.GEMINI_API_KEY)


def embed_texts(texts: list[str], task_type: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
    embeddings = []
    total = len(texts)
    t_start = time.time()

    for i, text in enumerate(texts):
        embeddings.append(_embed_one(text, task_type))
        n_done = i + 1
        if n_done % 50 == 0 or n_done == total:
            elapsed = time.time() - t_start
            rate = n_done / elapsed if elapsed > 0 else 0
            eta = (total - n_done) / rate if rate > 0 else 0
            print(
                f"[embedder] {n_done}/{total} "
                f"({n_done * 100 // total}%) "
                f"— {rate:.1f} docs/s "
                f"— ETA {eta / 60:.1f} phút"
            )

    return embeddings


def embed_query(text: str) -> list[float]:
    return _embed_one(text, task_type="RETRIEVAL_QUERY")


def _embed_one(text: str, task_type: str, retries: int = 3) -> list[float]:
    for attempt in range(retries):
        try:
            response = _client.models.embed_content(
                model=config.EMBEDDING_MODEL,
                contents=text,
                config=types.EmbedContentConfig(task_type=task_type),
            )
            return response.embeddings[0].values
        except Exception as exc:
            if attempt == retries - 1:
                raise RuntimeError(f"Embedding failed after {retries} attempts: {exc}") from exc
            wait = 2 ** attempt
            print(f"[embedder] Retry {attempt + 1}/{retries} after {wait}s — {exc}")
            time.sleep(wait)
    return []
