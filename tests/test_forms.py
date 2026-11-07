import io
import json

import pytest
from docx import Document
from fastapi.testclient import TestClient

import forms_ai
import server
import state
import tracker_api
from creds import CREDS
from tracker import Tracker

FORM = json.dumps({"title": "Travel claim", "fields": [{"label": "Applicant name", "hint": "as on passport"}, {"label": "Amount (THB)", "hint": ""}]})
STEP = {"title": "Submit", "documents": ["Travel claim"]}


def words(docx_bytes):
    d = Document(io.BytesIO(docx_bytes))
    return " ".join([p.text for p in d.paragraphs] + [c.text for t in d.tables for r in t.rows for c in r.cells])


# ---- forms_ai ----
def test_draft_form_parses_title_and_fields():
    got = forms_ai.draft_form("Travel claim", STEP, "Grant", llm=lambda m: FORM)
    assert got["title"] == "Travel claim" and [f["label"] for f in got["fields"]] == ["Applicant name", "Amount (THB)"]


@pytest.mark.parametrize("reply", ["not json", "[]", json.dumps({"title": "x", "fields": []}), json.dumps({"title": "x", "fields": [{"hint": "no label"}]})])
def test_draft_form_rejects_bad_model_output(reply):
    with pytest.raises(ValueError):
        forms_ai.draft_form("Travel claim", STEP, "Grant", llm=lambda m: reply)


def test_build_docx_has_title_labels_and_ai_notice(tmp_path):
    p = tmp_path / "f.docx"
    forms_ai.build_docx(json.loads(FORM), p)
    text = words(p.read_bytes())
    assert "Travel claim" in text and "Applicant name" in text and "Amount (THB)" in text and forms_ai.NOTICE in text


# ---- endpoint ----
class Counting:
    def __init__(self, reply):
        self.reply, self.n = reply, 0

    def __call__(self, messages):
        self.n += 1
        return self.reply


@pytest.fixture
def env(tmp_path, monkeypatch):
    tk = Tracker(tmp_path / "t.db")
    monkeypatch.setattr(state, "get_tracker", lambda: tk)
    monkeypatch.setattr(tracker_api, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(tracker_api, "find_template", lambda name: None)
    llm = Counting(FORM)
    monkeypatch.setattr(tracker_api, "llm", llm)
    v = tk.create_type("Grant", [{"title": "Submit", "documents": ["Travel claim"], "page": 1, "unsure": False}], "g.pdf")
    tk.approve(v)
    return tk, tk.create_submission("S", v, ["r1"], "s1"), llm


def client(uid):
    c = TestClient(server.app)
    assert c.post("/api/track/login", json=CREDS[uid]).status_code == 200
    return c


def get(c, sid, doc="Travel claim"):
    return c.get(f"/api/track/submissions/{sid}/form", params={"doc": doc})


def test_researcher_downloads_an_ai_made_blank_form_once(env):
    _, sid, llm = env
    r1 = client("r1")
    a, b = get(r1, sid), get(r1, sid)
    assert a.status_code == 200 and "Applicant name" in words(a.content) and b.content == a.content
    assert llm.n == 1  # generated once, then served from disk


def test_real_template_wins_over_ai(env, tmp_path, monkeypatch):
    _, sid, llm = env
    tpl = tmp_path / "Travel claim.docx"
    forms_ai.build_docx({"title": "Official", "fields": [{"label": "Official field", "hint": ""}]}, tpl)
    monkeypatch.setattr(tracker_api, "find_template", lambda name: tpl)
    r = get(client("r1"), sid)
    assert "Official field" in words(r.content) and llm.n == 0


def test_other_researcher_anonymous_and_unknown_document(env):
    _, sid, _ = env
    assert get(client("r2"), sid).status_code == 404
    assert get(TestClient(server.app), sid).status_code == 401
    assert get(client("r1"), sid, doc="Not a document").status_code == 400


def test_model_failure_is_a_clear_502_and_not_cached(env, monkeypatch):
    _, sid, _ = env
    monkeypatch.setattr(tracker_api, "llm", lambda m: "garbage")
    assert get(client("r1"), sid).status_code == 502
    monkeypatch.setattr(tracker_api, "llm", lambda m: FORM)
    assert get(client("r1"), sid).status_code == 200


def test_download_name_keeps_thai_marks(env, tmp_path):
    tk, _, _ = env
    v = tk.create_type("งาน", [{"title": "ยื่น", "documents": ["แบบขอเบิก"], "page": 1, "unsure": False}], "g.pdf")
    tk.approve(v)
    sid = tk.create_submission("S2", v, ["r1"], "s1")
    cd = get(client("r1"), sid, doc="แบบขอเบิก").headers["content-disposition"]
    from urllib.parse import unquote
    assert unquote(cd.split("''")[1]) == "แบบขอเบิก.docx"
