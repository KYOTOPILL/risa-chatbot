import pytest
from fastapi.testclient import TestClient

import admin
import server
import state
from store import Store
from test_store_ingest import fake_embed


@pytest.fixture
def env(tmp_path, monkeypatch):
    content = tmp_path / "content"
    content.mkdir()
    store = Store(tmp_path / "index", embed_fn=fake_embed)
    monkeypatch.setattr(admin, "CONTENT_DIR", content)
    monkeypatch.setattr(state, "get_store", lambda: store)
    server.app.dependency_overrides[admin.require_local] = lambda: None
    yield content, store, TestClient(server.app)
    server.app.dependency_overrides.clear()


def up(client, name="a.txt", data=b"annual leave ten days", category="policy", downloadable=False):
    return client.post(
        "/api/admin/upload",
        files=[("files", (name, data, "text/plain"))],
        data={"category": category, "downloadable": str(downloadable).lower()},
    )


def test_non_local_client_is_blocked():
    server.app.dependency_overrides.clear()
    c = TestClient(server.app)  # client host is "testclient", not loopback
    for r in (c.get("/admin"), c.get("/api/admin/files"), c.post("/api/admin/reindex")):
        assert r.status_code == 403


def test_upload_lands_in_category_folder_and_lists(env):
    content, _, c = env
    assert up(c).status_code == 200
    assert (content / "policy" / "a.txt").read_text() == "annual leave ten days"
    row = c.get("/api/admin/files").json()[0]
    assert (row["path"], row["category"], row["downloadable"]) == ("policy/a.txt", "policy", False)


def test_upload_downloadable_goes_to_shareable(env):
    content, _, c = env
    up(c, "f.txt", category="forms", downloadable=True)
    assert (content / "forms" / "shareable" / "f.txt").exists()
    assert c.get("/api/admin/files").json()[0]["downloadable"] is True


def test_upload_without_category_is_top_level(env):
    content, _, c = env
    up(c, category="")
    assert (content / "a.txt").exists()


@pytest.mark.parametrize("category", ["../x", "a/b", "..", ".hidden", "shareable", "a\\b"])
def test_bad_category_rejected(env, category):
    content, _, c = env
    assert up(c, category=category).status_code == 400
    assert not any(content.rglob("*.txt"))


def test_filename_is_reduced_to_basename(env, tmp_path):
    content, _, c = env
    up(c, name="../../evil.txt")
    assert (content / "policy" / "evil.txt").exists() and not (tmp_path / "evil.txt").exists()


def test_unsupported_and_hidden_names_rejected(env):
    _, _, c = env
    assert up(c, name="run.exe").status_code == 400
    assert up(c, name=".env.txt").status_code == 400


def test_oversized_upload_rejected(env, monkeypatch):
    monkeypatch.setattr(admin, "MAX_BYTES", 10)
    _, _, c = env
    assert up(c, data=b"x" * 11).status_code == 413


def test_delete_removes_file_and_empty_folder(env):
    content, _, c = env
    up(c)
    assert c.post("/api/admin/delete", json={"path": "policy/a.txt"}).status_code == 200
    assert not (content / "policy").exists() and content.exists()


@pytest.mark.parametrize("path", ["../outside.txt", "/etc/passwd", "policy", "nope.txt"])
def test_delete_rejects_traversal_dirs_and_missing(env, tmp_path, path):
    content, _, c = env
    (tmp_path / "outside.txt").write_text("keep")
    (content / "policy").mkdir()
    assert c.post("/api/admin/delete", json={"path": path}).status_code in (400, 404)
    assert (tmp_path / "outside.txt").exists() and (content / "policy").exists()


def test_reindex_adds_and_removes_files_from_search(env):
    _, store, c = env
    up(c)
    r = c.post("/api/admin/reindex")
    assert r.status_code == 200 and r.json()["indexed"] == 1
    assert store.query("annual leave", k=1)
    c.post("/api/admin/delete", json={"path": "policy/a.txt"})
    c.post("/api/admin/reindex")
    assert store.query("annual leave", k=1) == []


def test_admin_page_served(env):
    _, _, c = env
    r = c.get("/admin")
    assert r.status_code == 200 and "จัดการเอกสาร" in r.text
