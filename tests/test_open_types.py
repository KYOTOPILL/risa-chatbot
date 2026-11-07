import sqlite3

import pytest
from fastapi.testclient import TestClient

import server
import state
from creds import CREDS
from tracker import Tracker

STEPS = [{"title": "Submit", "documents": ["Form A", "Form B"], "page": 1, "unsure": True}, {"title": "Review", "documents": [], "page": 2, "unsure": False}]


@pytest.fixture
def env(tmp_path, monkeypatch):
    tk = Tracker(tmp_path / "t.db")
    monkeypatch.setattr(state, "get_tracker", lambda: tk)
    v = tk.create_type("Travel claim", STEPS, "t.pdf")
    tk.approve(v)
    return tk, tk.get_version(v)["type_id"]


def client(uid):
    c = TestClient(server.app)
    assert c.post("/api/track/login", json=CREDS[uid]).status_code == 200
    return c


def publish(c, tid, **body):
    return c.post(f"/api/track/types/{tid}/publish", json=body)


def test_old_database_gets_the_new_columns(tmp_path):
    db = sqlite3.connect(tmp_path / "old.db")
    db.executescript("CREATE TABLE types (id INTEGER PRIMARY KEY, name TEXT NOT NULL); INSERT INTO types (name) VALUES ('Old');")
    db.commit(); db.close()
    tk = Tracker(tmp_path / "old.db")
    assert tk.list_types() == []  # no crash, and the old row now has open = 0
    with sqlite3.connect(tmp_path / "old.db") as db:
        assert db.execute("SELECT open, owner_id FROM types").fetchone() == (0, "")


def test_nothing_is_open_until_staff_publish(env):
    _, tid = env
    assert client("r1").get("/api/track/open-types").json() == []
    assert publish(client("s1"), tid).status_code == 200
    got = client("r1").get("/api/track/open-types").json()
    assert [t["type_name"] for t in got] == ["Travel claim"] and got[0]["owner_name"] == "Malee"
    assert "page" not in str(got) and got[0]["steps"][0]["documents"] == ["Form A", "Form B"]


def test_publish_defaults_to_the_publisher_and_can_name_another_owner(env):
    _, tid = env
    publish(client("s2"), tid)
    assert client("r1").get("/api/track/open-types").json()[0]["owner_id"] == "s2"
    publish(client("s2"), tid, owner_id="s1")
    assert client("r1").get("/api/track/open-types").json()[0]["owner_id"] == "s1"


def test_publish_rules(env):
    tk, tid = env
    assert publish(client("r1"), tid).status_code == 403
    assert publish(TestClient(server.app), tid).status_code == 401
    assert publish(client("s1"), tid, owner_id="r1").status_code == 400  # a researcher cannot own a post
    assert publish(client("s1"), tid, owner_id="nobody").status_code == 400
    assert publish(client("s1"), 999).status_code == 404
    draft_only = tk.create_type("Draft only", STEPS, "d.pdf")
    assert publish(client("s1"), tk.get_version(draft_only)["type_id"]).status_code == 400  # no approved version yet


def test_close_hides_the_post_but_keeps_existing_requests(env):
    _, tid = env
    s1, r1 = client("s1"), client("r1")
    publish(s1, tid)
    sid = r1.post(f"/api/track/open-types/{tid}/start").json()["id"]
    assert s1.post(f"/api/track/types/{tid}/close").status_code == 200
    assert r1.get("/api/track/open-types").json() == []
    assert r1.post(f"/api/track/open-types/{tid}/start").status_code == 404
    assert r1.get(f"/api/track/submissions/{sid}").status_code == 200


def test_researcher_starts_their_own_request_owned_by_the_post_owner(env):
    _, tid = env
    publish(client("s2"), tid)
    r1, r2 = client("r1"), client("r2")
    a = r1.post(f"/api/track/open-types/{tid}/start").json()["id"]
    got = r1.get(f"/api/track/submissions/{a}").json()
    assert got["researcher_ids"] == ["r1"] and got["staff_id"] == "s2" and got["title"] == "Travel claim - Somchai" and got["current_step"] == 0
    assert r2.get(f"/api/track/submissions/{a}").status_code == 404  # Nida cannot see Somchai's request
    again = r1.post(f"/api/track/open-types/{tid}/start").json()  # the same post twice gives the same request, no copy
    assert again["id"] == a and [s["id"] for s in r1.get("/api/track/submissions").json()] == [a]
    assert [s["id"] for s in r2.get("/api/track/submissions").json()] == []


