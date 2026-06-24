"""Lập kế hoạch truy vấn tìm kiếm cho retrieval (gộp viết-lại + đa-truy-vấn).

Vì sao cần: retriever embed nguyên văn câu hỏi hiện tại. Hai lỗi thực tế:
  1. Câu follow-up cụt ("giá bao nhiêu?"), sai chính tả ("điều hào", "drakin"), hoặc
     tham chiếu ngầm ("công nghệ của loại bạn vừa giới thiệu") → embedding lệch, kéo
     nhầm tài liệu.
  2. Câu SO SÁNH đa thực thể ("so sánh Daikin và Gree") chỉ một embedding bị hãng phổ
     biến lấn át → retrieval chỉ kéo tài liệu một hãng, không đủ để so sánh.

Module này (khi cần) gọi MỘT lần LLM rẻ để sinh 1–N truy vấn độc lập: follow-up →
một truy vấn sạch rút tên/mã model từ history; so sánh → mỗi thực thể một truy vấn.

Cổng gọi LLM (giữ latency câu thường): chỉ gọi planner khi (a) là follow-up
(history ≠ rỗng), hoặc (b) lượt đầu nhưng phát hiện ý SO SÁNH qua heuristic rẻ.
Câu thường lượt đầu → trả ``[question]`` ngay, KHÔNG tốn lần gọi LLM nào.

An toàn (fail-open): mọi lỗi (API down, JSON hỏng, trả rỗng) → trả ``[question]``,
KHÔNG chặn luồng trả lời. Lập kế hoạch chỉ là tối ưu retrieval, không bắt buộc.
"""
import json
import logging
import re
from typing import Any

from google.genai import types

import config

logger = logging.getLogger(__name__)

Turn = dict[str, str]

# Từ khoá rẻ phát hiện ý SO SÁNH ở lượt đầu. Chỉ là CỔNG gọi planner — planner mới
# quyết số truy vấn; nhầm (false positive) chỉ tốn thêm một lần gọi LLM ở lượt đầu,
# không sai kết quả. Vì vậy ưu tiên bắt đủ ý so sánh.
_COMPARISON_KEYWORDS = (
    "so sánh",
    "đối chiếu",
    "khác nhau",
    "khác gì",
    "nên chọn",
    "nên mua",
    "nên lấy",
    "so với",
    " vs ",
    " vs.",
)

# Mẫu lựa chọn "A hay B" — loại các "hay" không phải so sánh ("... hay không/chưa/là").
_OR_CHOICE_RE = re.compile(r"\s\S+\s+hay\s+(\S+)")
_OR_CHOICE_STOPWORDS = frozenset({"không", "chưa", "là", "sao", "gì"})

_PLANNER_INSTRUCTION = (
    "Bạn là bộ lập kế hoạch truy vấn cho hệ thống tìm kiếm sản phẩm điện máy.\n"
    "Dựa vào lịch sử hội thoại và câu hỏi mới nhất của khách (có thể viết tắt, sai "
    "chính tả, hoặc tham chiếu ngầm tới thứ đã nói trước đó), hãy sinh danh sách truy "
    "vấn tiếng Việt độc lập, đầy đủ ngữ cảnh: nêu rõ loại sản phẩm / hãng / tên hoặc "
    "mã model đang được nhắc tới.\n"
    "QUY TẮC:\n"
    f"- Chỉ trả về MỘT mảng JSON gồm 1 đến {config.MAX_SUBQUERIES} chuỗi, không giải "
    "thích, không thêm gì khác.\n"
    "- Câu hỏi SO SÁNH nhiều hãng/sản phẩm → mỗi hãng/thực thể MỘT truy vấn riêng.\n"
    "- Câu hỏi thường (kể cả follow-up) → đúng MỘT truy vấn.\n"
    "- Câu follow-up cụt/sai chính tả/tham chiếu ngầm → viết lại thành truy vấn đầy "
    "đủ, rút tên/mã model từ lịch sử.\n"
    "Ví dụ:\n"
    'Khách: "so sánh điều hòa cây Daikin và Gree"\n'
    '→ ["điều hòa cây Daikin", "điều hòa cây Gree"]\n'
    "Lịch sử liệt kê các model điều hòa cây Daikin; Khách: \"công nghệ của mấy loại đó?\"\n"
    '→ ["công nghệ điều hòa cây Daikin Inverter"]'
)


