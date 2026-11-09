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


def test_only_added_people_can_log_in_and_the_first_login_sets_the_name(tmp_path):
    tk = Tracker(tmp_path / "t.db")
    assert tk.login_user("stranger@cmu.ac.th", "Stranger") is None and tk.get_user("stranger@cmu.ac.th") is None  # never creates anyone
    out = tk.add_users(["Somsri.K@cmu.ac.th", " somsri.k@cmu.ac.th ", "r1", "not an email", "x@y"], "researcher")
    assert out == {"added": ["somsri.k@cmu.ac.th"], "existing": [], "invalid": ["somsri.k@cmu.ac.th", "r1", "not an email", "x@y"]}  # the repeated line is skipped
    assert tk.get_user("somsri.k@cmu.ac.th")["name"] == "somsri.k"  # a placeholder until the first login
    assert tk.login_user("SOMSRI.K@cmu.ac.th", "Somsri Kaew")["name"] == "Somsri Kaew"
    tk.set_profile("somsri.k@cmu.ac.th", "Somsri (edited)", "", "", "")
    tk.set_role("somsri.k@cmu.ac.th", "staff")
    assert tk.login_user("somsri.k@cmu.ac.th", "Somsri Kaew") == {"id": "somsri.k@cmu.ac.th", "name": "Somsri (edited)", "role": "staff"}  # later logins keep edits and role
    tk.set_active("somsri.k@cmu.ac.th", False)
    assert tk.login_user("somsri.k@cmu.ac.th", "Somsri") is None and tk.role_of("somsri.k@cmu.ac.th") is None
    assert tk.get_user("somsri.k@cmu.ac.th")["name"] == "Somsri (edited)"  # old requests still show the name
    tk.set_active("somsri.k@cmu.ac.th", True)
    assert tk.role_of("somsri.k@cmu.ac.th") == "staff"


def test_role_must_be_known(tmp_path):
    tk = Tracker(tmp_path / "t.db")
    for bad in (lambda: tk.set_role("r1", "admin"), lambda: tk.add_users(["x@cmu.ac.th"], "admin")):
        try:
            bad()
            assert False, "accepted an unknown role"
        except ValueError:
            pass


def test_api_lists_and_checks_users_from_the_table(tmp_path, monkeypatch):
    tk = Tracker(tmp_path / "t.db")
    monkeypatch.setattr(state, "get_tracker", lambda: tk)
    tk.add_users(["new@cmu.ac.th"], "researcher")
    c = TestClient(server.app)
    assert c.post("/api/track/login", json=CREDS["s1"]).status_code == 200
    assert {"id": "new@cmu.ac.th", "name": "new", "role": "researcher", "active": True} in c.get("/api/track/users").json()
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


def test_listed_staff_emails_are_seeded_as_the_first_staff(tmp_path, monkeypatch):
    from app.features import tracker
    monkeypatch.setattr(tracker, "STAFF_EMAILS", {"boss@cmu.ac.th"})
    tk = Tracker(tmp_path / "t.db")
    assert tk.login_user("Boss@cmu.ac.th", "Boss")["role"] == "staff"  # can log in with no one adding them
    tk.set_role("boss@cmu.ac.th", "researcher")
    assert Tracker(tmp_path / "t.db").role_of("boss@cmu.ac.th") == "researcher"  # a restart never undoes a staff decision


def test_staff_change_roles_but_not_their_own_or_a_busy_staff_members(tmp_path, monkeypatch):
    tk, c = _client(tmp_path, monkeypatch, "s1")
    v = tk.create_type("T", [{"title": "S", "documents": []}], "t.pdf")
    tk.approve(v)
    tk.create_submission("Job", v, ["r1"], "s2")  # s2 is in charge of an unfinished request
    assert c.put("/api/track/users/s1/role", json={"role": "researcher"}).status_code == 400  # not yourself
    assert c.put("/api/track/users/s2/role", json={"role": "researcher"}).status_code == 409  # hand the request over first
    assert c.put("/api/track/users/s2/role", json={"role": "admin"}).status_code == 400
    assert c.put("/api/track/users/nobody/role", json={"role": "staff"}).status_code == 404
    r = c.put("/api/track/users/r1/role", json={"role": "staff"})
    assert r.status_code == 200 and {"id": "r1", "name": "Somchai", "role": "staff", "active": True} in r.json() and tk.role_of("r1") == "staff"
    r2 = TestClient(server.app); r2.post("/api/track/login", json=CREDS["r2"])
    assert r2.put("/api/track/users/r2/role", json={"role": "staff"}).status_code == 403  # researchers cannot promote themselves


