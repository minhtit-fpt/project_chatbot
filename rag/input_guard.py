"""Chặn input rác (gõ phím ngẫu nhiên) TRƯỚC khi vào pipeline RAG.

Vì sao cần: log production 2026-08-08 có 64/498 câu dưới 15 ký tự, trong đó ~30 câu
gần nhất là gõ phím ngẫu nhiên ("Ehfubrfuehfbrfuehf", "Vhrfurhfurvfurhufrhfuhrufhrfu").
Mỗi câu vẫn tốn 1 lần embedding + 1 lần gọi LLM; record id=310
("Beheuysydgh3vssgyggsgsy") mất 29 giây. Bắt ở tầng code rẻ hơn nhiều lần gọi API.

Nguyên tắc: THÀ BỎ SÓT CÒN HƠN CHẶN NHẦM. Câu cụt hợp lệ ("giá bao nhiêu?", "Tôi ở
HN", "18.000 BTU", "5.") và câu hỏi theo mã SKU ("SJ-FXP560V-BK", "u9bkh") PHẢI lọt
qua — chặn nhầm một câu thật tệ hơn nhiều so với tốn thêm một lần gọi API cho rác.
"""
import re
import unicodedata

# Câu trả lời tĩnh cho input rác — không gọi Gemini, không retrieve.
GIBBERISH_REPLY = (
    "Dạ em chưa hiểu ý câu hỏi của mình ạ. Anh/chị vui lòng nhập lại câu hỏi về sản "
    "phẩm hoặc dịch vụ bên em (tên sản phẩm, giá, bảo hành, lắp đặt…) để em hỗ trợ nhé."
)

# Chuỗi chữ cái liên tiếp (chữ số/dấu câu là ranh giới) — mã model "fxp560v" bị
# tách thành "fxp"/"v" nên không bao giờ dính ngưỡng độ dài bên dưới.
_LETTER_RUN_RE = re.compile(r"[^\W\d_]+", re.UNICODE)

# Âm tiết tiếng Việt dài nhất là 7 chữ cái ("nghiêng"). Chuỗi chữ cái liền không
# khoảng trắng dài hơn ngưỡng này gần như chắc chắn không phải một từ.
_MIN_GIBBERISH_LEN = 11

# ponytail: ngưỡng nguyên âm là heuristic, biên khá sát — "khuyenmaithang" (0.36) lọt,
# "Ehfubrfuehfbrfuehf" (0.33) bị chặn. Nếu về sau chặn nhầm, nâng ngưỡng độ dài
# (_MIN_GIBBERISH_LEN) trước, đừng hạ ngưỡng nguyên âm.
_MIN_VOWEL_RATIO = 0.34

# "y" CỐ TÌNH không tính là nguyên âm: chuỗi rác hay lặp "gy", "sy", "yd" (vd
# "Beheuysydgh"), tính y vào sẽ đẩy tỉ lệ lên trên ngưỡng và bỏ sót.
_VOWELS = frozenset("aeiou")


def _vowel_ratio(run: str) -> float:
    """Tỉ lệ nguyên âm trong một chuỗi chữ cái, tính cả nguyên âm có dấu (ề, ạ, ữ…)."""
    base = [
        c for c in unicodedata.normalize("NFD", run.lower())
        if unicodedata.category(c) != "Mn"
    ]
    if not base:
        return 0.0
    return sum(1 for c in base if c in _VOWELS) / len(base)


def is_gibberish(question: str) -> bool:
    """True nếu câu hỏi là rác rõ ràng (gõ phím ngẫu nhiên hoặc rỗng nghĩa)."""
    q = question.strip()
    if not q:
        return True

    letters = [c for c in q if c.isalpha()]
    digits = [c for c in q if c.isdigit()]

    # Không có chữ lẫn số (chỉ dấu câu/emoji) → không có gì để tra cứu.
    if not letters and not digits:
        return True

    # Một chữ cái đơn độc ("O", "b") — không đủ để tra cứu. Số đứng một mình
    # KHÔNG bị chặn: "5." là chọn mục trong danh sách gợi ý, "014040" là mã hàng.
    if len(letters) == 1 and not digits:
        return True

    return any(
        len(run) >= _MIN_GIBBERISH_LEN and _vowel_ratio(run) < _MIN_VOWEL_RATIO
        for run in _LETTER_RUN_RE.findall(q)
    )
