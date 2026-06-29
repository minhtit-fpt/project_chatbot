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
# Dấu * lẻ còn sót khi model mở **đậm** ở dòng này nhưng đóng ở dòng khác — split
# theo "\n" nên _BOLD (khớp cặp trong 1 dòng) không bắt được. Xoá sau khi đã đổi
# bullet "* " thành "- " để không ăn nhầm dấu bullet.
_STRAY_STAR = re.compile(r"\*+")

# FE sẽ thay marker này bằng số hotline thật (link tel:). Backend chỉ phát marker,
# không nhúng số cứng — đổi số chỉ cần sửa ở FE, không phải deploy lại bot.
# Khớp "hotline" không phân biệt hoa thường, có word boundary để không đụng từ khác.
_HOTLINE = re.compile(r"\bhotline\b", re.IGNORECASE)
HOTLINE_MARKER = "{{HOTLINE}}"

# Text hiển thị cho MỌI link — luôn ngắn gọn "Tại đây", không bao giờ lộ URL dài.
LINK_TEXT = "Tại đây"

# Bọc URL thành thẻ <a> để FE render thành link bấm được.
# LƯU Ý: chỉ có tác dụng nếu FE render mỗi dòng dưới dạng HTML. Nếu FE escape text
# thuần thì thẻ sẽ hiện literal "<a href=...>" → khi đó phải xử lý ở FE.
# Negative lookbehind (?<!href=") để không bọc lại URL đã nằm trong href của bước trước.
_URL = re.compile(r'(?<!href=")https?://[^\s<]+')
# Dòng "Xem chi tiết: <url>" → giữ nhãn, link text "Tại đây" (ẩn URL trần).
_DETAIL_LINK = re.compile(r"Xem chi tiết:\s*(https?://[^\s<]+)", re.IGNORECASE)


def _anchor(url: str, text: str) -> str:
    return f'<a href="{url}" target="_blank" rel="noopener noreferrer">{text}</a>'


def _linkify(line: str) -> str:
    """Bọc URL thành thẻ <a> cho FE render link bấm được — text luôn là "Tại đây".

    - "Xem chi tiết: <url>" → Xem chi tiết: <a href="url">Tại đây</a> (giữ nhãn, ẩn URL).
    - URL trần khác (vd model xuống dòng tách URL khỏi nhãn) → <a href="url">Tại đây</a>,
      KHÔNG dùng URL dài làm text hiển thị.
    """
    line = _DETAIL_LINK.sub(lambda m: f"Xem chi tiết: {_anchor(m.group(1), LINK_TEXT)}", line)
    return _URL.sub(lambda m: _anchor(m.group(0), LINK_TEXT), line)


def _strip_markdown(line: str) -> str:
    line = _HEADING.sub("", line)
    line = _BOLD.sub(r"\1", line)
    line = _BULLET_STAR.sub("- ", line)  # bullet "* " → "- " trước
    line = _STRAY_STAR.sub("", line)     # rồi mới xoá * lẻ còn sót (markdown hở)
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
