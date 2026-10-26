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


# Thai PDFs often use a font's private-use glyphs for lowered tone marks/vowels; map them back to real Thai
_PUA = {0xF701: "\u0e34", 0xF702: "\u0e35", 0xF703: "\u0e36", 0xF704: "\u0e37", 0xF710: "\u0e31",
        0xF711: "\u0e4d", 0xF712: "\u0e47", 0xF0B7: "\u2022"}
for _i, _c in enumerate("\u0e48\u0e49\u0e4a\u0e4b\u0e4c"):
    _PUA[0xF70A + _i] = _c  # lowered mai ek/tho/tri/chattawa/thanthakhat
    _PUA[0xF705 + _i] = _c
    _PUA[0xF713 + _i] = _c
_PUA_RE = re.compile("[\ue000-\uf8ff]")


def clean_thai(text: str) -> str:
    # unknown private-use characters are dropped: they carry no meaning outside their font
    text = _PUA_RE.sub(lambda m: _PUA.get(ord(m.group()), ""), text)
    return text.replace("\u0e4d\u0e32", "\u0e33")  # PDFs often split sara am into nikhahit + sara aa


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
    text = clean_thai(text.replace("\x00", ""))
    return re.sub(r"\n{3,}", "\n\n", text).strip()
