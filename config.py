import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
OBSIDIAN_VAULT_PATH = Path(os.environ["OBSIDIAN_VAULT_PATH"])

EMBEDDING_MODEL = "gemini-embedding-2"
CHAT_MODEL = "gemini-2.5-flash-lite"  # model mặc định

# Chain 3 model thử lần lượt khi lỗi/rỗng — leo thang theo năng lực:
#   1. flash-lite : nhanh/rẻ nhất, xử lý phần lớn câu FAQ (mặc định).
#   2. flash      : mục tiêu production, mạnh hơn khi lite lỗi/bị chặn.
#   3. pro        : mạnh nhất, lưới an toàn cuối cho câu phức tạp.
# Đọc từ .env (CHAT_MODEL_CHAIN, phân tách bằng dấu phẩy) — override được default này.
_DEFAULT_CHAT_MODEL_CHAIN = "gemini-2.5-flash-lite,gemini-2.5-flash,gemini-2.5-pro"
_chain_raw = os.environ.get("CHAT_MODEL_CHAIN", _DEFAULT_CHAT_MODEL_CHAIN)
CHAT_MODEL_CHAIN: list[str] = [m.strip() for m in _chain_raw.split(",") if m.strip()]

INDEX_PATH = Path(__file__).parent / "data" / "index.json"

# Múi giờ ứng dụng — mặc định Việt Nam (UTC+7). Đổi qua biến môi trường APP_TIMEZONE.
# Dùng ZoneInfo nên độc lập với timezone của container/host (container Docker mặc định UTC).
# Cần gói `tzdata` trong requirements.txt để ZoneInfo chạy được trên image python slim.
TIMEZONE = ZoneInfo(os.environ.get("APP_TIMEZONE", "Asia/Ho_Chi_Minh"))


def now_local() -> datetime:
    """Giờ hiện tại theo TIMEZONE, trả về naive datetime (wall-clock UTC+7).

    Để naive cho khớp cột MySQL DATETIME (không lưu offset) và giữ nguyên format
    timestamp trong JSONL — khác biệt duy nhất so với trước là giờ đã là UTC+7
    thay vì UTC mặc định của container.
    """
    return datetime.now(TIMEZONE).replace(tzinfo=None)

# CORS — comma-separated origins, e.g. "https://example.com,https://shop.example.com"
# Dùng "*" cho môi trường dev/local. Production nên set cụ thể.
_origins_raw = os.environ.get("ALLOWED_ORIGINS", "*")
ALLOWED_ORIGINS: list[str] = [o.strip() for o in _origins_raw.split(",") if o.strip()]

# MySQL logging
MYSQL_HOST = os.environ.get("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))
MYSQL_USER = os.environ.get("MYSQL_USER", "")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "chatbot_logs")

TOP_K = 5
RETRIEVAL_CANDIDATE_K = 100  # retrieve rộng rồi re-rank với keyword + policy boost
FEATURED_BOOST = 0.08  # cộng điểm cho note hãng nổi tiếng (frontmatter `featured: true`)
EMBEDDING_BATCH_SIZE = 20

# Retry / timeout cho Gemini API
GEMINI_MAX_RETRIES = len(CHAT_MODEL_CHAIN)  # tự động theo chain
GEMINI_RETRY_BASE_WAIT = 1.0   # seconds, nhân đôi mỗi lần (exponential backoff)
GEMINI_RETRY_MAX_WAIT = 32.0   # giới hạn trên
GEMINI_TIMEOUT = 30.0           # timeout mỗi lần gọi API (seconds)

# Response cache (in-memory, TTL-based)
RESPONSE_CACHE_TTL = 300        # seconds (5 phút)
RESPONSE_CACHE_MAX_SIZE = 256   # số câu hỏi tối đa được cache

# Conversation memory (in-memory per-session — giúp chatbot nhớ ngữ cảnh trong phiên)
HISTORY_MAX_TURNS = 20          # số cặp Q&A gần nhất gửi lại cho model mỗi lượt
HISTORY_TTL = 1800             # seconds (30 phút) — session idle quá lâu thì quên
HISTORY_MAX_SESSIONS = 1000    # trần số session giữ trong RAM (chống rò bộ nhớ)

# Lập kế hoạch truy vấn (retrieval query planner) — gộp viết-lại + đa-truy-vấn.
# Hai lỗi retrieval mà planner xử lý:
#   1. Câu follow-up cụt/sai chính tả/tham chiếu ngầm ("công nghệ loại bạn vừa giới thiệu")
#      nếu embed nguyên văn sẽ kéo nhầm tài liệu → viết lại thành 1 query độc lập.
#   2. Câu SO SÁNH đa thực thể ("so sánh Daikin và Gree") chỉ một embedding bị hãng phổ
#      biến lấn át → tách mỗi thực thể 1 query rồi merge cân bằng.
# Cổng gọi LLM giữ latency câu thường: chỉ gọi planner khi follow-up hoặc lượt đầu có ý so sánh.
QUERY_REWRITE_MODEL = "gemini-2.5-flash"   # model nhanh/rẻ cho planner (không dùng lite)
QUERY_REWRITE_HISTORY_TURNS = 4            # số lượt gần nhất đưa vào prompt planner
QUERY_REWRITE_ANSWER_MAXLEN = 1200         # cắt bớt câu trả lời dài trong history
MAX_SUBQUERIES = 3                         # trần số truy vấn con planner được sinh
MAX_CONTEXT_DOCS = 8                       # trần số tài liệu sau khi merge đa-query + carry-forward

# Gợi ý hỏi tiếp (guided selling) — model TỰ xuất phần gợi ý sau marker khi câu hỏi
# còn rộng/mơ hồ (không thêm lần gọi LLM riêng). BE tách marker → answer sạch + list gợi ý.
MAX_SUGGESTIONS = 3
SUGGESTIONS_MARKER = "###GỢI_Ý###"
SUGGESTIONS_LEAD_IN = "Để tư vấn sát hơn, anh/chị cho em hỏi thêm:"

EXCLUDE_PATTERNS = [
    "Daily Notes",
    "Templates",
    "_templates",
    "_daily",
]
