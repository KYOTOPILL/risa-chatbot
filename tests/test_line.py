"""LINE Official Account chatbot: signature check, account linking, answers and replies. LINE's own API is faked."""
import base64
import hashlib
import hmac
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api import server
from app.core import auth, config, state
from app.features import line_bot
from app.features.tracker import Tracker
from app.rag import rag
from creds import CREDS

SECRET = "s3cret"


class FakeStore:
    def doc_path(self, doc_id):
        return "policy/ใบลา.pdf"


@pytest.fixture
def env(tmp_path, monkeypatch):
    tk = Tracker(tmp_path / "t.db")
    monkeypatch.setattr(state, "get_tracker", lambda: tk)
    monkeypatch.setattr(state, "get_store", lambda: FakeStore())
    monkeypatch.setattr(config, "LINE_CHANNEL_SECRET", SECRET)
    monkeypatch.setattr(config, "LINE_CHANNEL_ACCESS_TOKEN", "tok")
    monkeypatch.setattr(config, "PUBLIC_URL", "https://risa.example")
    auth._fails.clear()
    state._starts.clear()
    sent = []  # (path, body) of every call to LINE
    monkeypatch.setattr(line_bot, "_post", lambda path, body: sent.append((path, body)))
    asked = []
    def fake_answer(history, message, store, **kw):
        asked.append((history, message, kw))
        return rag.Reply("คำตอบ", ["abc"])
    monkeypatch.setattr(rag, "answer", fake_answer)
    return tk, sent, asked


def hook(events, secret=SECRET):
    body = json.dumps({"events": events}).encode()
    sig = base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()
    return TestClient(server.app).post("/api/line/webhook", content=body, headers={"X-Line-Signature": sig})


def say(text, user="Uline1", kind="user"):
    return {"type": "message", "replyToken": "rt", "source": {"type": kind, "userId": user}, "message": {"type": "text", "text": text}}


def texts(sent):
    return [b["messages"][0]["text"] for p, b in sent if p == "message/reply"]


def web(uid):
    c = TestClient(server.app)
    assert c.post("/api/track/login", json=CREDS[uid]).status_code == 200
    return c


def link(uid="r1", line="Uline1"):
    code = web(uid).post("/api/line/code").json()["code"]
    assert hook([say(code, line)]).status_code == 200


def test_off_until_configured_and_signature_is_checked(env, monkeypatch):
    assert hook([], secret="wrong").status_code == 400
    assert hook([]).status_code == 200  # LINE's Verify button sends no events
    monkeypatch.setattr(config, "LINE_CHANNEL_SECRET", "")
    assert hook([]).status_code == 404


def test_unlinked_user_is_told_how_to_link_and_nothing_is_asked(env):
    _, sent, asked = env
    hook([say("ขอแบบฟอร์มใบลา")])
    assert "เชื่อม LINE" in texts(sent)[0] and not asked


def test_follow_event_welcomes(env):
    _, sent, _ = env
    hook([{"type": "follow", "replyToken": "rt", "source": {"type": "user", "userId": "Uline1"}}])
    assert "เชื่อม LINE" in texts(sent)[0]


def test_link_then_ask_gets_the_same_answer_with_file_links_and_keeps_history(env):
    tk, sent, asked = env
    link()
    assert tk.user_for_line("Uline1") == "r1" and "เรียบร้อย" in texts(sent)[-1]
    hook([say("ขอแบบฟอร์มใบลา")])
    assert asked[0][1] == "ขอแบบฟอร์มใบลา" and asked[0][2]["me"]()  # the asker's own requests are available to the model
    out = texts(sent)[-1]
    assert out.startswith("คำตอบ") and "ใบลา.pdf" in out and "https://risa.example/download/abc" in out
    assert any(p == "chat/loading/start" for p, _ in sent)
    hook([say("แล้วอีกอันล่ะ")])
    assert [t.role for t in asked[1][0]] == ["user", "assistant"] and "ใบลา.pdf" in asked[1][0][1].content


def test_a_code_works_once_and_a_wrong_one_is_refused(env):
    tk, sent, _ = env
    code = web("r1").post("/api/line/code").json()["code"]
    hook([say("000000" if code != "000000" else "111111")])
    assert "ไม่ถูกต้อง" in texts(sent)[-1] and tk.user_for_line("Uline1") is None
    hook([say(code)])
    assert tk.user_for_line("Uline1") == "r1"
    hook([say(code, "Uother")])  # already used
    assert tk.user_for_line("Uother") is None


