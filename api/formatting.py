"""Định dạng câu trả lời cho client (widget FE).

LLM trả về answer là một chuỗi nhiều dòng (ngăn bằng "\\n") kèm khoảng trắng
thừa do markdown. Tầng API tách chuỗi này thành mảng từng dòng đã làm sạch để
FE tự xuống dòng và style từng dòng — bản text đầy đủ vẫn được log ở DB.
"""
import re

import config

_WHITESPACE_RUN = re.compile(r"\s+")

_BOLD = re.compile(r"\*{1,3}(.+?)\*{1,3}")
_HEADING = re.compile(r"^#{1,6}\s+")
_BULLET_STAR = re.compile(r"^\*\s+")

# FE sẽ thay marker này bằng số hotline thật (link tel:). Backend chỉ phát marker,
# không nhúng số cứng — đổi số chỉ cần sửa ở FE, không phải deploy lại bot.
# Khớp "hotline" không phân biệt hoa thường, có word boundary để không đụng từ khác.
_HOTLINE = re.compile(r"\bhotline\b", re.IGNORECASE)
HOTLINE_MARKER = "{{HOTLINE}}"

# Bọc URL trần thành thẻ <a> để FE render thành link bấm được.
# LƯU Ý: chỉ có tác dụng nếu FE render mỗi dòng dưới dạng HTML. Nếu FE escape text
# thuần thì thẻ sẽ hiện literal "<a href=...>" → khi đó phải xử lý ở FE.
_URL = re.compile(r"https?://[^\s<]+")


def _linkify(line: str) -> str:
    return _URL.sub(
        lambda m: f'<a href="{m.group(0)}" target="_blank" rel="noopener noreferrer">'
                  f'{m.group(0)}</a>',
        line,
    )


def _strip_markdown(line: str) -> str:
    line = _HEADING.sub("", line)
    line = _BOLD.sub(r"\1", line)
    line = _BULLET_STAR.sub("- ", line)
    return line


def format_answer_lines(text: str) -> list[str]:
    """Tách `text` thành list các dòng plain text đã làm sạch.

    - Strip markdown (bold, heading, bullet *).
    - Bỏ khoảng trắng thừa và dòng trống.
    - Thay mọi chữ "hotline" bằng marker ``{{HOTLINE}}`` để FE render thành số/link.

    Ví dụ::

        >>> format_answer_lines("**Chào bạn:**\\n\\n* Giá: 5.000.000 đ")
        ['Chào bạn:', '- Giá: 5.000.000 đ']
        >>> format_answer_lines("Liên hệ Hotline để được hỗ trợ")
        ['Liên hệ {{HOTLINE}} để được hỗ trợ']
    """
    lines: list[str] = []
    for raw_line in text.split("\n"):
        cleaned = _strip_markdown(raw_line)
        cleaned = _WHITESPACE_RUN.sub(" ", cleaned).strip()
        cleaned = _HOTLINE.sub(HOTLINE_MARKER, cleaned)
        cleaned = _linkify(cleaned)
        if cleaned:
            lines.append(cleaned)
    return lines


def format_answer_with_suggestions(answer: str, suggestions: list[str]) -> list[str]:
    """Như ``format_answer_lines`` nhưng nối thêm phần gợi ý hỏi tiếp (nếu có).

    Khi ``suggestions`` không rỗng → thêm 1 dòng dẫn ``config.SUGGESTIONS_LEAD_IN``
    rồi mỗi gợi ý thành một dòng ``- <gợi ý>`` (đã làm sạch khoảng trắng). Không có
    gợi ý → trả đúng các dòng answer, không thêm dòng dẫn thừa.
    """
    lines = format_answer_lines(answer)
    if not suggestions:
        return lines
    lines.append(config.SUGGESTIONS_LEAD_IN)
    for suggestion in suggestions:
        cleaned = _WHITESPACE_RUN.sub(" ", suggestion).strip()
        if cleaned:
            lines.append(f"- {cleaned}")
    return lines
