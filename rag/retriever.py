import json
import logging
import re
import time
import unicodedata
import numpy as np
import config
from indexer.embedder import embed_query

logger = logging.getLogger(__name__)


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


def _code_match_boost(query_codes: set[str], rec: dict) -> float:
    """Boost lớn khi record mang ĐÚNG mã model khách hỏi.

    Cố tình lớn hơn hẳn keyword/policy/featured boost: khách gõ mã là ý định rõ ràng
    nhất có thể, phải thắng mọi tín hiệu mờ khác. 0 nếu câu hỏi không chứa mã nào.
    """
    if not query_codes:
        return 0.0
    return config.CODE_MATCH_BOOST if query_codes & _record_code_tokens(rec) else 0.0


def _price_text(content: str) -> str | None:
    """Trích phần giá thô sau nhãn 'Giá:' trong nội dung note.

    Trả None nếu note KHÔNG có dòng giá (note chính sách/hướng dẫn) → không phải
    sản phẩm, không bị lọc tồn kho. Nhãn phải đúng là 'Giá' (sau khi bỏ dấu/markdown),
    nên 'Giá trị sử dụng: ...' không bị nhầm là dòng giá.
    """
    for line in content.splitlines():
        if ":" not in line:
            continue
        label, _, value = line.partition(":")
        if _remove_diacritics(label).lower().strip(" -*\t") == "gia":
            return value.strip()
    return None


def _is_unavailable(rec: dict) -> bool:
    """True nếu note là SẢN PHẨM có giá 'Liên hệ'/rỗng = chưa bán hoặc hết hàng.

    Đây là ràng buộc CỨNG ở tầng code: không để model tự ý chào bán sản phẩm
    không có sẵn (rule 6 trong SYSTEM_PROMPT chỉ là lớp nhắc, không đáng tin).
    """
    price = _price_text(rec.get("content", ""))
    if price is None:
        return False
    norm = _remove_diacritics(price).lower()
    return norm == "" or "lien he" in norm


def _model_code_tokens(text: str) -> set[str]:
    """Các token 'mã model': vừa có chữ vừa có số, >=4 ký tự (vd 32t2, 50k820s,
    ua43du7000kxxv). Loại trừ cỡ màn thuần số ('32', '43') và từ thường."""
    tokens = re.findall(r"[a-z0-9]+", _remove_diacritics(text).lower())
    return {
        t for t in tokens
        if len(t) >= 4 and any(c.isalpha() for c in t) and any(c.isdigit() for c in t)
    }


def _record_code_tokens(rec: dict) -> set[str]:
    """Các mã model định danh một record — lấy từ title, path và frontmatter keywords."""
    kw_meta = rec.get("metadata", {}).get("keywords", []) or []
    kw_str = " ".join(str(k) for k in kw_meta) if isinstance(kw_meta, list) else str(kw_meta)
    return _model_code_tokens(
        rec.get("title", "") + " " + rec.get("path", "") + " " + kw_str
    )


def _query_targets_record(query: str, rec: dict) -> bool:
    """True nếu khách hỏi ĐÍCH DANH sản phẩm: query chứa mã model trùng title/keywords.

    Carve-out của rule 6: chỉ giữ lại sản phẩm 'Liên hệ' khi khách gọi đúng tên/mã
    của nó (để model còn báo 'hiện chưa có sẵn'), không phải với câu hỏi chung chung.
    """
    q_codes = _model_code_tokens(query)
    if not q_codes:
        return False
    return bool(q_codes & _record_code_tokens(rec))


def build_code_index(records: list[dict]) -> dict[str, set[int]]:
    """Map { mã model -> chỉ số các record chứa mã đó } — dựng MỘT lần lúc load index.

    Embedding rất yếu với chuỗi mã ("u9bkh", "SJ-FXP560V-BK"): cosine trả về sản phẩm
    cùng danh mục nhưng SAI mã (log id 394, 404, 288, 487, 435). Map này cho phép khớp
    CHÍNH XÁC trước khi xét cosine, và trả lời được câu "mã khách hỏi có tồn tại không".
    """
    index: dict[str, set[int]] = {}
    for i, rec in enumerate(records):
        for code in _record_code_tokens(rec):
            index.setdefault(code, set()).add(i)
    return index


