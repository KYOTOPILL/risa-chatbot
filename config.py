import os
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
THAI_MIN_RATIO = 0.5  # ponytail: char-ratio heuristic lets a half-Thai reply through; use a language detector if it matters

HR_CONTACT = "ฝ่ายทรัพยากรบุคคล (HR) อีเมล hr@example.com"  # placeholder
SUPPORTED_EXTS = {".pdf", ".docx", ".xlsx", ".pptx", ".txt", ".md"}
