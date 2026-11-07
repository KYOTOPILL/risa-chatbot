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


# ---- endpoints: staff draft, edit, approve; researcher sees it only after approval ----
class Counting:
    def __init__(self, reply):
        self.reply, self.n, self.seen = reply, 0, []

    def __call__(self, messages):
        self.n += 1
        self.seen.append(messages[-1]["content"])
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
    tid = tk.get_version(v)["type_id"]
    return tk, tk.create_submission("S", v, ["r1"], "s1"), tid, llm


def client(uid):
    c = TestClient(server.app)
    assert c.post("/api/track/login", json=CREDS[uid]).status_code == 200
    return c


def download(c, sid, doc="Travel claim"):
    return c.get(f"/api/track/submissions/{sid}/form", params={"doc": doc})


def draft(c, tid, doc="Travel claim"):
    return c.post(f"/api/track/types/{tid}/forms/draft", json={"doc_name": doc})


def test_only_staff_may_manage_forms(env):
    _, _, tid, _ = env
    for c, code in ((client("r1"), 403), (TestClient(server.app), 401)):
        assert draft(c, tid).status_code == code
        assert c.get(f"/api/track/types/{tid}/forms").status_code == code
        assert c.put(f"/api/track/types/{tid}/forms", json={"doc_name": "Travel claim", "title": "t", "fields": [{"label": "a", "hint": ""}]}).status_code == code
        assert c.post(f"/api/track/types/{tid}/forms/approve", json={"doc_name": "Travel claim"}).status_code == code


def test_staff_draft_is_saved_as_draft_and_hidden_from_researchers(env):
    _, sid, tid, llm = env
    s1, r1 = client("s1"), client("r1")
    got = draft(s1, tid).json()
    assert got["status"] == "draft" and got["fields"][0]["label"] == "Applicant name" and llm.n == 1
    assert s1.get(f"/api/track/types/{tid}/forms").json()[0]["doc_name"] == "Travel claim"
    assert download(r1, sid).status_code == 404
    assert r1.get(f"/api/track/submissions/{sid}").json()["forms"] == []


def test_staff_edit_then_approve_researcher_gets_the_edited_form(env):
    _, sid, tid, _ = env
    s1, r1 = client("s1"), client("r1")
    draft(s1, tid)
    edited = {"doc_name": "Travel claim", "title": "Travel claim v2", "fields": [{"label": "ชื่อ-สกุล", "hint": "ตามบัตร"}, {"label": "Trip dates", "hint": ""}]}
    assert s1.put(f"/api/track/types/{tid}/forms", json=edited).status_code == 200
    assert s1.post(f"/api/track/types/{tid}/forms/approve", json={"doc_name": "Travel claim"}).status_code == 200
    assert r1.get(f"/api/track/submissions/{sid}").json()["forms"] == ["Travel claim"]
    text = words(download(r1, sid).content)
    assert "Travel claim v2" in text and "ชื่อ-สกุล" in text and "Applicant name" not in text


def test_editing_an_approved_form_keeps_it_approved(env):
    _, sid, tid, _ = env
    s1 = client("s1")
    draft(s1, tid)
    s1.post(f"/api/track/types/{tid}/forms/approve", json={"doc_name": "Travel claim"})
    s1.put(f"/api/track/types/{tid}/forms", json={"doc_name": "Travel claim", "title": "T", "fields": [{"label": "Only field", "hint": ""}]})
    assert "Only field" in words(download(client("r1"), sid).content)


def test_bad_edits_and_unknown_documents_are_rejected(env):
    _, _, tid, _ = env
    s1 = client("s1")
    put = lambda **kw: s1.put(f"/api/track/types/{tid}/forms", json={"doc_name": "Travel claim", "title": "t", "fields": [{"label": "a", "hint": ""}], **kw}).status_code
    assert put(fields=[]) == 400 and put(fields=[{"label": "  ", "hint": ""}]) == 400 and put(title=" ") == 400
    assert put(doc_name="Not a document") == 400 and draft(s1, tid, "Not a document").status_code == 400
    assert s1.post(f"/api/track/types/{tid}/forms/approve", json={"doc_name": "Travel claim"}).status_code == 404  # nothing drafted yet


