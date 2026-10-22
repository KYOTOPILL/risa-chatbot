import re
from pathlib import Path

import pymupdf
from docx import Document

from config import SUPPORTED_EXTS


def _pdf(path: Path) -> str:
    with pymupdf.open(path) as doc:
        return "\n".join(page.get_text() for page in doc)


def _docx(path: Path) -> str:
    return "\n".join(p.text for p in Document(path).paragraphs)


def extract_text(path: Path) -> str:
    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTS:
        raise ValueError(f"unsupported file type: {path.name}")
    if ext == ".pdf":
        text = _pdf(path)
    elif ext == ".docx":
        text = _docx(path)
    else:
        text = path.read_text(encoding="utf-8", errors="replace")
    text = text.replace("\x00", "")
    return re.sub(r"\n{3,}", "\n\n", text).strip()
