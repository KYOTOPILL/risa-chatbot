import re
from pathlib import Path

import openpyxl
import pymupdf
from docx import Document
from docx.text.paragraph import Paragraph
from pptx import Presentation

from config import SUPPORTED_EXTS


def _pdf(path: Path) -> str:
    with pymupdf.open(path) as doc:
        return "\n".join(page.get_text() for page in doc)


def _docx(path: Path) -> str:
    """Paragraphs and tables in document order; a table row becomes one line of cells joined by " | "."""
    out = []
    for block in Document(path).iter_inner_content():
        if isinstance(block, Paragraph):
            out.append(block.text)
            continue
        for row in block.rows:
            cells = []
            for c in row.cells:  # a merged cell repeats in row.cells
                t = c.text.strip().replace("\n", " ")
                if t and t not in cells:
                    cells.append(t)
            if cells:
                out.append(" | ".join(cells))
    return "\n".join(out)


MAX_SHEET_ROWS = 3000  # ponytail: a huge sheet would become hundreds of chunks; raise if real sheets are longer


def _xlsx(path: Path) -> str:
    """One paragraph per row ("Header: value | ..."), so chunking never cuts a row and every cell keeps its column name."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        out = []
        for ws in wb.worksheets:
            header = None
            for row in ws.iter_rows(values_only=True, max_row=MAX_SHEET_ROWS):
                row = ["" if c is None else str(c).strip() for c in row]
                if not any(row):
                    continue
                if header is None:
                    header = row
                    out.append(f"[{ws.title}] " + " | ".join(h for h in row if h))
                    continue
                cells = [f"{header[i]}: {v}" if i < len(header) and header[i] else v for i, v in enumerate(row) if v]
                out.append(f"[{ws.title}] " + " | ".join(cells))
        return "\n\n".join(out)
    finally:
        wb.close()


def _shape_text(shape) -> list[str]:
    if shape.shape_type == 6:  # group: look inside
        return [t for sub in shape.shapes for t in _shape_text(sub)]
    if shape.has_table:
        return [" | ".join(c.text.strip() for c in row.cells if c.text.strip()) for row in shape.table.rows]
    return [shape.text_frame.text.strip()] if shape.has_text_frame else []


def _pptx(path: Path) -> str:
    """One paragraph per slide: its text, tables and speaker notes."""
    slides = []
    for n, slide in enumerate(Presentation(path).slides, 1):
        lines = [t for shape in slide.shapes for t in _shape_text(shape) if t]
        note = slide.notes_slide.notes_text_frame.text.strip() if slide.has_notes_slide else ""
        if note:
            lines.append("Notes: " + note)
        if lines:
            slides.append(f"Slide {n}\n" + "\n".join(lines))
    return "\n\n".join(slides)


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
    elif ext == ".xlsx":
        text = _xlsx(path)
    elif ext == ".pptx":
        text = _pptx(path)
    else:
        text = path.read_text(encoding="utf-8", errors="replace")
    text = clean_thai(text.replace("\x00", ""))
    return re.sub(r"\n{3,}", "\n\n", text).strip()