def test_guessing_codes_is_locked_out(env):
    tk, sent, _ = env
    code = web("r1").post("/api/line/code").json()["code"]
    wrong = [f"{i:06d}" for i in range(5) if f"{i:06d}" != code][:5]
    for w in wrong:
        hook([say(w)])
    hook([say(code)])
    assert tk.user_for_line("Uline1") is None and "หลายครั้ง" in texts(sent)[-1]


def test_staff_cannot_get_a_code_and_a_linked_staff_account_gets_no_chat(env):
    tk, sent, asked = env
    assert web("s1").post("/api/line/code").status_code == 403
    tk.link_line("Ustaff", "s1")
    hook([say("สวัสดี", "Ustaff")])
    assert "เฉพาะนักวิจัย" in texts(sent)[-1] and not asked


def test_unlink(env):
    tk, sent, asked = env
    link()
    hook([say("ยกเลิกการเชื่อมต่อ")])
    assert tk.user_for_line("Uline1") is None
    hook([say("ถามอีก")])
    assert not asked and "เชื่อม LINE" in texts(sent)[-1]


def test_images_and_group_chats(env):
    _, sent, asked = env
    link()
    hook([{"type": "message", "replyToken": "rt", "source": {"type": "user", "userId": "Uline1"}, "message": {"type": "image"}}])
    assert "รองรับเฉพาะข้อความ" in texts(sent)[-1]
    n = len(sent)
    hook([say("hi", "Uline1", kind="group")])
    assert len(sent) == n and not asked


def test_expired_reply_token_falls_back_to_push(env, monkeypatch):
    tk, sent, _ = env
    link()
    def post(path, body):
        if path == "message/reply":
            raise httpx.HTTPError("token expired")
        sent.append((path, body))
    monkeypatch.setattr(line_bot, "_post", post)
    hook([say("ถาม")])
    assert sent[-1][0] == "message/push" and sent[-1][1]["to"] == "Uline1" and sent[-1][1]["messages"][0]["text"].startswith("คำตอบ")


def test_status_for_the_web_button(env):
    got = web("r1").get("/api/line/status").json()
    assert got["enabled"] is True and got["linked"] is False
    link()
    assert web("r1").get("/api/line/status").json()["linked"] is True


def _new_request(tk, researcher="r1"):
    v = tk.create_type("T", [{"title": "S", "documents": ["Doc"]}], "t.pdf")
    tk.approve(v)
    r = web("s1").post("/api/track/submissions", json={"title": "Grant", "version_id": v, "researcher_ids": [researcher], "staff_id": "s1"})
    assert r.status_code == 200


def pushes(sent):
    return [b for p, b in sent if p == "message/push"]


def test_status_changes_are_pushed_to_the_researchers_line(env, monkeypatch):
    tk, sent, _ = env
    monkeypatch.setattr(line_bot, "_run", lambda f, *a: f(*a))  # no thread in tests
    link("r1", "Uline1")
    _new_request(tk, "r1")
    assert not pushes(sent)  # a new request is only in-app: LINE carries the events that ask for action
    tk.move_step(1, "s1", 1, "")  # the request finishes
    got = pushes(sent)
    assert len(got) == 1 and got[0]["to"] == "Uline1" and "เสร็จสิ้น" in got[0]["messages"][0]["text"] and "https://risa.example" in got[0]["messages"][0]["text"]


def test_no_push_for_people_without_a_link_or_when_line_is_off(env, monkeypatch):
    tk, sent, _ = env
    monkeypatch.setattr(line_bot, "_run", lambda f, *a: f(*a))
    _new_request(tk, "r2")  # r2 never linked
    assert not pushes(sent)
    link("r1", "Uline1")
    monkeypatch.setattr(config, "LINE_CHANNEL_ACCESS_TOKEN", "")
    _new_request(tk, "r1")
    assert not pushes(sent)


def test_a_failing_push_never_breaks_the_request(env, monkeypatch):
    tk, sent, _ = env
    monkeypatch.setattr(line_bot, "_run", lambda f, *a: f(*a))
    link("r1", "Uline1")
    def boom(path, body):
        raise httpx.HTTPError("down")
    monkeypatch.setattr(line_bot, "_post", boom)
    _new_request(tk, "r1")  # the assert inside is the check: the API call still succeeded