def _select_results(
    question: str,
    candidates: list[tuple[float, int]],
    records: list[dict],
    top_k: int,
) -> list[dict]:
    """Dựng top-k kết quả, BỎ QUA sản phẩm giá 'Liên hệ' khi chọn note.

    candidates: list (final_score, idx) ĐÃ sắp xếp giảm dần. Sản phẩm hết hàng bị
    bỏ qua để nhường slot cho sản phẩm đang bán hạng dưới — TRỪ khi khách hỏi đích
    danh mã model (giữ lại để báo chưa có sẵn). Note phi-sản-phẩm luôn được giữ.
    """
    results: list[dict] = []
    for final_score, idx in candidates:
        rec = records[idx]
        if _is_unavailable(rec) and not _query_targets_record(question, rec):
            continue
        results.append({
            "path": rec["path"],
            "title": rec["title"],
            "content": rec["content"],
            "score": round(final_score, 4),
            "metadata": rec["metadata"],
        })
        if len(results) >= top_k:
            break
    return results


class Retriever:
    def __init__(self) -> None:
        self._records: list[dict] = []
        self._matrix: np.ndarray | None = None
        self._code_index: dict[str, set[int]] = {}
        self._load()

    def _load(self) -> None:
        if not config.INDEX_PATH.exists():
            raise FileNotFoundError(
                f"Index not found at {config.INDEX_PATH}. "
                "Run: python -m indexer.build_index"
            )
        records = json.loads(config.INDEX_PATH.read_text(encoding="utf-8"))
        self._records = records
        self._code_index = build_code_index(records)
        embeddings = [r["embedding"] for r in records]
        matrix = np.array(embeddings, dtype=np.float32)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms = np.clip(norms, 1e-9, None)
        self._matrix = matrix / norms

    def unmatched_model_codes(self, question: str) -> list[str]:
        """Mã model khách hỏi mà KHÔNG record nào trong index có.

        Caller (chat_engine) dùng để bảo model nói thẳng "chưa có mã này" thay vì
        để cosine đổ ra sản phẩm khác cùng danh mục như thể đúng mã khách hỏi.
        """
        return sorted(c for c in _model_code_tokens(question) if c not in self._code_index)

    def search(self, question: str, top_k: int = config.TOP_K) -> list[dict]:
        t_embed = time.perf_counter()
        query_vec = np.array(embed_query(question), dtype=np.float32)
        embed_ms = int((time.perf_counter() - t_embed) * 1000)
        t_rank = time.perf_counter()
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

        # Khớp mã CHÍNH XÁC chạy TRƯỚC cosine: record mang đúng mã khách hỏi được
        # nạp thẳng vào pool dù cosine của nó nằm ngoài top-k ứng viên.
        q_codes = _model_code_tokens(question)
        for code in q_codes:
            candidate_idx_set.update(self._code_index.get(code, ()))

        candidates = []
        for idx in candidate_idx_set:
            rec = self._records[idx]
            boost = (
                _keyword_boost(question, rec)
                + _policy_boost(rec)
                + _featured_boost(rec)
                + _code_match_boost(q_codes, rec)
            )
            final_score = float(cosine_scores[idx]) + boost
            candidates.append((final_score, idx))

        candidates.sort(key=lambda x: x[0], reverse=True)

        # Lọc sản phẩm giá "Liên hệ" (chưa bán/hết hàng) NGAY KHI chọn note, để model
        # không bao giờ thấy — không phụ thuộc model tuân thủ rule prompt.
        results = _select_results(question, candidates, self._records, top_k)
        # Tách bạch embed vs rank: log production chỉ có latency TỔNG nên không biết
        # 118 request > 8s chậm ở chặng nào (plan-prod-log-fixes B.3.1).
        logger.info(
            "retrieval embed=%dms rank=%dms n=%d q=%.60s",
            embed_ms, int((time.perf_counter() - t_rank) * 1000), len(results), question,
        )
        return results

    def reload(self) -> None:
        self._load()
