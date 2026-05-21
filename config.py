import os
from pathlib import Path
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
LOG_DB_PATH = Path(__file__).parent / "logs" / "conversations.db"

TOP_K = 5
RETRIEVAL_CANDIDATE_K = 30  # retrieve rộng rồi re-rank
EMBEDDING_BATCH_SIZE = 20

# Retry / timeout cho Gemini API
GEMINI_MAX_RETRIES = len(CHAT_MODEL_CHAIN)  # tự động theo chain
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
