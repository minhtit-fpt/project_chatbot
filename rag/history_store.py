"""Lưu lịch sử hội thoại theo từng session, in-memory (không cần DB).

Vì sao tách module riêng:
- `chat_engine` chỉ cần một kho nhớ nhẹ để truyền các lượt Q&A trước cho model,
  giúp chatbot "nhớ" ngữ cảnh trong cùng một phiên chat.
- Đúng triết lý "siêu nhẹ" của dự án (Phương án C): không thêm hạ tầng, không DB.

Đặc tính:
- Mỗi lượt là dict ``{"question": str, "answer": str}``.
- Chỉ giữ ``max_turns`` cặp Q&A gần nhất cho mỗi session (đủ ngữ cảnh, chặn prompt phình to).
- Session không hoạt động quá ``ttl`` giây bị coi là hết hạn → trả rỗng và xoá.
- Tổng số session bị chặn bởi ``max_sessions`` (LRU evict) để không rò bộ nhớ
  khi có nhiều phiên chat.
- Thread-safe: API chạy ``answer()`` trong thread pool (asyncio.to_thread) nên có lock.
"""
import threading
import time
from collections import OrderedDict
from typing import Callable

Turn = dict[str, str]


class SessionHistoryStore:
    """Kho lịch sử hội thoại per-session với TTL + giới hạn dung lượng."""

    def __init__(
        self,
        max_turns: int,
        ttl: float,
        max_sessions: int,
        time_func: Callable[[], float] = time.time,
    ) -> None:
        # session_id -> (danh sách lượt, timestamp cập nhật cuối)
        self._store: OrderedDict[str, tuple[list[Turn], float]] = OrderedDict()
        self._max_turns = max_turns
        self._ttl = ttl
        self._max_sessions = max_sessions
        self._now = time_func  # tách ra để test TTL không cần sleep thật
        self._lock = threading.Lock()

    def get(self, session_id: str) -> list[Turn]:
        """Trả lịch sử (bản sao) của session; rỗng nếu chưa có hoặc đã hết hạn."""
        with self._lock:
            entry = self._store.get(session_id)
            if entry is None:
                return []
            turns, updated_at = entry
            if self._now() - updated_at > self._ttl:
                del self._store[session_id]
                return []
            self._store.move_to_end(session_id)
            # Bản sao sâu (mỗi turn là dict mới) để caller không mutate state nội bộ.
            return [dict(t) for t in turns]

    def append(self, session_id: str, question: str, answer: str) -> None:
        """Ghi thêm một lượt Q&A vào lịch sử của session."""
        turn: Turn = {"question": question, "answer": answer}
        with self._lock:
            now = self._now()
            entry = self._store.get(session_id)
            if entry is None or now - entry[1] > self._ttl:
                prev: list[Turn] = []  # phiên mới hoặc đã hết hạn → khởi tạo lại
            else:
                prev = entry[0]
            # Tạo list mới (immutable update), chỉ giữ max_turns lượt gần nhất.
            turns = [*prev, turn][-self._max_turns:]
            self._store[session_id] = (turns, now)
            self._store.move_to_end(session_id)
            self._evict_locked(now)

    def _evict_locked(self, now: float) -> None:
        """Dọn session hết hạn + chặn trần số session. Gọi khi đang giữ lock."""
        expired = [
            sid for sid, (_, updated_at) in self._store.items()
            if now - updated_at > self._ttl
        ]
        for sid in expired:
            del self._store[sid]
        while len(self._store) > self._max_sessions:
            self._store.popitem(last=False)  # bỏ session cũ nhất (LRU)
