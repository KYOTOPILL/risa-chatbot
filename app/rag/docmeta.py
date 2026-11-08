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
    summary: str = ""  # Thai summary of a downloadable file, so file requests match by meaning
    sig: str = ""  # size + mtime: if unchanged, the indexed text is still current


def doc_meta(path: Path, root: Path, mtime: str | None = None) -> DocMeta:
    rel = path.relative_to(root)
    folders = rel.parts[:-1]
    category = next((f for f in folders if f != SHAREABLE), "general")
    sig = ""
    if mtime is None:
        st = path.stat()
        mtime, sig = date.fromtimestamp(st.st_mtime).isoformat(), f"{st.st_size}:{st.st_mtime_ns}"
    return DocMeta(
        doc_id=hashlib.sha256(rel.as_posix().encode()).hexdigest()[:16],
        category=category,
        downloadable=SHAREABLE in folders,
        mtime=mtime,
        rel_path=rel.as_posix(),
        sig=sig,
    )
