from pathlib import Path

from app.rag.docmeta import doc_meta

root = Path("/data/content")


def test_category_from_first_subfolder():
    assert doc_meta(root / "policy" / "x.pdf", root, mtime="2026-01-01").category == "policy"


def test_top_level_is_general():
    assert doc_meta(root / "n.txt", root, mtime="2026-01-01").category == "general"


def test_shareable_ignored_for_category_but_marks_downloadable():
    m = doc_meta(root / "forms" / "shareable" / "f.docx", root, mtime="2026-01-01")
    assert (m.category, m.downloadable) == ("forms", True)


def test_top_level_shareable_is_general_and_downloadable():
    m = doc_meta(root / "shareable" / "f.docx", root, mtime="2026-01-01")
    assert (m.category, m.downloadable) == ("general", True)


def test_not_downloadable_by_default():
    assert doc_meta(root / "policy" / "x.pdf", root, mtime="2026-01-01").downloadable is False


def test_doc_id_stable_independent_of_root_and_distinct_per_path():
    a = doc_meta(root / "policy" / "x.pdf", root, mtime="2026-01-01")
    b = doc_meta(Path("/other") / "policy" / "x.pdf", Path("/other"), mtime="2026-01-01")
    c = doc_meta(root / "policy" / "y.pdf", root, mtime="2026-01-01")
    assert a.doc_id == b.doc_id != c.doc_id
    assert len(a.doc_id) == 16
