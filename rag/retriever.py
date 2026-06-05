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
    """Trả về điểm boost [0, 0.15] dựa trên keyword overlap, bỏ dấu tiếng Việt khi so sánh.

    Ngoài title và path, còn xét thêm mảng keywords trong frontmatter metadata
    để tận dụng từ đồng nghĩa và cách khách hay hỏi.
    """
    q = _remove_diacritics(query.lower())
    query_words = set(re.findall(r"\w+", q))

    # Lấy keywords từ frontmatter (list hoặc string)
    kw_meta = rec.get("metadata", {}).get("keywords", []) or []
    if isinstance(kw_meta, list):
        kw_str = " ".join(str(k) for k in kw_meta)
    else:
        kw_str = str(kw_meta)

    target = _remove_diacritics(
        (rec.get("title", "") + " " + rec.get("path", "") + " " + kw_str).lower()
    )
    target_words = set(re.findall(r"\w+", target))
    if not query_words:
        return 0.0
    overlap = len(query_words & target_words) / len(query_words)
    return overlap * 0.15


def _policy_boost(rec: dict) -> float:
    """Boost +0.10 cho notes chính sách (Chinh-sach-*.md ở root vault).

    Notes chính sách thường bị các trang sản phẩm (7000+) đè điểm cosine
    dù nội dung thực sự liên quan hơn với câu hỏi chính sách của khách.
    """
    path = rec.get("path", "")
    # Notes ở root vault (không có subfolder) và tên chứa "Chinh-sach"
    if "/" not in path and "\\" not in path and "chinh-sach" in path.lower():
        return 0.10
    return 0.0


def _featured_boost(rec: dict) -> float:
    """Boost cho note hãng nổi tiếng (frontmatter `featured: true`).

    Với câu hỏi chung chung ("có những dòng tivi nào"), mọi sản phẩm cùng loại có
    cosine gần nhau nên hàng bình dân dễ lọt top. Boost này đẩy hãng nổi tiếng lên.
    Tag `featured` được gắn sẵn trong frontmatter các note hãng nổi tiếng (xem .claude/memory.md).
    """
    if rec.get("metadata", {}).get("featured"):
        return config.FEATURED_BOOST
    return 0.0


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
        candidate_idx_set = set(np.argsort(cosine_scores)[::-1][:candidate_k].tolist())

        # Luôn thêm các policy notes vào pool (số lượng nhỏ, ~5 notes)
        # để keyword boost có cơ hội nâng rank dù cosine score thấp
        for i, rec in enumerate(self._records):
            if _policy_boost(rec) > 0:
                candidate_idx_set.add(i)

        candidates = []
        for idx in candidate_idx_set:
            rec = self._records[idx]
            boost = _keyword_boost(question, rec) + _policy_boost(rec) + _featured_boost(rec)
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
