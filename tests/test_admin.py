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
    server.app.dependency_overrides[admin.require_admin] = lambda: None
    yield content, store, TestClient(server.app)
    server.app.dependency_overrides.clear()


def up(client, name="a.txt", data=b"annual leave ten days", category="policy", downloadable=False):
    return client.post(
        "/api/admin/upload",
        files=[("files", (name, data, "text/plain"))],
        data={"category": category, "downloadable": str(downloadable).lower()},
    )


def test_non_local_client_is_blocked_without_password(monkeypatch):
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    server.app.dependency_overrides.clear()
    c = TestClient(server.app)  # client host is "testclient", not loopback
    for r in (c.get("/admin"), c.get("/api/admin/files"), c.post("/api/admin/reindex")):
        assert r.status_code == 403


def test_password_required_when_set(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "s3cret")
    server.app.dependency_overrides.clear()
    c = TestClient(server.app)
    for r in (c.get("/api/admin/files"), c.get("/api/admin/files", auth=("admin", "wrong")),
              c.get("/api/admin/files", auth=("root", "s3cret")), c.post("/api/admin/reindex")):
        assert r.status_code == 401 and r.headers["www-authenticate"].startswith("Basic")
    assert c.get("/api/admin/files", auth=("admin", "s3cret")).status_code == 200
    assert c.get("/admin", auth=("admin", "s3cret")).status_code == 200


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


def test_reindex_clears_answer_cache(env):
    _, _, c = env
    state.cache["ลากี่วัน"] = object()
    c.post("/api/admin/reindex")
    assert state.cache == {}


def test_file_list_includes_the_thai_summary_of_every_file(env):
    from ingest import build_index
    content, store, c = env
    up(c, "form.txt", b"annual leave form " * 10, category="forms", downloadable=True)
    up(c, "policy.txt", b"annual leave ten days " * 10)
    build_index(content, store, summarize=lambda text: "แบบฟอร์มลา")
    rows = {r["path"].split("/")[-1]: r for r in c.get("/api/admin/files").json()}
    assert rows["form.txt"]["summary"] == rows["policy.txt"]["summary"] == "แบบฟอร์มลา"  # every file has one, downloadable or not


def test_summary_still_listed_after_downloadable_is_switched_off(env):
    from ingest import build_index
    content, store, c = env
    up(c, "form.txt", b"annual leave form " * 10, category="forms", downloadable=True)
    build_index(content, store, summarize=lambda text: "แบบฟอร์มลา")
    path = c.get("/api/admin/files").json()[0]["path"]
    c.post("/api/admin/move", json={"path": path, "downloadable": False})
    build_index(content, store, summarize=lambda text: "ไม่ควรเรียก")
    row = c.get("/api/admin/files").json()[0]
    assert row["downloadable"] is False and row["summary"] == "แบบฟอร์มลา"


def test_file_that_was_never_downloadable_still_gets_a_description(env):
    from ingest import build_index
    content, store, c = env
    up(c, "internal.txt", b"internal policy text " * 10)
    build_index(content, store, summarize=lambda text: "นโยบายภายใน")
    assert c.get("/api/admin/files").json()[0]["summary"] == "นโยบายภายใน"


def test_admin_page_served(env):
    _, _, c = env
    r = c.get("/admin")
    assert r.status_code == 200 and "จัดการเอกสาร" in r.text


def test_mkdir_and_folders_listing(env):
    content, _, c = env
    assert c.post("/api/admin/mkdir", json={"folder": " forms "}).json() == {"folder": "forms"}
    up(c, category="policy", downloadable=True)  # shareable/ must not show up as a folder
    assert c.get("/api/admin/folders").json() == ["forms", "policy"]
    for bad in ("", "a/b", "shareable", ".x"):
        assert c.post("/api/admin/mkdir", json={"folder": bad}).status_code == 400


def test_move_renames_moves_and_toggles_downloadable(env):
    content, _, c = env
    up(c)
    r = c.post("/api/admin/move", json={"path": "policy/a.txt", "name": "b.txt"})
    assert r.json() == {"path": "policy/b.txt"} and (content / "policy" / "b.txt").exists()
    r = c.post("/api/admin/move", json={"path": "policy/b.txt", "downloadable": True})
    assert r.json() == {"path": "policy/shareable/b.txt"} and not (content / "policy" / "b.txt").exists()
    r = c.post("/api/admin/move", json={"path": "policy/shareable/b.txt", "folder": "forms"})
    assert r.json() == {"path": "forms/shareable/b.txt"}  # keeps downloadable
    assert not (content / "policy").exists()  # emptied folder is pruned
    r = c.post("/api/admin/move", json={"path": "forms/shareable/b.txt", "folder": "", "downloadable": False})
    assert r.json() == {"path": "b.txt"} and (content / "b.txt").exists()


