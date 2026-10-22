from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONTENT_DIR = ROOT / "content"
INDEX_DIR = ROOT / "index"

CHAT_MODEL = "qwen3:8b"  # confirm newest Qwen instruct ~8B tag with `ollama list`
EMBED_MODEL = "bge-m3"

CHUNK_SIZE = 800
CHUNK_OVERLAP = 100
TOP_K = 5
MAX_DISTANCE = 0.6  # cosine distance; tune with evals
THAI_MIN_RATIO = 0.5

HR_CONTACT = "ฝ่ายทรัพยากรบุคคล (HR) อีเมล hr@example.com"  # placeholder
SUPPORTED_EXTS = {".pdf", ".docx", ".txt", ".md"}
