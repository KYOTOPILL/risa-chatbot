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

CHAT_MODEL = "gpt-5-nano"  # cheapest OpenAI chat model; needs OPENAI_API_KEY env var
EMBED_MODEL = "bge-m3"

CHUNK_SIZE = 800
CHUNK_OVERLAP = 100
TOP_K = 4
MAX_DISTANCE = 0.6  # cosine distance; tune with evals
THAI_MIN_RATIO = 0.5  # ponytail: char-ratio heuristic lets a half-Thai reply through; use a language detector if it matters
FILE_MARGIN = 0.15  # downloadable doc must be this close to the best hit; tune with evals

HR_CONTACT = "ฝ่ายทรัพยากรบุคคล (HR) อีเมล hr@example.com"  # placeholder
SUPPORTED_EXTS = {".pdf", ".docx", ".txt", ".md"}
