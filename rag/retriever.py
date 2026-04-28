import json
import re
import unicodedata
import numpy as np
import config
from indexer.embedder import embed_query


def _remove_diacritics(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


def _keyword_boost(query: str, rec: dict) -> float:
    """Trả về điểm boost [0, 0.15] dựa trên keyword overlap, bỏ dấu tiếng Việt khi so sánh."""
    q = _remove_diacritics(query.lower())
    query_words = set(re.findall(r"\w+", q))
    target = _remove_diacritics(
        (rec.get("title", "") + " " + rec.get("path", "")).lower()
    )
    target_words = set(re.findall(r"\w+", target))
    if not query_words:
        return 0.0
    overlap = len(query_words & target_words) / len(query_words)
    return overlap * 0.15


class Retriever:
    def __init__(self) -> None:
        self._records: list[dict] = []
        self._matrix: np.ndarray | None = None
        self._load()

    def _load(self) -> None:
        if not config.INDEX_PATH.exists():
            raise FileNotFoundError(
                f"Index not found at {config.INDEX_PATH}. "
                "Run: python -m indexer.build_index"
            )
        records = json.loads(config.INDEX_PATH.read_text(encoding="utf-8"))
        self._records = records
        embeddings = [r["embedding"] for r in records]
        matrix = np.array(embeddings, dtype=np.float32)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms = np.clip(norms, 1e-9, None)
        self._matrix = matrix / norms

    def search(self, question: str, top_k: int = config.TOP_K) -> list[dict]:
        query_vec = np.array(embed_query(question), dtype=np.float32)
        norm = np.linalg.norm(query_vec)
        if norm > 0:
            query_vec = query_vec / norm

        cosine_scores = self._matrix @ query_vec

        # Lấy candidates rộng rồi re-rank với keyword boost
        candidate_k = min(config.RETRIEVAL_CANDIDATE_K, len(self._records))
        candidate_indices = np.argsort(cosine_scores)[::-1][:candidate_k]

        candidates = []
        for idx in candidate_indices:
            rec = self._records[idx]
            boost = _keyword_boost(question, rec)
            final_score = float(cosine_scores[idx]) + boost
            candidates.append((final_score, idx))

        candidates.sort(key=lambda x: x[0], reverse=True)

        results = []
        for final_score, idx in candidates[:top_k]:
            rec = self._records[idx]
            results.append({
                "path": rec["path"],
                "title": rec["title"],
                "content": rec["content"],
                "score": round(final_score, 4),
                "metadata": rec["metadata"],
            })
        return results

    def reload(self) -> None:
        self._load()
