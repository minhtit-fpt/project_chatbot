import json
import numpy as np
import config
from indexer.embedder import embed_query


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
        norms = np.where(norms == 0, 1, norms)
        self._matrix = matrix / norms

    def search(self, question: str, top_k: int = config.TOP_K) -> list[dict]:
        query_vec = np.array(embed_query(question), dtype=np.float32)
        norm = np.linalg.norm(query_vec)
        if norm > 0:
            query_vec = query_vec / norm

        scores = self._matrix @ query_vec
        top_indices = np.argsort(scores)[::-1][:top_k]

        results = []
        for idx in top_indices:
            rec = self._records[idx]
            results.append({
                "path": rec["path"],
                "title": rec["title"],
                "content": rec["content"],
                "score": float(scores[idx]),
                "metadata": rec["metadata"],
            })
        return results

    def reload(self) -> None:
        self._load()
