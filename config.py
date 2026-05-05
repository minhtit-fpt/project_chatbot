import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
OBSIDIAN_VAULT_PATH = Path(os.environ["OBSIDIAN_VAULT_PATH"])

EMBEDDING_MODEL = "gemini-embedding-2"

# Chain models dùng tuần tự khi retry — mỗi lần thử = 1 model khác.
# Không dùng Pro, không dùng 1.x, không dùng 2.0.
# Chạy check_api.py để xem danh sách models khả dụng trên account của bạn.
CHAT_MODEL_CHAIN = [
    "gemini-2.5-flash-lite",             # attempt 1 — primary
    "gemini-2.5-flash",        # attempt 2 
    "gemini-2.5-pro",        # attempt 3
    "gemini-3-flash-preview",               # attempt 4
    "gemini-3-pro-preview",       # attempt 5
]

INDEX_PATH = Path(__file__).parent / "data" / "index.json"
LOG_DB_PATH = Path(__file__).parent / "logs" / "conversations.db"

TOP_K = 5
RETRIEVAL_CANDIDATE_K = 30  # retrieve rộng rồi re-rank
EMBEDDING_BATCH_SIZE = 20

# Retry / timeout cho Gemini API
GEMINI_MAX_RETRIES = 5          # phải bằng len(CHAT_MODEL_CHAIN)
GEMINI_RETRY_BASE_WAIT = 1.0   # seconds, nhân đôi mỗi lần (exponential backoff)
GEMINI_RETRY_MAX_WAIT = 32.0   # giới hạn trên
GEMINI_TIMEOUT = 30.0           # timeout mỗi lần gọi API (seconds)

# Response cache (in-memory, TTL-based)
RESPONSE_CACHE_TTL = 300        # seconds (5 phút)
RESPONSE_CACHE_MAX_SIZE = 256   # số câu hỏi tối đa được cache

EXCLUDE_PATTERNS = [
    "Daily Notes",
    "Templates",
    "_templates",
    "_daily",
]