def _looks_like_comparison(question: str) -> bool:
    """Heuristic rẻ phát hiện ý SO SÁNH — chỉ là CỔNG quyết định có gọi planner hay không."""
    q = f" {question.lower()} "
    if any(kw in q for kw in _COMPARISON_KEYWORDS):
        return True
    match = _OR_CHOICE_RE.search(q)
    if match and match.group(1).strip(" ?.") not in _OR_CHOICE_STOPWORDS:
        return True
    return False


def _format_history(history: list[Turn], max_turns: int, answer_maxlen: int) -> str:
    """Ghép vài lượt gần nhất thành đoạn văn bản ngắn cho prompt planner.

    Cắt bớt câu trả lời dài để prompt gọn, nhưng vẫn đủ để model thấy tên/mã model
    đã nêu (vd danh sách 5 điều hòa cây ở lượt trước) mà rút vào truy vấn.
    """
    recent = history[-max_turns:]
    lines: list[str] = []
    for turn in recent:
        question = turn.get("question", "")
        answer = turn.get("answer", "")
        if len(answer) > answer_maxlen:
            answer = answer[:answer_maxlen] + "…"
        lines.append(f"Khách: {question}")
        lines.append(f"Bot: {answer}")
    return "\n".join(lines)


def _parse_query_list(raw: str) -> list[str]:
    """Parse mảng JSON truy vấn từ output model; trả [] nếu không hợp lệ (caller fallback).

    Model đôi khi bọc JSON trong ```fences``` hoặc thêm chữ → rút đoạn ``[...]`` đầu tiên
    rồi parse strict. Cắt theo ``config.MAX_SUBQUERIES``.
    """
    text = raw.strip()
    if not text:
        return []
    if text.startswith("```"):
        text = text.strip("`")
        newline = text.find("\n")  # bỏ nhãn ngôn ngữ ở đầu (vd "json\n[...]")
        if newline != -1:
            text = text[newline + 1:]
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []
    try:
        parsed = json.loads(text[start:end + 1])
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    queries = [str(q).strip() for q in parsed if str(q).strip()]
    return queries[:config.MAX_SUBQUERIES]


def plan_search_queries(
    question: str,
    history: list[Turn],
    *,
    client: Any,
    model: str | None = None,
    max_turns: int | None = None,
    answer_maxlen: int | None = None,
) -> list[str]:
    """Trả về 1–``MAX_SUBQUERIES`` truy vấn độc lập cho retrieval.

    Cổng gọi LLM:
      - Lượt thường (history rỗng, không có ý so sánh) → ``[question]``, KHÔNG gọi LLM.
      - Follow-up (history ≠ rỗng) HOẶC lượt đầu có ý so sánh → gọi planner LLM.
    Lỗi API / JSON hỏng / rỗng → fallback ``[question]`` (fail-open, không chặn trả lời).
    """
    needs_planner = bool(history) or _looks_like_comparison(question)
    if not needs_planner:
        return [question]

    model = model or config.QUERY_REWRITE_MODEL
    max_turns = config.QUERY_REWRITE_HISTORY_TURNS if max_turns is None else max_turns
    answer_maxlen = (
        config.QUERY_REWRITE_ANSWER_MAXLEN if answer_maxlen is None else answer_maxlen
    )

    convo = _format_history(history, max_turns, answer_maxlen) if history else "(chưa có)"
    prompt = (
        f"Lịch sử hội thoại:\n{convo}\n\n"
        f"Câu hỏi mới nhất của khách: {question}\n\n"
        "Danh sách truy vấn (mảng JSON):"
    )

    try:
        resp = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=_PLANNER_INSTRUCTION
            ),
        )
        queries = _parse_query_list(resp.text or "")
    except Exception as exc:  # noqa: BLE001 — fail-open: lỗi planner không được chặn trả lời
        logger.warning("Lập kế hoạch truy vấn thất bại (%s), dùng câu hỏi gốc", exc)
        return [question]

    return queries or [question]