def test_move_conflicts_and_bad_input_rejected(env):
    content, _, c = env
    up(c, "a.txt"); up(c, "b.txt")
    assert c.post("/api/admin/move", json={"path": "policy/a.txt", "name": "b.txt"}).status_code == 409
    assert c.post("/api/admin/move", json={"path": "policy/a.txt", "name": "a.exe"}).status_code == 400
    assert c.post("/api/admin/move", json={"path": "policy/a.txt", "folder": "../x"}).status_code == 400
    assert c.post("/api/admin/move", json={"path": "../a.txt"}).status_code in (400, 404)
    assert c.post("/api/admin/move", json={"path": "policy/nope.txt"}).status_code == 404
    assert c.post("/api/admin/move", json={"path": "policy/a.txt"}).status_code == 200  # no-op
    assert (content / "policy" / "a.txt").exists() and (content / "policy" / "b.txt").exists()


def test_replace_keeps_path_and_requires_same_type(env):
    content, _, c = env
    up(c, downloadable=True)
    r = c.post("/api/admin/replace", data={"path": "policy/shareable/a.txt"},
               files={"file": ("whatever.txt", b"new text", "text/plain")})
    assert r.status_code == 200 and (content / "policy" / "shareable" / "a.txt").read_text() == "new text"
    r = c.post("/api/admin/replace", data={"path": "policy/shareable/a.txt"},
               files={"file": ("x.md", b"nope", "text/plain")})
    assert r.status_code == 400 and (content / "policy" / "shareable" / "a.txt").read_text() == "new text"
    r = c.post("/api/admin/replace", data={"path": "policy/missing.txt"},
               files={"file": ("a.txt", b"x", "text/plain")})
    assert r.status_code == 404


def test_rename_folder_and_conflicts(env):
    content, _, c = env
    up(c, category="policy"); up(c, category="forms")
    assert c.post("/api/admin/rename-folder", json={"folder": "policy", "name": "rules"}).json() == {"folder": "rules"}
    assert (content / "rules" / "a.txt").exists() and not (content / "policy").exists()
    assert c.post("/api/admin/rename-folder", json={"folder": "rules", "name": "forms"}).status_code == 409
    for bad in ("", "a/b", "shareable", ".x"):
        assert c.post("/api/admin/rename-folder", json={"folder": "rules", "name": bad}).status_code == 400
    assert c.post("/api/admin/rename-folder", json={"folder": "nope", "name": "z"}).status_code == 404


def test_delete_folder_removes_contents_only_that_folder(env):
    content, _, c = env
    up(c, category="policy", downloadable=True); up(c, category="forms")
    assert c.post("/api/admin/delete-folder", json={"folder": "policy"}).status_code == 200
    assert not (content / "policy").exists() and (content / "forms" / "a.txt").exists()
    for bad in ("", "..", "a/b", "nope"):
        assert c.post("/api/admin/delete-folder", json={"folder": bad}).status_code in (400, 404)
    assert content.exists() and (content / "forms" / "a.txt").exists()


def test_cross_site_post_and_rebinding_are_blocked(monkeypatch):
    server.app.dependency_overrides.clear()
    monkeypatch.setenv("ADMIN_PASSWORD", "s3cret")
    c = TestClient(server.app)
    r = c.post("/api/admin/reindex", auth=("admin", "s3cret"), headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and "cross-site" in r.text
    r = c.get("/api/admin/folders", auth=("admin", "s3cret"), headers={"Origin": "https://evil.example"})
    assert r.status_code == 200  # reads are not Origin-checked; browsers block cross-site reads
    monkeypatch.delenv("ADMIN_PASSWORD")
    local = TestClient(server.app, client=("127.0.0.1", 5000), base_url="http://localhost")
    assert local.get("/api/admin/folders").status_code == 200
    assert local.get("/api/admin/folders", headers={"Host": "evil.example"}).status_code == 403