def test_model_failure_is_a_502_and_saves_nothing(env, monkeypatch):
    _, _, tid, _ = env
    s1 = client("s1")
    monkeypatch.setattr(tracker_api, "llm", lambda m: "garbage")
    assert draft(s1, tid).status_code == 502
    assert s1.get(f"/api/track/types/{tid}/forms").json() == []


def test_other_researcher_and_anonymous_cannot_download(env):
    _, sid, tid, _ = env
    s1 = client("s1")
    draft(s1, tid)
    s1.post(f"/api/track/types/{tid}/forms/approve", json={"doc_name": "Travel claim"})
    assert download(client("r2"), sid).status_code == 404
    assert download(TestClient(server.app), sid).status_code == 401
    assert download(client("r1"), sid, doc="Not a document").status_code == 400


def test_staff_can_upload_an_official_form_that_replaces_the_ai_one(env, tmp_path):
    _, sid, tid, _ = env
    s1 = client("s1")
    official = tmp_path / "o.docx"
    forms_ai.build_docx({"title": "Official", "fields": [{"label": "Official field", "hint": ""}]}, official)
    r = s1.post(f"/api/track/types/{tid}/forms/upload", data={"doc_name": "Travel claim"}, files={"file": ("o.docx", official.read_bytes(), "application/octet-stream")})
    assert r.status_code == 200 and r.json()["status"] == "approved"
    assert "Official field" in words(download(client("r1"), sid).content)
    bad = s1.post(f"/api/track/types/{tid}/forms/upload", data={"doc_name": "Travel claim"}, files={"file": ("x.exe", b"MZ", "application/octet-stream")})
    assert bad.status_code == 400


def test_template_folder_still_works_when_no_form_is_approved(env, tmp_path, monkeypatch):
    _, sid, _, _ = env
    tpl = tmp_path / "Travel claim.docx"
    forms_ai.build_docx({"title": "Folder", "fields": [{"label": "Folder field", "hint": ""}]}, tpl)
    monkeypatch.setattr(tracker_api, "find_template", lambda name: tpl)
    assert client("r1").get(f"/api/track/submissions/{sid}").json()["forms"] == ["Travel claim"]
    assert "Folder field" in words(download(client("r1"), sid).content)


def test_screening_uses_the_approved_fields_as_the_reference(env, monkeypatch):
    _, sid, tid, llm = env
    s1, r1 = client("s1"), client("r1")
    draft(s1, tid)
    s1.post(f"/api/track/types/{tid}/forms/approve", json={"doc_name": "Travel claim"})
    monkeypatch.setattr(tracker_api, "extract_text", lambda p: "some filled form text")
    screen = Counting("[]")
    monkeypatch.setattr(tracker_api, "llm", screen)
    r = r1.post(f"/api/track/submissions/{sid}/uploads", data={"doc_name": "Travel claim"}, files={"file": ("a.pdf", b"%PDF-1.4", "application/pdf")})
    assert r.json()["status"] == "screened" and "Applicant name" in screen.seen[0]


def test_download_name_keeps_thai_marks(env):
    tk, _, _, _ = env
    v = tk.create_type("งาน", [{"title": "ยื่น", "documents": ["แบบขอเบิก"], "page": 1, "unsure": False}], "g.pdf")
    tk.approve(v)
    tid, sid = tk.get_version(v)["type_id"], tk.create_submission("S2", v, ["r1"], "s1")
    tk.put_form(tid, "แบบขอเบิก", "แบบขอเบิก", [{"label": "ชื่อ", "hint": ""}], "approved")
    from urllib.parse import unquote
    cd = download(client("r1"), sid, doc="แบบขอเบิก").headers["content-disposition"]
    assert unquote(cd.split("''")[1]) == "แบบขอเบิก.docx"
