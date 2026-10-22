import logging
from pathlib import Path

from chunk import chunk_text
from config import CHUNK_OVERLAP, CHUNK_SIZE, CONTENT_DIR, SUPPORTED_EXTS
from docmeta import doc_meta
from extract import extract_text
from store import Store

log = logging.getLogger("ingest")


def build_index(content_dir: Path, store: Store) -> dict:
    items, skipped = [], []
    for path in sorted(p for p in content_dir.rglob("*") if p.is_file()):
        rel = path.relative_to(content_dir).as_posix()
        if path.name.startswith(".") or path.suffix.lower() not in SUPPORTED_EXTS:
            skipped.append(f"{rel}: unsupported")
            continue
        try:
            chunks = chunk_text(extract_text(path), CHUNK_SIZE, CHUNK_OVERLAP)
        except Exception as e:  # corrupt file must not stop the whole run
            skipped.append(f"{rel}: error {e}")
            continue
        if not chunks:
            skipped.append(f"{rel}: no extractable text (scanned?)")
            continue
        items.append((doc_meta(path, content_dir), chunks))
    store.replace_all(items)
    for s in skipped:
        log.warning("skipped %s", s)
    return {"indexed": len(items), "skipped": skipped}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(build_index(CONTENT_DIR, Store()))
