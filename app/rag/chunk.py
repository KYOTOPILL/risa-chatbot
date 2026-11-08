import re


def chunk_text(text: str, size: int, overlap: int) -> list[str]:
    """Greedy pack paragraphs up to `size`; hard-split anything longer (e.g. Thai without spaces)."""
    pieces: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        while len(para) > size:
            pieces.append(para[:size])
            para = para[size - overlap:]
        if para:
            pieces.append(para)
    chunks: list[str] = []
    cur = ""
    for piece in pieces:
        if cur and len(cur) + 2 + len(piece) <= size:
            cur += "\n\n" + piece
            continue
        if cur:
            chunks.append(cur)
            tail = cur[-overlap:] if overlap else ""
            cur = tail + piece if len(tail) + len(piece) <= size else piece
        else:
            cur = piece
    if cur:
        chunks.append(cur)
    return chunks
