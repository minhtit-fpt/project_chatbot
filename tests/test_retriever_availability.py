"""Lọc sản phẩm giá 'Liên hệ' (chưa bán/hết hàng) ở TẦNG RETRIEVAL.

Bất biến: prompt chỉ là "nhờ" model bỏ qua sản phẩm 'Liên hệ' — không đáng tin.
Ràng buộc cứng phải nằm ở code: trước khi chọn note đưa cho model, kiểm tra giá;
note sản phẩm có giá 'Liên hệ' bị loại khỏi kết quả — TRỪ khi khách hỏi đích danh
mã model của nó (khớp rule 6 trong SYSTEM_PROMPT). Note không phải sản phẩm
(chính sách/hướng dẫn, không có dòng giá) KHÔNG bị lọc.

Test thuần — không gọi embedding API, không load index thật.
"""
from rag.retriever import (
    _is_unavailable,
    _price_text,
    _query_targets_record,
    _select_results,
)


def _rec(title: str, price_line: str | None, *, keywords=None) -> dict:
    content = "# " + title + "\n"
    if price_line is not None:
        content += f"- **Giá**: {price_line}\n"
    content += "- Bảo hành: 24 tháng\n"
    return {
        "path": title.lower().replace(" ", "-") + ".md",
        "title": title,
        "content": content,
        "metadata": {"keywords": keywords or []},
    }


# ── _price_text ────────────────────────────────────────────────────────────
def test_price_text_extracts_value_after_label():
    assert _price_text("- **Giá**: Liên hệ\n") == "Liên hệ"
    assert _price_text("- Giá: 10.000.000 đ") == "10.000.000 đ"


def test_price_text_none_when_no_price_line():
    assert _price_text("# Chính sách bảo hành\nNội dung...") is None


def test_price_text_ignores_non_price_label_containing_gia():
    # "Giá trị sử dụng" KHÔNG phải dòng giá → không nhầm
    assert _price_text("- Giá trị sử dụng: cao") is None


# ── _is_unavailable ────────────────────────────────────────────────────────
def test_unavailable_when_price_is_lien_he():
    assert _is_unavailable(_rec("Tivi UBC 32T2", "Liên hệ")) is True


def test_available_when_price_is_concrete():
    assert _is_unavailable(_rec("Smart Tivi Samsung 55", "8.550.000 đ")) is False


def test_non_product_note_not_treated_unavailable():
    assert _is_unavailable(_rec("Chính sách đổi trả", None)) is False


# ── _query_targets_record (khách hỏi đích danh mã model) ───────────────────
def test_query_with_model_code_targets_record():
    rec = _rec("Tivi UBC 32T2 32 Inch", "Liên hệ")
    assert _query_targets_record("tivi ubc 32t2 có gì", rec) is True


def test_generic_brand_query_does_not_target_specific_record():
    rec = _rec("Tivi UBC 32T2 32 Inch", "Liên hệ")
    assert _query_targets_record("tivi samsung có những loại nào", rec) is False


def test_size_digits_alone_do_not_count_as_model_code():
    # "32 inch" chứa "32" (cỡ màn) — KHÔNG được coi là mã model
    rec = _rec("Tivi UBC 32T2 32 Inch", "Liên hệ")
    assert _query_targets_record("tivi 32 inch", rec) is False


# ── _select_results (lọc khi dựng top-k) ───────────────────────────────────
def test_unavailable_skipped_for_general_query():
    records = [
        _rec("Tivi UBC 32T2", "Liên hệ"),          # idx 0 — top score, unavailable
        _rec("Smart Tivi Samsung 55", "8.550.000 đ"),  # idx 1 — available
    ]
    candidates = [(0.9, 0), (0.8, 1)]
    out = _select_results("có tivi nào không", candidates, records, top_k=2)
    titles = [r["title"] for r in out]
    assert "Tivi UBC 32T2" not in titles
    assert "Smart Tivi Samsung 55" in titles


def test_unavailable_kept_when_query_names_model_code():
    records = [_rec("Tivi UBC 32T2 32 Inch", "Liên hệ")]
    candidates = [(0.9, 0)]
    out = _select_results("tivi ubc 32t2", candidates, records, top_k=2)
    assert [r["title"] for r in out] == ["Tivi UBC 32T2 32 Inch"]


def test_policy_note_never_filtered():
    records = [_rec("Chính sách bảo hành", None)]
    candidates = [(0.5, 0)]
    out = _select_results("chính sách bảo hành thế nào", candidates, records, top_k=2)
    assert len(out) == 1
