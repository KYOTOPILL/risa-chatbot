"""The users table: who exists, their name and role. Logins (mock now, CMU later) only prove identity."""
from fastapi.testclient import TestClient

from app.api import server
from app.core import state
from app.features.tracker import Tracker
from creds import CREDS


def test_demo_users_are_seeded_once_and_roles_survive_a_restart(tmp_path):
    tk = Tracker(tmp_path / "t.db")
    assert {u["id"]: u["role"] for u in tk.list_users()} == {"r1": "researcher", "r2": "researcher", "s1": "staff", "s2": "staff"}
    tk.set_role("r1", "staff")
    assert Tracker(tmp_path / "t.db").get_user("r1")["role"] == "staff"  # seeding never overwrites


def test_upsert_adds_a_first_login_and_never_overwrites_a_known_user(tmp_path):
    tk = Tracker(tmp_path / "t.db")
    tk.upsert_user("somsri.k@cmu.ac.th", "Somsri K")
    assert tk.get_user("somsri.k@cmu.ac.th") == {"id": "somsri.k@cmu.ac.th", "name": "Somsri K", "role": "researcher"}
    tk.set_role("somsri.k@cmu.ac.th", "staff")
    tk.set_profile("somsri.k@cmu.ac.th", "Somsri (edited)", "", "", "")
    tk.upsert_user("somsri.k@cmu.ac.th", "Somsri Kaew", role="researcher")  # a later login keeps the edited name and the role
    assert tk.get_user("somsri.k@cmu.ac.th") == {"id": "somsri.k@cmu.ac.th", "name": "Somsri (edited)", "role": "staff"}
    assert tk.get_user("nobody") is None


def test_role_must_be_known(tmp_path):
    tk = Tracker(tmp_path / "t.db")
    for bad in (lambda: tk.set_role("r1", "admin"), lambda: tk.upsert_user("x@cmu.ac.th", "X", role="admin")):
        try:
            bad()
            assert False, "accepted an unknown role"
        except ValueError:
            pass


def test_api_lists_and_checks_users_from_the_table(tmp_path, monkeypatch):
    tk = Tracker(tmp_path / "t.db")
    monkeypatch.setattr(state, "get_tracker", lambda: tk)
    tk.upsert_user("new@cmu.ac.th", "New Person")
    c = TestClient(server.app)
    assert c.post("/api/track/login", json=CREDS["s1"]).status_code == 200
    assert {"id": "new@cmu.ac.th", "name": "New Person", "role": "researcher"} in c.get("/api/track/users").json()
    tid = tk.get_version(tk.create_type("T", [{"title": "S", "documents": []}], "t.pdf"))["type_id"]
    assert c.put(f"/api/track/types/{tid}/audience", json={"user_ids": ["new@cmu.ac.th"]}).status_code == 200
    tk.set_role("s1", "researcher")  # a role change takes effect on the next request, no new login needed
    assert c.get("/api/track/users").status_code == 200 and c.put(f"/api/track/types/{tid}/audience", json={"user_ids": None}).status_code == 403


def test_profile_is_validated_and_old_databases_gain_the_columns(tmp_path):
    import sqlite3
    path = tmp_path / "old.db"
    db = sqlite3.connect(path)  # a database made before profiles: users without the new columns
    db.execute("CREATE TABLE users (id TEXT PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
    db.execute("INSERT INTO users (id, name, role) VALUES ('r1', 'Old', 'researcher')")
    db.commit(); db.close()
    tk = Tracker(path)
    assert tk.get_profile("r1") == {"id": "r1", "name": "Old", "role": "researcher", "phone": "", "faculty": "", "avatar_color": "", "photo": False}
    tk.set_profile("r1", " Somchai ", "081-234 5678", "Science", "#2563eb")
    assert tk.get_profile("r1")["name"] == "Somchai" and tk.get_profile("r1")["avatar_color"] == "#2563eb"
    for bad in (("", "", "", ""), ("x" * 81, "", "", ""), ("A", "call me", "", ""), ("A", "", "f" * 101, ""), ("A", "", "", "#ff0000")):
        try:
            tk.set_profile("r1", *bad)
            assert False, f"accepted {bad}"
        except ValueError:
            pass
    try:
        tk.set_profile("nobody", "A", "", "", "")
        assert False
    except KeyError:
        pass


def _client(tmp_path, monkeypatch, who="r1"):
    tk = Tracker(tmp_path / "t.db")
    monkeypatch.setattr(state, "get_tracker", lambda: tk)
    c = TestClient(server.app)
    assert c.post("/api/track/login", json=CREDS[who]).status_code == 200
    return tk, c


def test_profile_api_edits_only_my_own_details(tmp_path, monkeypatch):
    tk, c = _client(tmp_path, monkeypatch)
    assert TestClient(server.app).get("/api/track/profile").status_code == 401
    r = c.put("/api/track/profile", json={"name": "Somchai P", "phone": "0812345678", "faculty": "Science", "avatar_color": "#7c3aed", "role": "staff", "id": "s1"})
    assert r.status_code == 200 and r.json()["name"] == "Somchai P" and r.json()["role"] == "researcher" and r.json()["id"] == "r1"
    assert c.get("/api/track/me").json() == {"id": "r1", "name": "Somchai P", "role": "researcher", "avatar_color": "#7c3aed", "photo": False}
    assert tk.get_user("s1")["name"] == "Malee"  # nobody else changed
    assert c.put("/api/track/profile", json={"name": ""}).status_code == 400
    assert c.put("/api/track/profile", json={"name": "A", "avatar_color": "red"}).status_code == 400


def test_avatar_accepts_real_images_only_and_can_be_removed(tmp_path, monkeypatch):
    tk, c = _client(tmp_path, monkeypatch)
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 50
    assert c.get("/api/track/profile/avatar").status_code == 404
    assert c.put("/api/track/profile/avatar", files={"file": ("a.png", b"<script>alert(1)</script>", "image/png")}).status_code == 400
    assert c.put("/api/track/profile/avatar", files={"file": ("a.png", png + b"0" * 300_000, "image/png")}).status_code == 400  # too big
    assert c.put("/api/track/profile/avatar", files={"file": ("a.png", png, "image/png")}).status_code == 200
    got = c.get("/api/track/profile/avatar")
    assert got.content == png and got.headers["content-type"] == "image/png" and c.get("/api/track/me").json()["photo"] is True
    assert c.delete("/api/track/profile/avatar").status_code == 200 and c.get("/api/track/profile/avatar").status_code == 404


def test_profile_page_is_served_and_unlink_cuts_every_line_link(tmp_path, monkeypatch):
    tk, c = _client(tmp_path, monkeypatch)
    assert c.get("/profile").status_code == 200 and b"RiSA" in c.get("/profile").content
    tk.link_line("U1", "r1"); tk.link_line("U2", "r2")
    assert c.post("/api/line/unlink").status_code == 200
    assert not tk.has_line("r1") and tk.has_line("r2")
    s = TestClient(server.app); s.post("/api/track/login", json=CREDS["s1"])
    assert s.post("/api/line/unlink").status_code == 403  # staff have no LINE link
