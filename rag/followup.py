"""Phát hiện câu hỏi PHỤ THUỘC NGỮ CẢNH (referential follow-up) — câu chỉ có nghĩa
khi đặt trong mạch hội thoại trước đó (vd "thế nên mua loại nào", "giá bao nhiêu").

Vì sao cần (defense-in-depth cho cache):
`_response_cache` ở chat_engine CHỈ được dùng khi history rỗng, và đánh khoá theo
NGUYÊN VĂN câu hỏi, dùng CHUNG cho mọi session. Một câu follow-up cụt như
"thế nên mua loại nào" nếu lọt vào engine lúc history rỗng (vd FE không giữ
`session_id` → mỗi request là một session mới) sẽ trúng đáp án đã cache của MỘT
phiên khác (vd máy giặt) → trả nhầm hẳn nhóm sản phẩm. Nhận diện các câu này để
BỎ QUA cache (đọc lẫn ghi), buộc retrieve lại thay vì phục vụ đáp án nhiễm chéo phiên.

Triết lý như cổng so sánh ở `query_rewriter`: thà nhận nhầm (false positive) — chỉ
tốn một lần miss cache (retrieve lại) — còn hơn phục vụ đáp án sai nhóm. Vì vậy bắt
rộng. Hệ quả đã biết: câu mở đầu bằng "thế giới…" cũng bị coi là follow-up; vô hại
vì chỉ làm lỡ cache, không bao giờ trả sai.
"""
import re

# Hư từ diễn ngôn mở đầu, trỏ về thứ vừa nói ("thế…", "vậy…", "còn…").
_DISCOURSE_OPENER_RE = re.compile(r"^(thế|vậy|còn)\b")

# Chỉ định trỏ ngược về một mục đã nêu ở lượt trước (không nêu lại tên sản phẩm).
_REFERENTIAL_MARKERS = (
    "loại đó", "loại này", "loại kia", "loại ấy", "loại đấy",
    "cái đó", "cái này", "cái kia", "cái ấy", "cái đấy",
    "mẫu đó", "mẫu này", "mẫu kia",
    "con đó", "con này", "con kia",
    "máy đó", "máy này", "máy kia",
    "em đó", "bên đó", "hãng đó",
)

# Câu chỉ gồm "bộ chọn" trống, không nêu sản phẩm: "(thế/vậy) (thì) (nên) mua loại nào".
_BARE_SELECTOR_RE = re.compile(
    r"^(thế|vậy)?\s*(thì)?\s*(nên|cần|muốn)?\s*(mua|lấy|chọn|dùng|xài)?\s*"
    r"(loại|cái|mẫu|con|chiếc|máy)\s+nào\b"
)

# Câu hỏi giá/thông số đứng MỘT MÌNH (vô nghĩa nếu thiếu ngữ cảnh): "giá bao nhiêu",
# "bao nhiêu tiền". Neo ^ để KHÔNG bắt câu đã nêu sản phẩm ("Daikin X giá bao nhiêu").
_BARE_PRICE_RE = re.compile(
    r"^(giá( cả)?\s+(bao nhiêu|thế nào|sao)|bao nhiêu( tiền)?\b)"
)


def is_referential_followup(question: str) -> bool:
    """True nếu câu hỏi chỉ có nghĩa trong ngữ cảnh hội thoại trước (không tự đứng).

    Bắt rộng (fail-safe cho cache): nhận nhầm chỉ tốn một lần retrieve lại, không
    bao giờ gây trả lời sai nhóm sản phẩm.
    """
    q = question.strip().lower()
    if not q:
        return False
    if _DISCOURSE_OPENER_RE.match(q):
        return True
    if any(marker in q for marker in _REFERENTIAL_MARKERS):
        return True
    if _BARE_SELECTOR_RE.match(q):
        return True
    if _BARE_PRICE_RE.match(q):
        return True
    return False
