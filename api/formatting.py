"""Định dạng câu trả lời cho client (widget FE).

LLM trả về answer là một chuỗi nhiều dòng (ngăn bằng "\\n") kèm khoảng trắng
thừa do markdown. Tầng API tách chuỗi này thành mảng từng dòng đã làm sạch để
FE tự xuống dòng và style từng dòng — bản text đầy đủ vẫn được log ở DB.
"""
import re

_WHITESPACE_RUN = re.compile(r"\s+")

_BOLD = re.compile(r"\*{1,3}(.+?)\*{1,3}")
_HEADING = re.compile(r"^#{1,6}\s+")
_BULLET_STAR = re.compile(r"^\*\s+")


def _strip_markdown(line: str) -> str:
    line = _HEADING.sub("", line)
    line = _BOLD.sub(r"\1", line)
    line = _BULLET_STAR.sub("- ", line)
    return line


def format_answer_lines(text: str) -> list[str]:
    """Tách `text` thành list các dòng plain text đã làm sạch.

    - Strip markdown (bold, heading, bullet *).
    - Bỏ khoảng trắng thừa và dòng trống.

    Ví dụ::

        >>> format_answer_lines("**Chào bạn:**\\n\\n* Giá: 5.000.000 đ")
        ['Chào bạn:', '- Giá: 5.000.000 đ']
    """
    lines: list[str] = []
    for raw_line in text.split("\n"):
        cleaned = _strip_markdown(raw_line)
        cleaned = _WHITESPACE_RUN.sub(" ", cleaned).strip()
        if cleaned:
            lines.append(cleaned)
    return lines
