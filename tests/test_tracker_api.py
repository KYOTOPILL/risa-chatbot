import pytest
from fastapi.testclient import TestClient

import server
import state
from tracker import Tracker

STEPS3 = [{"title": t, "documents": [], "page": None, "unsure": False} for t in ("Submit", "Review", "Sign")]


@pytest.fixture
def env(tmp_path, monkeypatch):
    tk = Tracker(tmp_path / "t.db")
    monkeypatch.setattr(state, "get_tracker", lambda: tk)
    v = tk.create_type("CMU", STEPS3, "cmu.pdf")
    tk.approve(v)
    sid = tk.create_submission("Somchai CMU", v, ["r1"], "s1")
    return tk, v, sid


def login(user_id):
    c = TestClient(server.app)
    r = c.post("/api/track/login", json={"user_id": user_id})
    assert r.status_code == 200
    return c


def test_login_unknown_user_401():
    assert TestClient(server.app).post("/api/track/login", json={"user_id": "nobody"}).status_code == 401


def test_login_sets_cookie_and_me_returns_role(env):
    assert login("s1").get("/api/track/me").json() == {"id": "s1", "name": "Malee", "role": "staff"}


def test_anonymous_requests_401(env):
    c = TestClient(server.app)
    assert c.get("/api/track/me").status_code == 401
    assert c.get("/api/track/submissions").status_code == 401


def test_researcher_cannot_create_or_move(env):
    tk, v, sid = env
    r1 = login("r1")
    assert r1.post("/api/track/submissions", json={"title": "x", "version_id": v, "researcher_ids": ["r1"], "staff_id": "s1"}).status_code == 403
    assert r1.post(f"/api/track/submissions/{sid}/move", json={"to_step": 1}).status_code == 403


def test_researcher_gets_404_for_foreign_submission(env):
    _, _, sid = env
    assert login("r2").get(f"/api/track/submissions/{sid}").status_code == 404
    assert login("r2").get("/api/track/submissions/999").status_code == 404  # same answer as a missing id
    assert login("r1").get(f"/api/track/submissions/{sid}").json()["id"] == sid


def test_staff_creates_submission_and_researcher_sees_it(env):
    _, v, _ = env
    r = login("s2").post("/api/track/submissions", json={"title": "Nida", "version_id": v, "researcher_ids": ["r2"], "staff_id": "s2"})
    assert r.status_code == 200
    assert [s["title"] for s in login("r2").get("/api/track/submissions").json()] == ["Nida"]


def test_create_rejects_unknown_users_and_draft_versions(env):
    tk, v, _ = env
    s1 = login("s1")
    assert s1.post("/api/track/submissions", json={"title": "x", "version_id": v, "researcher_ids": ["ghost"], "staff_id": "s1"}).status_code == 400
    draft = tk.create_type("Other", STEPS3, "o.pdf")
    assert s1.post("/api/track/submissions", json={"title": "x", "version_id": draft, "researcher_ids": ["r1"], "staff_id": "s1"}).status_code == 400


def test_staff_not_in_charge_move_403(env):
    _, _, sid = env
    assert login("s2").post(f"/api/track/submissions/{sid}/move", json={"to_step": 1}).status_code == 403


def test_move_works_and_out_of_range_400(env):
    _, _, sid = env
    s1 = login("s1")
    assert s1.post(f"/api/track/submissions/{sid}/move", json={"to_step": 1, "note": "ok"}).status_code == 200
    assert s1.get(f"/api/track/submissions/{sid}").json()["current_step"] == 1
    assert s1.post(f"/api/track/submissions/{sid}/move", json={"to_step": 9}).status_code == 400


def test_mock_users_lists_everyone_with_roles():
    got = TestClient(server.app).get("/api/track/mock-users").json()
    assert {"id": "s1", "name": "Malee", "role": "staff"} in got
