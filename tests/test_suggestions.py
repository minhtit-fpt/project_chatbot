"""Unit tests cho tách/định dạng phần gợi ý hỏi tiếp (guided selling).

Bao phủ:
- split_answer_and_suggestions: có marker → tách đúng answer/suggestions + cap;
  không marker → (raw, []); marker nhưng phần dưới rỗng/rác → []; marker bị loại
  khỏi answer; nhiều dòng bullet xen dòng trống → lọc đúng.
- join_answer_and_suggestions: round-trip giữ lại phần gợi ý cho history.
- format_answer_with_suggestions: có suggestions → dòng dẫn + đủ dòng gợi ý; không
  có → chỉ các dòng answer (không dòng dẫn thừa).

Không gọi API thật — chỉ thao tác chuỗi.
"""
import config
from api.formatting import format_answer_with_suggestions
from rag.suggestions import join_answer_and_suggestions, split_answer_and_suggestions

MARKER = config.SUGGESTIONS_MARKER


# ── split_answer_and_suggestions ─────────────────────────────────────────────

def test_split_no_marker_returns_raw_and_empty():
    raw = "1. Điều hòa Daikin\n- Giá: 10.000.000 đ"
    answer, suggestions = split_answer_and_suggestions(raw)
    assert answer == raw
    assert suggestions == []


def test_split_with_marker_separates_answer_and_suggestions():
    raw = (
        "1. Điều hòa Daikin\n- Giá: 10.000.000 đ\n\n"
        f"{MARKER}\n"
        "- Phòng mình rộng khoảng bao nhiêu m² ạ?\n"
        "- Anh/chị muốn loại Inverter tiết kiệm điện không ạ?"
    )
    answer, suggestions = split_answer_and_suggestions(raw)
    assert answer == "1. Điều hòa Daikin\n- Giá: 10.000.000 đ"
    assert suggestions == [
        "Phòng mình rộng khoảng bao nhiêu m² ạ?",
        "Anh/chị muốn loại Inverter tiết kiệm điện không ạ?",
    ]


def test_split_removes_marker_from_answer():
    raw = f"Trả lời.\n{MARKER}\n- Câu hỏi gợi ý?"
    answer, _ = split_answer_and_suggestions(raw)
    assert MARKER not in answer
    assert answer == "Trả lời."


def test_split_caps_at_max_suggestions():
    bullets = "\n".join(f"- Gợi ý {i}?" for i in range(config.MAX_SUGGESTIONS + 3))
    raw = f"Trả lời.\n{MARKER}\n{bullets}"
    _, suggestions = split_answer_and_suggestions(raw)
    assert len(suggestions) == config.MAX_SUGGESTIONS


def test_split_marker_with_empty_body_yields_no_suggestions():
    raw = f"Trả lời sản phẩm.\n{MARKER}\n   \n\n"
    answer, suggestions = split_answer_and_suggestions(raw)
    assert suggestions == []
    assert answer == "Trả lời sản phẩm."


def test_split_marker_with_garbage_body_yields_no_suggestions():
    raw = f"Trả lời.\n{MARKER}\nkhông phải bullet, chỉ là văn xuôi rác"
    _, suggestions = split_answer_and_suggestions(raw)
    assert suggestions == []


def test_split_filters_blank_lines_between_bullets():
    raw = f"Trả lời.\n{MARKER}\n- A?\n\n- B?\n   \n- C?"
    _, suggestions = split_answer_and_suggestions(raw)
    assert suggestions == ["A?", "B?", "C?"]


# ── join_answer_and_suggestions (round-trip cho history) ─────────────────────

def test_join_without_suggestions_returns_answer_unchanged():
    assert join_answer_and_suggestions("Trả lời.", []) == "Trả lời."


def test_join_then_split_round_trips():
    answer = "1. Daikin\n- Giá: 10tr"
    suggestions = ["Phòng bao nhiêu m²?", "Ngân sách tầm bao nhiêu?"]
    raw = join_answer_and_suggestions(answer, suggestions)
    assert MARKER in raw
    back_answer, back_suggestions = split_answer_and_suggestions(raw)
    assert back_answer == answer
    assert back_suggestions == suggestions


# ── format_answer_with_suggestions ───────────────────────────────────────────

def test_format_without_suggestions_has_no_lead_in():
    lines = format_answer_with_suggestions("**Chào bạn:**\n* Giá: 5.000.000 đ", [])
    assert lines == ["Chào bạn:", "- Giá: 5.000.000 đ"]
    assert config.SUGGESTIONS_LEAD_IN not in lines


def test_format_with_suggestions_appends_lead_in_and_bullets():
    lines = format_answer_with_suggestions(
        "1. Daikin", ["Phòng bao nhiêu m²?", "Ngân sách?"]
    )
    assert lines[0] == "1. Daikin"
    assert config.SUGGESTIONS_LEAD_IN in lines
    idx = lines.index(config.SUGGESTIONS_LEAD_IN)
    assert lines[idx + 1:] == ["- Phòng bao nhiêu m²?", "- Ngân sách?"]
