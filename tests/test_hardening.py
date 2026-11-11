import time
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.core import auth
from app.rag import extract
from app.api import server
from app.core import state
from creds import CREDS


def test_login_locks_after_five_wrong_tries_and_cookie_expires(monkeypatch):
    auth._fails.clear()
    c = TestClient(server.app)
    bad = {"username": CREDS["r1"]["username"], "password": "nope"}
    assert [c.post("/api/track/login", json=bad).status_code for _ in range(6)] == [401] * 5 + [429]
    assert c.post("/api/track/login", json=CREDS["r1"]).status_code == 429  # right password is refused too while locked
    auth._fails.clear()
    assert c.post("/api/track/login", json=CREDS["r1"]).status_code == 200
    assert c.get("/api/track/me").status_code == 200
    monkeypatch.setattr(time, "time", lambda t=time.time(): t + auth.SESSION_TTL + 5)
    assert c.get("/api/track/me").status_code == 401


def test_session_value_cannot_be_moved_to_another_user_or_time():
    uid, start, exp, sig = auth.session_value("r1").split(".")
    c = TestClient(server.app)
    for forged in (f"s1.{start}.{exp}.{sig}", f"r1.{int(start) - 99999}.{exp}.{sig}", f"r1.{start}.{int(exp) + 99999}.{sig}"):
        c.cookies.set("uid", forged)
        assert c.get("/api/track/me").status_code == 401


def test_zip_bomb_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(extract, "MAX_UNZIPPED", 1000)
    p = tmp_path / "a.docx"
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("x.xml", "a" * 5000)
    with pytest.raises(ValueError, match="too large"):
        extract.extract_text(p)


def test_per_minute_limit(monkeypatch):
    state._starts.clear()
    monkeypatch.setattr("app.core.config.MAX_PER_MIN", 2)
    results = []
    for _ in range(3):
        with state.slot("u") as ok:
            results.append(ok)
    assert results == [True, True, False]
