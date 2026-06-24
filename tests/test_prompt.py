"""Guard test cho SYSTEM_PROMPT — khoá các bất biến quan trọng của (C).

Phần (C) của plan-answer-quality nới giọng trả lời cho linh hoạt hơn (so sánh từ
dữ liệu có, bớt bail hotline, chống lặp khuôn) NHƯNG phải GIỮ ràng buộc chống bịa
giá/số liệu. Test này là lưới regression offline: nếu một lần chỉnh prompt sau này
vô tình bỏ ràng buộc chống bịa hoặc các nguyên tắc linh hoạt, test sẽ đỏ.

Không gọi API thật — chỉ kiểm tra nội dung chuỗi prompt. Việc xác minh hành vi model
thật (Daikin vs Gree không bịa số liệu) làm thủ công qua `python3 test_chat.py`.
"""
import config
import rag.prompt_builder as pb
from rag.prompt_builder import SYSTEM_PROMPT, build_prompt


def test_prompt_keeps_anti_fabrication_constraint():
    """Bất biến GIỮ: không được bịa giá/số liệu, chỉ dùng dữ kiện trong tài liệu."""
    assert "Không suy đoán, không bịa số liệu hay giá cả" in SYSTEM_PROMPT


def test_prompt_comparison_handles_one_sided_data():
    """So sánh khi chỉ có dữ liệu một bên → trình bày bên có, không từ chối toàn bộ."""
    assert "chỉ có dữ liệu MỘT bên" in SYSTEM_PROMPT
    assert "không bịa thông số/giá của bên còn thiếu" in SYSTEM_PROMPT


def test_prompt_has_flexible_principles():
    """Khối nguyên tắc linh hoạt (bớt bail hotline + chống lặp khuôn) phải còn."""
    assert "NGUYÊN TẮC LINH HOẠT" in SYSTEM_PROMPT
    assert "HOÀN TOÀN không liên quan" in SYSTEM_PROMPT  # gating bail hotline
    assert "ĐIỂM KHÁC BIỆT" in SYSTEM_PROMPT             # chống lặp khuôn


def test_prompt_keeps_plain_text_rule():
    """Bất biến GIỮ: trả lời plain-text, không markdown."""
    assert "KHÔNG dùng markdown" in SYSTEM_PROMPT


def test_prompt_brand_level_feature_rule():
    """Câu hỏi tính năng/công nghệ cấp thương hiệu → chỉ nêu đặc điểm chung, không
    liệt kê từng model. Khoá cả rule lẫn ví dụ minh hoạ (ví dụ điều khiển hành vi
    model mạnh hơn câu lệnh, nên phải còn ví dụ brand-level không kèm model/giá)."""
    assert "cấp THƯƠNG HIỆU hoặc DÒNG/LOẠI nói chung" in SYSTEM_PROMPT
    assert "KHÔNG liệt kê từng sản phẩm/mã rồi kể tính năng từng cái" in SYSTEM_PROMPT
    assert "KHÔNG kèm tên model, KHÔNG kèm giá" in SYSTEM_PROMPT


def test_prompt_brand_level_comparison_rule():
    """So sánh hai thương hiệu/dòng nói chung → so ở cấp tổng quát, không đặt từng
    model rời kèm giá/specs cạnh nhau. Khoá cả rule lẫn ví dụ minh hoạ."""
    assert "So sánh hai THƯƠNG HIỆU hoặc hai DÒNG/LOẠI nói chung" in SYSTEM_PROMPT
    assert "KHÔNG liệt kê từng model rời kèm giá/specs đặt cạnh nhau" in SYSTEM_PROMPT
    assert "so sánh hai thương hiệu/dòng (TỔNG QUÁT" in SYSTEM_PROMPT


def test_prompt_has_product_link_rule():
    """Luật đính link sản phẩm phải còn (gồm dùng đúng link, không bịa)."""
    assert "LINK SẢN PHẨM:" in SYSTEM_PROMPT
    assert "Xem chi tiết" in SYSTEM_PROMPT
    assert "không gán nhầm link" in SYSTEM_PROMPT


def test_build_prompt_injects_link_by_slug():
    """Map key = slug; doc['path'] dạng 'bep/bep-abc.md' → tra theo stem 'bep-abc'."""
    pb._product_links = {"bep-abc": "https://dienmaythienphu.vn/bep/bep-abc"}
    try:
        doc = {"path": "bep/bep-abc.md", "title": "Bếp ABC", "content": "Giá: 1.000.000 đ"}
        out = build_prompt("giá bao nhiêu", [doc])
        assert "Link sản phẩm: https://dienmaythienphu.vn/bep/bep-abc" in out
    finally:
        pb._product_links = None  # reset cache cho test khác


def test_build_prompt_omits_link_when_no_match():
    """Slug không có trong map → không thêm dòng link (tránh gán nhầm)."""
    pb._product_links = {"bep-abc": "https://dienmaythienphu.vn/bep/bep-abc"}
    try:
        doc = {"path": "khong/ton-tai.md", "title": "X", "content": "abc"}
        assert "Link sản phẩm:" not in build_prompt("q", [doc])
    finally:
        pb._product_links = None
