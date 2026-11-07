import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONTENT_DIR = ROOT / "content"
INDEX_DIR = ROOT / "index"

# .env holds OPENAI_API_KEY; real environment variables win
for _line in (ROOT / ".env").read_text().splitlines() if (ROOT / ".env").exists() else []:
    _k, _, _v = _line.partition("=")
    if _k.strip().isidentifier() and _v.strip():
        os.environ.setdefault(_k.strip(), _v.strip().strip("\"'"))

# Any OpenAI-compatible chat endpoint. API (default): needs OPENAI_API_KEY. Local: RISA_CHAT_BASE_URL=http://localhost:11434/v1 RISA_CHAT_MODEL=qwen3:8b
CHAT_BASE_URL = os.environ.get("RISA_CHAT_BASE_URL", "https://api.openai.com/v1")
CHAT_MODEL = os.environ.get("RISA_CHAT_MODEL", "gpt-5.4-nano")  # cheapest OpenAI chat model
EMBED_MODEL = "bge-m3"

CHUNK_SIZE = 800
CHUNK_OVERLAP = 100
SUMMARY_CHARS = 6000  # how much of a file the summary call reads
TOP_K = 4
MAX_DISTANCE = 0.6  # cosine distance; tune with evals
MAX_INFLIGHT = int(os.environ.get("RISA_MAX_INFLIGHT", "2"))  # chat questions one IP may have being answered at once; 0 = off
THAI_MIN_RATIO = 0.5  # ponytail: char-ratio heuristic lets a half-Thai reply through; use a language detector if it matters

HR_CONTACT = "ฝ่ายทรัพยากรบุคคล (HR) อีเมล hr@example.com"  # placeholder
SUPPORTED_EXTS = {".pdf", ".docx", ".xlsx", ".pptx", ".txt", ".md"}

# Tracking dashboard. ponytail: mock users until CMU email login exists; only auth.current_user should change then
# ponytail: plaintext demo passwords; real CMU login replaces this whole table
MOCK_USERS = {
    "r1": {"name": "Somchai", "role": "researcher", "username": "somchai", "password": "somchai123"},
    "r2": {"name": "Nida", "role": "researcher", "username": "nida", "password": "nida123"},
    "s1": {"name": "Malee", "role": "staff", "username": "malee", "password": "malee123"},
    "s2": {"name": "Anan", "role": "staff", "username": "anan", "password": "anan123"},
}
SESSION_SECRET = os.environ.get("RISA_SESSION_SECRET") or secrets.token_hex(32)  # unset: logins end when the server restarts
TRACKER_DB = ROOT / "tracker.db"
UPLOAD_DIR = ROOT / "uploads"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
