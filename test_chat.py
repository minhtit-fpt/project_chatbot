"""Test chatbot trực tiếp trên terminal.

Gọi thẳng answer() (không qua HTTP API), nhưng hiển thị answer theo ĐÚNG định
dạng client/FE nhận được — mảng từng dòng đã làm sạch (qua format_answer_lines)
— để test local khớp với output thật của widget.

Usage: python test_chat.py
"""
import uuid

from api.formatting import format_answer_lines
from rag.chat_engine import answer
from logs.sync_to_mysql import sync

print("Chatbot FAQ — gõ 'quit' để thoát\n")

session_id = str(uuid.uuid4())
print(f"Session: {session_id[:8]}...\n")


def main() -> None:
    asked = 0
    while True:
        question = input("Bạn: ").strip()
        if not question or question.lower() == "quit":
            break

        result = answer(question, session_id)
        asked += 1

        # answer hiển thị đúng như client/FE nhận: mảng từng dòng đã làm sạch.
        print("\nBot:")
        for line in format_answer_lines(result["answer"]):
            print(f"  {line}")

        # Thông tin debug local — KHÔNG nằm trong response gửi cho client thật.
        sources = ", ".join(s["title"] for s in result["sources"])
        print(f"[debug] Nguồn (chỉ lưu DB): {sources}")
        print(f"[debug] Latency: {result['latency_ms']}ms\n")

    if asked > 0:
        print("Đang sync log lên MySQL...")
        sync()
        print("Done.")


main()
