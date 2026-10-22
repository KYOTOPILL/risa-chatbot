from pathlib import Path

from downloads import resolve_download
from ingest import build_index
from store import Store
from test_store_ingest import fake_embed


def setup(tmp_path):
    content = tmp_path / "content"
    (content / "policy").mkdir(parents=True)
    (content / "forms" / "shareable").mkdir(parents=True)
    (content / "policy" / "salary.txt").write_text("salary bands", encoding="utf-8")
    (content / "forms" / "shareable" / "expense.txt").write_text("expense form", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    (content / "forms" / "shareable" / "link.txt").symlink_to(outside)
    store = Store(tmp_path / "index", embed_fn=fake_embed)
    build_index(content, store)
    ids = {h.rel_path: h.doc_id for h in store.query("salary expense secret", k=10)}
    return content, store, ids


def test_valid_shareable_id_resolves(tmp_path):
    content, store, ids = setup(tmp_path)
    assert resolve_download(ids["forms/shareable/expense.txt"], store, content) == (content / "forms/shareable/expense.txt").resolve()


def test_non_shareable_id_returns_none(tmp_path):
    content, store, ids = setup(tmp_path)
    assert resolve_download(ids["policy/salary.txt"], store, content) is None


def test_unknown_id_returns_none(tmp_path):
    content, store, _ = setup(tmp_path)
    assert resolve_download("deadbeefdeadbeef", store, content) is None


def test_path_string_instead_of_id_returns_none(tmp_path):
    content, store, _ = setup(tmp_path)
    for bad in ["../../etc/passwd", "forms/shareable/expense.txt", "/etc/passwd", ""]:
        assert resolve_download(bad, store, content) is None


def test_symlink_escaping_content_dir_returns_none(tmp_path):
    content, store, ids = setup(tmp_path)
    assert resolve_download(ids["forms/shareable/link.txt"], store, content) is None
