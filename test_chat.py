"""Test chatbot trực tiếp trên terminal.

Gọi thẳng answer() (không qua HTTP API), nhưng hiển thị answer theo ĐÚNG định
dạng client/FE nhận được — mảng từng dòng đã làm sạch (qua format_answer_lines)
— để test local khớp với output thật của widget.

Usage: python test_chat.py
"""
import uuid

from api.formatting import format_answer_lines
from rag.chat_engine import answer

print("Chatbot FAQ — gõ 'quit' để thoát\n")

session_id = str(uuid.uuid4())
print(f"Session: {session_id[:8]}...\n")


def main() -> None:
    asked = 0
    while True:
        question = input("Bạn: ").strip()
        if not question or question.lower() == "quit":
            break

        result = answer(question, session_id, skip_log=True)
        asked += 1

        # answer hiển thị đúng như client/FE nhận: mảng từng dòng đã làm sạch.
        print("\nBot:")
        for line in format_answer_lines(result["answer"]):
            print(f"  {line}")

        # Thông tin debug local — KHÔNG nằm trong response gửi cho client thật.
        sources = ", ".join(s["title"] for s in result["sources"])
        # Các truy vấn đã lập kế hoạch (follow-up viết lại / câu so sánh tách nhiều
        # truy vấn) — để soi retrieval. Lượt thường giữ nguyên câu hỏi nên bỏ qua.
        queries = result.get("search_queries") or []
        if queries and queries != [question]:
            print(f"[debug] Truy vấn: {queries}")
        print(f"[debug] Nguồn (chỉ lưu DB): {sources}")
        print(f"[debug] Latency: {result['latency_ms']}ms\n")


main()
