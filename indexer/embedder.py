import time
import google.generativeai as genai
import config

genai.configure(api_key=config.GEMINI_API_KEY)


def embed_texts(texts: list[str], task_type: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
    """Embed a list of texts in batches, with retry on transient errors."""
    embeddings = []
    batch_size = config.EMBEDDING_BATCH_SIZE

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        embeddings.extend(_embed_batch(batch, task_type))

    return embeddings


def embed_query(text: str) -> list[float]:
    results = _embed_batch([text], task_type="RETRIEVAL_QUERY")
    return results[0]


def _embed_batch(texts: list[str], task_type: str, retries: int = 3) -> list[list[float]]:
    for attempt in range(retries):
        try:
            result = genai.embed_content(
                model=config.EMBEDDING_MODEL,
                content=texts,
                task_type=task_type,
            )
            return result["embedding"] if len(texts) == 1 else result["embedding"]
        except Exception as exc:
            if attempt == retries - 1:
                raise RuntimeError(f"Embedding failed after {retries} attempts: {exc}") from exc
            wait = 2 ** attempt
            print(f"[embedder] Retry {attempt + 1}/{retries} after {wait}s — {exc}")
            time.sleep(wait)
    return []
