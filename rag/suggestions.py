"""Tách phần "gợi ý hỏi tiếp" (guided selling) khỏi câu trả lời thô của model.

Khi câu hỏi của khách còn RỘNG/mơ hồ, model được yêu cầu xuất thêm tối đa
``config.MAX_SUGGESTIONS`` câu hỏi gợi ý, đặt sau một marker cố định
(``config.SUGGESTIONS_MARKER``) ngay trong cùng lần gọi LLM trả lời — KHÔNG thêm
lần gọi riêng. Module này là tầng parse fail-safe:

- Có marker → answer sạch (phần trên) + danh sách câu gợi ý (các dòng ``- …`` phần dưới).
- Không marker (câu cụ thể) → ``(raw, [])``.
- Marker nhưng phần dưới rỗng/rác/format lệch → ``[]``; answer vẫn nguyên vẹn,
  marker bị loại để không lọt xuống FE.
"""
import re

import config

# Một dòng gợi ý hợp lệ bắt đầu bằng bullet (-, *, •) rồi tới nội dung câu hỏi.
_BULLET_LINE = re.compile(r"^\s*[-*•]\s+(.+?)\s*$")


def split_answer_and_suggestions(raw: str) -> tuple[str, list[str]]:
    """Tách ``raw`` thành ``(answer_sạch, danh_sách_gợi_ý)``.

    Cắt tại lần xuất hiện đầu tiên của ``config.SUGGESTIONS_MARKER``. Phần trên là
    answer (đã rstrip khoảng trắng/dòng trống thừa); phần dưới được quét lấy các dòng
    bullet làm câu gợi ý, strip và giới hạn ``config.MAX_SUGGESTIONS``.

    Fail-safe: không marker → ``(raw, [])``; có marker nhưng không parse được gợi ý
    hợp lệ → ``(answer_trên_marker, [])`` (marker không lọt vào answer).
    """
    marker = config.SUGGESTIONS_MARKER
    if marker not in raw:
        return raw, []

    answer_part, _, suggestion_part = raw.partition(marker)
    answer = answer_part.rstrip()

    suggestions: list[str] = []
    for line in suggestion_part.splitlines():
        match = _BULLET_LINE.match(line)
        if not match:
            continue
        text = match.group(1).strip()
        if text:
            suggestions.append(text)
        if len(suggestions) >= config.MAX_SUGGESTIONS:
            break

    return answer, suggestions


def join_answer_and_suggestions(answer: str, suggestions: list[str]) -> str:
    """Ghép answer sạch + phần gợi ý lại thành text thô (dạng model đã xuất).

    Dùng cho lịch sử hội thoại: history giữ answer KÈM phần gợi ý để planner/model
    các lượt sau thấy "Bot đã hỏi: phòng bao nhiêu m²?" → khép đúng vòng dẫn dắt.
    Không có gợi ý → trả answer nguyên vẹn (không thêm marker thừa).
    """
    if not suggestions:
        return answer
    lines = "\n".join(f"- {s}" for s in suggestions)
    return f"{answer}\n\n{config.SUGGESTIONS_MARKER}\n{lines}"
