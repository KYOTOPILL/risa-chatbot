import hashlib
from dataclasses import dataclass
from datetime import date
from pathlib import Path

SHAREABLE = "shareable"


@dataclass(frozen=True)
class DocMeta:
    doc_id: str
    category: str
    downloadable: bool
    mtime: str
    rel_path: str


def doc_meta(path: Path, root: Path, mtime: str | None = None) -> DocMeta:
    rel = path.relative_to(root)
    folders = rel.parts[:-1]
    category = next((f for f in folders if f != SHAREABLE), "general")
    if mtime is None:
        mtime = date.fromtimestamp(path.stat().st_mtime).isoformat()
    return DocMeta(
        doc_id=hashlib.sha256(rel.as_posix().encode()).hexdigest()[:16],
        category=category,
        downloadable=SHAREABLE in folders,
        mtime=mtime,
        rel_path=rel.as_posix(),
    )