def test_only_researchers_start_and_anonymous_cannot(env):
    _, tid = env
    publish(client("s1"), tid)
    assert client("s1").post(f"/api/track/open-types/{tid}/start").status_code == 403
    assert TestClient(server.app).post(f"/api/track/open-types/{tid}/start").status_code == 401
    assert TestClient(server.app).get("/api/track/open-types").status_code == 401


def test_started_request_uses_the_newest_approved_version(env):
    tk, tid = env
    publish(client("s1"), tid)
    v2 = tk.new_version(tid, [{"title": "Only step", "documents": ["Form C"], "page": 1, "unsure": False}], "t2.pdf")
    tk.approve(v2)
    sid = client("r1").post(f"/api/track/open-types/{tid}/start").json()["id"]
    assert [s["title"] for s in client("r1").get(f"/api/track/submissions/{sid}").json()["steps"]] == ["Only step"]


def test_staff_type_list_shows_open_state_and_owner(env):
    _, tid = env
    s1 = client("s1")
    assert s1.get("/api/track/types").json()[0]["open"] == 0
    publish(s1, tid, owner_id="s2")
    t = s1.get("/api/track/types").json()[0]
    assert t["open"] == 1 and t["owner_id"] == "s2"


def test_staff_delete_draft_and_unused_type(env):
    tk, tid = env
    s1 = client("s1")
    d = tk.new_version(tid, STEPS, "t2.pdf")
    assert s1.delete(f"/api/track/versions/{d}").status_code == 200
    assert [v["status"] for v in s1.get("/api/track/types").json()] == ["approved"]  # type stays, only the draft went
    tk.put_form(tid, "Form A", "Form A", [{"label": "Name", "type": "text"}])
    assert s1.delete(f"/api/track/types/{tid}").status_code == 200
    assert s1.get("/api/track/types").json() == [] and tk.list_forms(tid) == []
    assert s1.delete(f"/api/track/types/{tid}").status_code == 404


def test_delete_refused_when_requests_use_it_or_not_staff(env):
    tk, tid = env
    publish(client("s1"), tid)
    sid = client("r1").post(f"/api/track/open-types/{tid}/start").json()["id"]
    s1 = client("s1")
    assert s1.delete(f"/api/track/types/{tid}").status_code == 409
    vid = tk.list_types()[0]["id"]
    assert s1.delete(f"/api/track/versions/{vid}").status_code == 409
    assert client("r1").delete(f"/api/track/types/{tid}").status_code == 403
    assert client("r1").get(f"/api/track/submissions/{sid}").status_code == 200  # request untouched


def test_categories_staff_manage_everyone_reads_types_carry_one(env):
    tk, tid = env
    s1, r1 = client("s1"), client("r1")
    a = s1.post("/api/track/categories", json={"name": " ทุนวิจัย "}).json()["id"]
    b = s1.post("/api/track/categories", json={"name": "เบิกจ่าย"}).json()["id"]
    assert s1.post("/api/track/categories", json={"name": "ทุนวิจัย"}).status_code == 409  # same name twice
    assert s1.post("/api/track/categories", json={"name": "  "}).status_code == 400
    assert r1.post("/api/track/categories", json={"name": "x"}).status_code == 403
    assert [c["name"] for c in r1.get("/api/track/categories").json()] == ["ทุนวิจัย", "เบิกจ่าย"]  # a researcher may read
    s1.put("/api/track/categories/order", json={"ids": [b, a]})
    assert [c["name"] for c in r1.get("/api/track/categories").json()] == ["เบิกจ่าย", "ทุนวิจัย"]
    assert s1.put(f"/api/track/categories/{a}", json={"name": "ทุน"}).status_code == 200
    assert s1.put(f"/api/track/types/{tid}/category", json={"category_id": a}).status_code == 200
    publish(s1, tid)
    assert r1.get("/api/track/open-types").json()[0]["category_id"] == a
    assert next(c for c in s1.get("/api/track/categories").json() if c["id"] == a)["types"] == 1
    assert s1.delete(f"/api/track/categories/{a}").status_code == 409  # not empty
    assert s1.put(f"/api/track/types/{tid}/category", json={"category_id": 999}).status_code == 404
    assert s1.put(f"/api/track/types/{tid}/category", json={"category_id": None}).status_code == 200
    assert s1.delete(f"/api/track/categories/{a}").status_code == 200
    assert s1.delete(f"/api/track/categories/{a}").status_code == 404
