"""Định dạng câu trả lời cho client (widget FE).

LLM trả về answer là một chuỗi nhiều dòng (ngăn bằng "\\n") kèm khoảng trắng
thừa do markdown. Tầng API tách chuỗi này thành mảng từng dòng đã làm sạch để
FE tự xuống dòng và style từng dòng — bản text đầy đủ vẫn được log ở DB.
"""
import re

# Gộp mọi cụm khoảng trắng liên tiếp (space, tab...) thành 1 space.
_WHITESPACE_RUN = re.compile(r"\s+")


def format_answer_lines(text: str) -> list[str]:
    """Tách `text` thành list các dòng đã làm sạch.

    - Mỗi phần tử là một dòng nội dung.
    - Bỏ khoảng trắng đầu/cuối và gộp khoảng trắng thừa ở giữa thành 1 space.
    - Bỏ các dòng trống (sinh ra từ "\\n\\n").

    Ví dụ::

        >>> format_answer_lines("Chào bạn:\\n\\n    *   Giá:  5.000.000 đ")
        ['Chào bạn:', '* Giá: 5.000.000 đ']
    """
    lines: list[str] = []
    for raw_line in text.split("\n"):
        cleaned = _WHITESPACE_RUN.sub(" ", raw_line).strip()
        if cleaned:
            lines.append(cleaned)
    return lines