def test_access_list_pages_searches_and_counts(tmp_path, monkeypatch):
    tk, c = _client(tmp_path, monkeypatch, "s1")
    tk.add_users([f"nida{i}@cmu.ac.th" for i in range(60)] + ["100%_sure@cmu.ac.th"], "researcher")
    tk.set_active("nida3@cmu.ac.th", False)
    p = c.get("/api/track/users/page?limit=50").json()
    assert len(p["items"]) == 50 and p["total"] == 64 and p["counts"] == {"": 64, "staff": 2, "researcher": 62, "disabled": 1}  # r1 r2 s1 s2 + 60 + 1 - 1 disabled
    assert [u["role"] for u in p["items"][:2]] == ["staff", "staff"]  # staff come first
    assert len(c.get("/api/track/users/page?limit=50&offset=50").json()["items"]) == 14
    assert [u["id"] for u in c.get("/api/track/users/page?q=%25_s").json()["items"]] == ["100%_sure@cmu.ac.th"]  # % and _ are plain letters
    assert [u["id"] for u in c.get("/api/track/users/page?view=disabled").json()["items"]] == ["nida3@cmu.ac.th"]
    assert c.get("/api/track/users/page?view=nope").status_code == 400
    r = TestClient(server.app); r.post("/api/track/login", json=CREDS["r1"])
    assert r.get("/api/track/users/page").status_code == 403 and r.post("/api/track/users/add", json={"emails": "a@b.co"}).status_code == 403


def test_staff_add_people_and_turn_access_off(tmp_path, monkeypatch):
    tk, c = _client(tmp_path, monkeypatch, "s1")
    r = c.post("/api/track/users/add", json={"emails": "A@cmu.ac.th\nb@cmu.ac.th\nbad", "role": "staff"}).json()
    assert r == {"added": ["a@cmu.ac.th", "b@cmu.ac.th"], "existing": [], "invalid": ["bad"]} and tk.role_of("a@cmu.ac.th") == "staff"
    assert c.post("/api/track/users/add", json={"emails": "  "}).status_code == 400
    assert c.post("/api/track/users/add", json={"emails": "a@b.co", "role": "admin"}).status_code == 400
    tk.link_line("U1", "r1")
    assert c.put("/api/track/users/r1/active", json={"active": False}).status_code == 200
    assert not tk.has_line("r1") and tk.role_of("r1") is None  # the LINE link is cut, they can no longer be picked
    gone = TestClient(server.app)
    assert gone.post("/api/track/login", json=CREDS["r1"]).status_code == 403  # no session for a disabled person
    assert {"id": "r1", "name": "Somchai", "role": "researcher", "active": False} in c.get("/api/track/users").json()
    assert c.put("/api/track/users/r1/active", json={"active": True}).status_code == 200 and gone.post("/api/track/login", json=CREDS["r1"]).status_code == 200
    assert gone.put("/api/track/users/s1/active", json={"active": False}).status_code == 403
    assert c.put("/api/track/users/s1/active", json={"active": False}).status_code == 400  # not yourself
    assert c.put("/api/track/users/nobody/active", json={"active": False}).status_code == 404


def test_a_session_ends_when_the_person_is_disabled_and_a_busy_staff_member_cannot_be(tmp_path, monkeypatch):
    tk, c = _client(tmp_path, monkeypatch, "s1")
    r1 = TestClient(server.app); r1.post("/api/track/login", json=CREDS["r1"])
    assert r1.get("/api/track/me").status_code == 200
    tk.set_active("r1", False)
    assert r1.get("/api/track/me").status_code == 401  # the old cookie stops working at once
    v = tk.create_type("T", [{"title": "S", "documents": []}], "t.pdf")
    tk.approve(v)
    tk.create_submission("Job", v, ["r2"], "s2")
    assert c.put("/api/track/users/s2/active", json={"active": False}).status_code == 409


