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


def test_upsert_adds_a_first_login_and_later_only_refreshes_the_name(tmp_path):
    tk = Tracker(tmp_path / "t.db")
    tk.upsert_user("somsri.k@cmu.ac.th", "Somsri K")
    assert tk.get_user("somsri.k@cmu.ac.th") == {"id": "somsri.k@cmu.ac.th", "name": "Somsri K", "role": "researcher"}
    tk.set_role("somsri.k@cmu.ac.th", "staff")
    tk.upsert_user("somsri.k@cmu.ac.th", "Somsri Kaew", role="researcher")  # role only applies to a new user
    assert tk.get_user("somsri.k@cmu.ac.th") == {"id": "somsri.k@cmu.ac.th", "name": "Somsri Kaew", "role": "staff"}
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
