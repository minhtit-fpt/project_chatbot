import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
OBSIDIAN_VAULT_PATH = Path(os.environ["OBSIDIAN_VAULT_PATH"])

EMBEDDING_MODEL = "gemini-embedding-2"
CHAT_MODEL = "gemini-2.5-flash"  # model mặc định

# Chain models thử lần lượt khi retry — đọc từ .env, fallback về CHAT_MODEL
_chain_raw = os.environ.get("CHAT_MODEL_CHAIN", CHAT_MODEL)
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
HISTORY_MAX_TURNS = 10          # số cặp Q&A gần nhất gửi lại cho model mỗi lượt
HISTORY_TTL = 1800             # seconds (30 phút) — session idle quá lâu thì quên
HISTORY_MAX_SESSIONS = 1000    # trần số session giữ trong RAM (chống rò bộ nhớ)

EXCLUDE_PATTERNS = [
    "Daily Notes",
    "Templates",
    "_templates",
    "_daily",
]
