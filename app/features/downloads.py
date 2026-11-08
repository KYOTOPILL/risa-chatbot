from pathlib import Path

from app.rag.docmeta import SHAREABLE


def resolve_download(doc_id: str, store, content_dir: Path) -> Path | None:
    """Return the file for a downloadable indexed doc id, else None. Never accepts paths."""
    rel = store.doc_path(doc_id)
    if rel is None or SHAREABLE not in Path(rel).parts[:-1]:
        return None
    path = (content_dir / rel).resolve()
    if not path.is_relative_to(content_dir.resolve()) or not path.is_file():
        return None
    return path