def test_dev_login_is_one_listed_email_with_a_password_from_the_environment(tmp_path, monkeypatch):
    from app.core import auth
    tk, _ = _client(tmp_path, monkeypatch, "s1")
    tk.add_users(["me@cmu.ac.th"], "staff")
    def login(user, pw):
        return TestClient(server.app).post("/api/track/login", json={"username": user, "password": pw})
    assert login("me@cmu.ac.th", "secret").status_code == 401  # off until RISA_DEV_LOGIN is set
    monkeypatch.setattr(auth, "DEV_LOGIN", ("me@cmu.ac.th", "se:cret"))
    ok = login(" ME@cmu.ac.th ", "se:cret")
    assert ok.status_code == 200 and ok.json()["role"] == "staff"
    assert login("me@cmu.ac.th", "wrong").status_code == 401
    tk.set_active("me@cmu.ac.th", False)
    assert login("me@cmu.ac.th", "se:cret").status_code == 403  # the access list still decides
    monkeypatch.setattr(auth, "DEV_LOGIN", ("stranger@cmu.ac.th", "pw"))
    assert login("stranger@cmu.ac.th", "pw").status_code == 403  # a password alone never creates someone


def test_a_session_works_for_an_email_id_with_dots(tmp_path, monkeypatch):
    tk, _ = _client(tmp_path, monkeypatch, "s1")
    tk.add_users(["pawarit_di@cmu.ac.th"], "staff")
    from app.core import auth
    monkeypatch.setattr(auth, "DEV_LOGIN", ("pawarit_di@cmu.ac.th", "pw"))
    c = TestClient(server.app)
    assert c.post("/api/track/login", json={"username": "pawarit_di@cmu.ac.th", "password": "pw"}).status_code == 200
    assert c.get("/api/track/me").json()["id"] == "pawarit_di@cmu.ac.th"  # the cookie id has dots; it used to be cut at the first one
    good = c.cookies.get("uid")
    c.cookies.clear()
    c.cookies.set("uid", "x" + good)  # a tampered id still fails
    assert c.get("/api/track/me").status_code == 401


def test_pasted_people_may_carry_a_name_and_the_preview_says_what_will_happen(tmp_path, monkeypatch):
    tk, c = _client(tmp_path, monkeypatch, "s1")
    tk.add_users(["old@cmu.ac.th", "gone@cmu.ac.th"], "researcher")
    tk.set_active("gone@cmu.ac.th", False)
    text = ("new1@cmu.ac.th\tSomchai Suksai\n"            # two columns pasted from Excel
            '"new2@cmu.ac.th", "Nida J."\n'                 # csv with quotes
            "NEW3@mail.cmu.ac.th Preecha\n"                 # a subdomain is still cmu
            "someone@gmail.com\n"                           # allowed, but flagged
            "old@cmu.ac.th\ngone@cmu.ac.th\n"
            "a@cmu.ac.th b@cmu.ac.th\n"                     # two emails on one line
            "nope\nnew1@cmu.ac.th\n\n")                   # not an email; a repeat; a blank line
    p = c.post("/api/track/users/preview", json={"emails": text}).json()
    assert [r["status"] for r in p["rows"]] == ["new", "new", "new", "new", "exists", "disabled", "invalid", "invalid", "invalid"]
    assert [r["name"] for r in p["rows"][:3]] == ["Somchai Suksai", "Nida J.", "Preecha"]
    assert p["counts"] == {"new": 4, "exists": 1, "disabled": 1, "invalid": 3} and p["warn"] == 1 and p["rows"][3]["warn"] is True
    assert c.get("/api/track/users/page?q=new").json()["total"] == 0  # a preview saves nothing
    out = c.post("/api/track/users/add", json={"emails": text}).json()
    assert out["added"] == ["new1@cmu.ac.th", "new2@cmu.ac.th", "new3@mail.cmu.ac.th", "someone@gmail.com"] and len(out["invalid"]) == 3 and out["existing"] == ["old@cmu.ac.th", "gone@cmu.ac.th"]
    assert tk.get_user("new1@cmu.ac.th")["name"] == "Somchai Suksai" and tk.get_user("someone@gmail.com")["name"] == "someone"  # no name given: the part before @
    assert tk.login_user("new1@cmu.ac.th", "Somchai S. (CMU)")["name"] == "Somchai S. (CMU)"  # the CMU name wins at first login
    assert c.post("/api/track/users/preview", json={"emails": "   "}).status_code == 400
    r = TestClient(server.app); r.post("/api/track/login", json=CREDS["r1"])
    assert r.post("/api/track/users/preview", json={"emails": "a@cmu.ac.th"}).status_code == 403
