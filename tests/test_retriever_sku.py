"""Khớp mã SKU chính xác ở tầng retrieval (plan-prod-log-fixes B.1).

Vấn đề từ log production: embedding rất yếu với chuỗi mã, cosine trả về sản phẩm
CÙNG DANH MỤC nhưng SAI mã (id 394/404 "u9bkh vs xu9bkh", id 487 "SJ-FXP560V-BK",
id 435 "R-29D2(G/R)VN"). Hai bất biến được canh ở đây:
  1. Record mang đúng mã khách hỏi được boost mạnh hơn mọi tín hiệu mờ khác.
  2. Mã KHÔNG có trong index phải được báo ra (``unmatched_model_codes``) để tầng
     trên nói thẳng "chưa có mã này" thay vì đổ sản phẩm khác.

Test thuần — không gọi embedding API, không load index thật.
"""
import config
from rag.retriever import (
    Retriever,
    _code_match_boost,
    _model_code_tokens,
    _record_code_tokens,
    build_code_index,
)


def _rec(title: str, *, keywords=None) -> dict:
    return {
        "path": "tivi/" + title.lower().replace(" ", "-") + ".md",
        "title": title,
        "content": "- Giá: 10.000.000 đ\n",
        "metadata": {"keywords": keywords or []},
    }


def _retriever_with(records: list[dict]) -> Retriever:
    """Retriever chỉ có code index — bỏ qua __init__ để không load index 336 MB."""
    retriever = object.__new__(Retriever)
    retriever._code_index = build_code_index(records)
    return retriever


# ── build_code_index ───────────────────────────────────────────────────────
def test_code_index_maps_code_from_title():
    records = [_rec("Smart Tivi Samsung UA43DU7000KXXV")]
    assert build_code_index(records)["ua43du7000kxxv"] == {0}


def test_code_index_maps_code_from_keywords():
    records = [_rec("Tủ Lạnh Sharp", keywords=["SJ-FXP560V-BK", "tu lanh sharp"])]
    assert 0 in build_code_index(records)["fxp560v"]


def test_code_index_ignores_plain_words_and_bare_numbers():
    index = build_code_index([_rec("Tivi Samsung 43 Inch")])
    assert "samsung" not in index
    assert "43" not in index


# ── _code_match_boost ──────────────────────────────────────────────────────
def test_exact_code_match_boost_beats_other_signals():
    rec = _rec("Smart Tivi Samsung UA43DU7000KXXV")
    boost = _code_match_boost(_model_code_tokens("tivi ua43du7000kxxv"), rec)
    # Phải thắng hẳn tổng keyword (0.15) + policy (0.10) + featured boost.
    assert boost == config.CODE_MATCH_BOOST
    assert boost > 0.15 + 0.10 + config.FEATURED_BOOST


def test_no_boost_for_different_code():
    rec = _rec("Smart Tivi Samsung UA43DU7000KXXV")
    assert _code_match_boost(_model_code_tokens("tivi xu9bkh"), rec) == 0.0


def test_no_boost_when_question_has_no_code():
    rec = _rec("Smart Tivi Samsung UA43DU7000KXXV")
    assert _code_match_boost(_model_code_tokens("tivi samsung giá bao nhiêu"), rec) == 0.0


# ── unmatched_model_codes ──────────────────────────────────────────────────
def test_unmatched_reports_code_absent_from_index():
    retriever = _retriever_with([_rec("Robot Hút Bụi Hitachi RV-X20J")])
    # Mã khách hỏi (log id 453/454) không có trong vault → phải báo thiếu.
    assert retriever.unmatched_model_codes("robot midea mv15ultraapbk") == [
        "mv15ultraapbk"
    ]


def test_unmatched_empty_when_code_exists():
    retriever = _retriever_with([_rec("Tủ Lạnh Sharp", keywords=["SJ-FXP560V-BK"])])
    assert retriever.unmatched_model_codes("tủ lạnh SJ-FXP560V-BK") == []


def test_unmatched_empty_for_question_without_code():
    retriever = _retriever_with([_rec("Smart Tivi Samsung UA43DU7000KXXV")])
    assert retriever.unmatched_model_codes("tivi 43 inch giá bao nhiêu") == []


def test_unmatched_reports_each_missing_code_once_sorted():
    retriever = _retriever_with([_rec("Tivi Samsung U9BKH")])
    # id 394/404: "u9bkh khác gì xu9bkh" — chỉ mã thứ hai là thiếu.
    assert retriever.unmatched_model_codes("u9bkh khác gì xu9bkh") == ["xu9bkh"]


def test_record_code_tokens_covers_title_path_and_keywords():
    rec = _rec("Tủ Lạnh Sharp", keywords=["SJ-FXP560V-BK"])
    assert "fxp560v" in _record_code_tokens(rec)
