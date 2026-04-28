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

EXCLUDE_PATTERNS = [
    "Daily Notes",
    "Templates",
    "_templates",
    "_daily",
]
