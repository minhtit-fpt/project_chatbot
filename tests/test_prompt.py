"""Guard test cho SYSTEM_PROMPT — khoá các bất biến quan trọng của (C).

Phần (C) của plan-answer-quality nới giọng trả lời cho linh hoạt hơn (so sánh từ
dữ liệu có, bớt bail hotline, chống lặp khuôn) NHƯNG phải GIỮ ràng buộc chống bịa
giá/số liệu. Test này là lưới regression offline: nếu một lần chỉnh prompt sau này
vô tình bỏ ràng buộc chống bịa hoặc các nguyên tắc linh hoạt, test sẽ đỏ.

Không gọi API thật — chỉ kiểm tra nội dung chuỗi prompt. Việc xác minh hành vi model
thật (Daikin vs Gree không bịa số liệu) làm thủ công qua `python3 test_chat.py`.
"""
from rag.prompt_builder import SYSTEM_PROMPT


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
