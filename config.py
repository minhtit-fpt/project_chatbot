import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
OBSIDIAN_VAULT_PATH = Path(os.environ["OBSIDIAN_VAULT_PATH"])

EMBEDDING_MODEL = "gemini-embedding-2"
CHAT_MODEL = "gemini-2.5-flash"  # fallback: gemini-2.0-flash

INDEX_PATH = Path(__file__).parent / "data" / "index.json"
LOG_DB_PATH = Path(__file__).parent / "logs" / "conversations.db"

TOP_K = 5
RETRIEVAL_CANDIDATE_K = 30  # retrieve rộng rồi re-rank
EMBEDDING_BATCH_SIZE = 20

# Retry / timeout cho Gemini API
GEMINI_MAX_RETRIES = 5
GEMINI_RETRY_BASE_WAIT = 1.0   # seconds, nhân đôi mỗi lần (exponential backoff)
GEMINI_RETRY_MAX_WAIT = 32.0   # giới hạn trên
GEMINI_TIMEOUT = 30.0           # timeout mỗi lần gọi API (seconds)
CHAT_FALLBACK_MODEL = "gemini-2.0-flash"  # dùng khi model chính 503

# Response cache (in-memory, TTL-based)
RESPONSE_CACHE_TTL = 300        # seconds (5 phút)
RESPONSE_CACHE_MAX_SIZE = 256   # số câu hỏi tối đa được cache

EXCLUDE_PATTERNS = [
    "Daily Notes",
    "Templates",
    "_templates",
    "_daily",
]
