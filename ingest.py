import dataclasses
import logging
from pathlib import Path

from chunk import chunk_text
from config import CHUNK_OVERLAP, CHUNK_SIZE, CONTENT_DIR, SUMMARY_CHARS, SUPPORTED_EXTS
from docmeta import doc_meta
from extract import extract_text
from rag import chat
from store import Store

log = logging.getLogger("ingest")

SUMMARY_PROMPT = """Summarize this document in Thai: 2-3 sentences on what it is and who or what it is for, then a line "คำค้น:" with 8 Thai keywords people would use to ask for it (include the document type, e.g. ใบเสร็จ, ประกาศ, แบบฟอร์ม). Plain text only."""


def summarize(text: str) -> str:
    return chat([{"role": "system", "content": SUMMARY_PROMPT}, {"role": "user", "content": text[:SUMMARY_CHARS]}])


def build_index(content_dir: Path, store: Store, summarize=None) -> dict:
    """`summarize` (text -> Thai summary) is called only for new or changed downloadable files; None skips it."""
    items, skipped, keep = [], [], set()
    known = store.signatures()
    for path in sorted(p for p in content_dir.rglob("*") if p.is_file()):
        rel = path.relative_to(content_dir).as_posix()
        if path.name.startswith(".") or path.suffix.lower() not in SUPPORTED_EXTS:
            skipped.append(f"{rel}: unsupported")
            continue
        meta = doc_meta(path, content_dir)
        if meta.sig and known.get(meta.doc_id) == meta.sig:  # unchanged since last run: skip extract and embed
            keep.add(meta.doc_id)
            continue
        try:
            text = extract_text(path)
            chunks = chunk_text(text, CHUNK_SIZE, CHUNK_OVERLAP)
        except Exception as e:  # corrupt file must not stop the whole run
            skipped.append(f"{rel}: error {e}")
            continue
        if not chunks:
            skipped.append(f"{rel}: no extractable text (scanned?)")
            continue
        if summarize and meta.downloadable:
            try:
                meta = dataclasses.replace(meta, summary=summarize(text))
            except Exception as e:  # the file is still findable by name
                log.warning("summary failed for %s: %s", rel, e)
        items.append((meta, chunks))
    store.update(items, keep)
    for s in skipped:
        log.warning("skipped %s", s)
    return {"indexed": len(items) + len(keep), "changed": len(items), "skipped": skipped}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(build_index(CONTENT_DIR, Store(), summarize))
