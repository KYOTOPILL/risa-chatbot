import math
from pathlib import Path

import pymupdf

from ingest import build_index
from store import Store


def fake_embed(texts):
    out = []
    for t in texts:
        v = [0.0] * 64
        for ch in t.lower():
            v[ord(ch) % 64] += 1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        out.append([x / n for x in v])
    return out


def make(tmp_path):
    content = tmp_path / "content"
    (content / "policy").mkdir(parents=True)
    (content / "forms" / "shareable").mkdir(parents=True)
    (content / "policy" / "leave.txt").write_text("annual leave is ten days per year", encoding="utf-8")
    (content / "forms" / "shareable" / "expense.txt").write_text("expense claim form for receipts", encoding="utf-8")
    return content, Store(tmp_path / "index", embed_fn=fake_embed)


def test_ingest_indexes_supported_and_skips_unsupported(tmp_path):
    content, store = make(tmp_path)
    (content / "data.xlsx").write_bytes(b"x")
    (content / ".DS_Store").write_bytes(b"x")
    result = build_index(content, store)
    assert result["indexed"] == 2
    assert any("data.xlsx" in s for s in result["skipped"])
    assert any(".DS_Store" in s for s in result["skipped"])


def test_empty_extraction_is_skipped_with_warning(tmp_path):
    content, store = make(tmp_path)
    doc = pymupdf.open()
    page = doc.new_page()
    page.draw_rect(pymupdf.Rect(50, 50, 200, 200), fill=(0, 0, 0))
    doc.save(content / "policy" / "scan.pdf")
    result = build_index(content, store)
    assert result["indexed"] == 2
    assert any("scan.pdf" in s for s in result["skipped"])
    assert all("scan.pdf" not in h.rel_path for h in store.query("anything", k=10))


def test_reingest_removes_deleted_file_chunks(tmp_path):
    content, store = make(tmp_path)
    build_index(content, store)
    (content / "policy" / "leave.txt").unlink()
    build_index(content, store)
    assert all("leave.txt" not in h.rel_path for h in store.query("annual leave", k=10))


def test_query_category_filter(tmp_path):
    content, store = make(tmp_path)
    build_index(content, store)
    hits = store.query("leave expense", k=10, category="forms")
    assert hits and all(h.category == "forms" for h in hits)


def test_metadata_roundtrip_and_doc_path(tmp_path):
    content, store = make(tmp_path)
    build_index(content, store)
    h = store.query("expense claim", k=1)[0]
    assert (h.category, h.downloadable) == ("forms", True)
    assert len(h.mtime) == 10 and h.text and 0 <= h.distance <= 2
    assert store.doc_path(h.doc_id) == "forms/shareable/expense.txt"
    assert store.doc_path("nope") is None
