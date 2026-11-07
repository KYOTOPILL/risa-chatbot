import json

import pytest
from fastapi.testclient import TestClient

import forms_ai
import server
import state
import tracker_api
from creds import CREDS
from tracker import Tracker, validate_form

FORM = json.dumps({"title": "Travel claim", "fields": [
    {"label": "Applicant name", "hint": "as on passport", "type": "text", "required": True},
    {"label": "Amount (THB)", "type": "number", "required": True},
    {"label": "Travel date", "type": "date"},
    {"label": "Class", "type": "choice", "options": ["Economy", "Business"]},
    {"label": "Receipt", "type": "file", "required": True}]})
STEP = {"title": "Submit", "documents": ["Travel claim"]}


# ---- field shape ----
def test_validate_form_fills_defaults_and_stable_keys():
    f = validate_form("T", [{"label": "a"}, {"label": "b", "type": "number", "required": 1}])
    assert [(x["key"], x["type"], x["required"], x["options"]) for x in f] == [("f1", "text", False, []), ("f2", "number", True, [])]
    again = validate_form("T", [{**f[1], "label": "renamed"}, {**f[0]}])  # reordered and relabelled: keys stay
    assert [x["key"] for x in again] == ["f2", "f1"]


@pytest.mark.parametrize("bad", [[], [{"label": " "}], [{"label": "a", "type": "radio"}], [{"label": "a", "type": "choice", "options": ["only one"]}]])
def test_validate_form_rejects(bad):
    with pytest.raises(ValueError):
        validate_form("T", bad)


# ---- forms_ai ----
def test_draft_form_parses_types_and_required():
    got = forms_ai.draft_form("Travel claim", STEP, "Grant", llm=lambda m: FORM)
    assert [f["type"] for f in got["fields"]] == ["text", "number", "date", "choice", "file"] and got["fields"][0]["required"] is True


def test_draft_form_falls_back_to_text_for_unknown_type_or_bad_choice():
    reply = json.dumps({"title": "x", "fields": [{"label": "a", "type": "slider"}, {"label": "b", "type": "choice", "options": ["one"]}]})
    assert [f["type"] for f in forms_ai.draft_form("d", STEP, "G", llm=lambda m: reply)["fields"]] == ["text", "text"]


@pytest.mark.parametrize("reply", ["not json", "[]", json.dumps({"title": "x", "fields": []}), json.dumps({"title": "x", "fields": [{"hint": "no label"}]})])
def test_draft_form_rejects_bad_model_output(reply):
    with pytest.raises(ValueError):
        forms_ai.draft_form("Travel claim", STEP, "Grant", llm=lambda m: reply)


def test_draft_form_gives_the_model_the_guide_text(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(forms_ai, "extract_text", lambda p: "GUIDE: receipts must be original")
    forms_ai.draft_form("Travel claim", STEP, "Grant", tmp_path / "g.pdf", llm=lambda m: (seen.append(m[-1]["content"]), FORM)[1])
    assert "receipts must be original" in seen[0]


# ---- endpoints ----
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
    llm = Counting(FORM)
    monkeypatch.setattr(tracker_api, "llm", llm)
    monkeypatch.setattr(tracker_api, "extract_text", lambda p: "")
    v = tk.create_type("Grant", [{"title": "Submit", "documents": ["Travel claim"], "page": 1, "unsure": False}, {"title": "Done", "documents": [], "page": 1, "unsure": False}], "g.pdf")
    tk.approve(v)
    tid = tk.get_version(v)["type_id"]
    return tk, tk.create_submission("S", v, ["r1"], "s1"), tid, llm


def client(uid):
    c = TestClient(server.app)
    assert c.post("/api/track/login", json=CREDS[uid]).status_code == 200
    return c


def draft(c, tid, doc="Travel claim"):
    return c.post(f"/api/track/types/{tid}/forms/draft", json={"doc_name": doc})


def publish_form(tid):
    s1 = client("s1")
    draft(s1, tid)
    assert s1.post(f"/api/track/types/{tid}/forms/approve", json={"doc_name": "Travel claim"}).status_code == 200


def fill(c, sid, answers=None, files=None, doc="Travel claim"):
    a = {"f1": "Somchai", "f2": "1200", "f3": "2026-11-20", "f4": "Economy", **(answers or {})}
    files = files if files is not None else {"f5": ("r.pdf", b"%PDF-1.4", "application/pdf")}
    return c.post(f"/api/track/submissions/{sid}/forms", data={"doc_name": doc, "answers": json.dumps(a), "file_keys": list(files)},
                  files=[("files", v) for v in files.values()])


def test_only_staff_may_manage_forms(env):
    _, _, tid, _ = env
    for c, code in ((client("r1"), 403), (TestClient(server.app), 401)):
        assert draft(c, tid).status_code == code
        assert c.get(f"/api/track/types/{tid}/forms").status_code == code
        assert c.put(f"/api/track/types/{tid}/forms", json={"doc_name": "Travel claim", "title": "t", "fields": [{"label": "a"}]}).status_code == code
        assert c.post(f"/api/track/types/{tid}/forms/approve", json={"doc_name": "Travel claim"}).status_code == code


def test_staff_draft_is_saved_as_draft_and_hidden_from_researchers(env):
    _, sid, tid, llm = env
    got = draft(client("s1"), tid).json()
    assert got["status"] == "draft" and got["fields"][1]["type"] == "number" and llm.n == 1
    assert client("s1").get(f"/api/track/types/{tid}/forms").json()[0]["doc_name"] == "Travel claim"
    assert client("r1").get(f"/api/track/submissions/{sid}").json()["forms"] == {}
    assert fill(client("r1"), sid).status_code == 400  # no approved form yet


def test_staff_edit_then_approve_researcher_sees_the_edited_form(env):
    _, sid, tid, _ = env
    s1, r1 = client("s1"), client("r1")
    draft(s1, tid)
    edited = {"doc_name": "Travel claim", "title": "Travel claim v2", "fields": [{"label": "ชื่อ-สกุล", "type": "text", "required": True}]}
    assert s1.put(f"/api/track/types/{tid}/forms", json=edited).status_code == 200
    s1.post(f"/api/track/types/{tid}/forms/approve", json={"doc_name": "Travel claim"})
    f = r1.get(f"/api/track/submissions/{sid}").json()["forms"]["Travel claim"]
    assert f["title"] == "Travel claim v2" and [x["label"] for x in f["fields"]] == ["ชื่อ-สกุล"]


def test_editing_an_approved_form_keeps_it_approved(env):
    _, sid, tid, _ = env
    publish_form(tid)
    client("s1").put(f"/api/track/types/{tid}/forms", json={"doc_name": "Travel claim", "title": "T", "fields": [{"label": "Only field"}]})
    assert [x["label"] for x in client("r1").get(f"/api/track/submissions/{sid}").json()["forms"]["Travel claim"]["fields"]] == ["Only field"]


def test_bad_edits_and_unknown_documents_are_rejected(env):
    _, _, tid, _ = env
    s1 = client("s1")
    put = lambda **kw: s1.put(f"/api/track/types/{tid}/forms", json={"doc_name": "Travel claim", "title": "t", "fields": [{"label": "a"}], **kw}).status_code
    assert put(fields=[]) == 400 and put(fields=[{"label": "  "}]) == 400 and put(title=" ") == 400 and put(fields=[{"label": "a", "type": "radio"}]) == 400
    assert put(doc_name="Not a document") == 400 and draft(s1, tid, "Not a document").status_code == 400
    assert s1.post(f"/api/track/types/{tid}/forms/approve", json={"doc_name": "Travel claim"}).status_code == 404


def test_model_failure_is_a_502_and_saves_nothing(env, monkeypatch):
    _, _, tid, _ = env
    monkeypatch.setattr(tracker_api, "llm", lambda m: "garbage")
    assert draft(client("s1"), tid).status_code == 502
    assert client("s1").get(f"/api/track/types/{tid}/forms").json() == []


# ---- researcher fills the form on the website ----
def test_fill_form_saves_answers_screens_them_and_hides_server_paths(env):
    _, sid, tid, llm = env
    publish_form(tid)
    llm.reply = "[]"
    r = fill(client("r1"), sid)
    assert r.status_code == 200 and r.json()["status"] == "screened"
    assert "Somchai" in llm.seen[-1] and "1200" in llm.seen[-1]  # the checker reads the answers
    up = client("r1").get(f"/api/track/submissions/{sid}").json()["uploads"][0]
    vals = {a["label"]: a["value"] for a in up["answers"]}
    assert vals["Applicant name"] == "Somchai" and vals["Receipt"] == {"name": "r.pdf"} and "path" not in json.dumps(up)


@pytest.mark.parametrize("answers,files,why", [
    ({"f1": ""}, None, "required text"),
    ({"f2": "abc"}, None, "number"),
    ({"f3": "20/11/2026"}, None, "date"),
    ({"f4": "First"}, None, "choice"),
    ({}, {}, "required file"),
])
def test_fill_form_validates(env, answers, files, why):
    _, sid, tid, _ = env
    publish_form(tid)
    assert fill(client("r1"), sid, answers, files).status_code == 400, why


def test_refill_replaces_answers_and_keeps_the_earlier_file(env):
    tk, sid, tid, llm = env
    publish_form(tid)
    llm.reply = "[]"
    fill(client("r1"), sid)
    r = fill(client("r1"), sid, {"f2": "999"}, files={})  # no new file: the earlier receipt stays
    assert r.status_code == 200
    up = client("r1").get(f"/api/track/submissions/{sid}").json()["uploads"][0]
    assert {a["label"]: a["value"] for a in up["answers"]}["Amount (THB)"] == "999" and up["answers"][4]["value"] == {"name": "r.pdf"}


def test_form_goes_through_send_and_staff_review_with_file_download(env):
    tk, sid, tid, llm = env
    publish_form(tid)
    llm.reply = "[]"
    r1, s1 = client("r1"), client("s1")
    uid = fill(r1, sid).json()["upload_id"]
    assert r1.post(f"/api/track/uploads/{uid}/send").status_code == 200
    q = s1.get("/api/track/review-queue").json()[0]
    assert q["answers"][0]["value"] == "Somchai" and "path" not in json.dumps(q)
    assert s1.get(f"/api/track/uploads/{uid}/answer-file", params={"key": "f5"}).content == b"%PDF-1.4"
    assert client("r2").get(f"/api/track/uploads/{uid}/answer-file", params={"key": "f5"}).status_code == 404
    assert r1.get(f"/api/track/uploads/{uid}/file").status_code == 404  # a form has no single file
    assert s1.post(f"/api/track/uploads/{uid}/review", json={"decision": "approve", "dismissed": [], "note": ""}).json()["advanced"] is True
    assert fill(r1, sid).status_code == 400  # step moved on and the document is approved


def test_sent_form_cannot_be_refilled_and_plain_upload_is_refused(env):
    _, sid, tid, llm = env
    publish_form(tid)
    llm.reply = "[]"
    r1 = client("r1")
    uid = fill(r1, sid).json()["upload_id"]
    r1.post(f"/api/track/uploads/{uid}/send")
    assert fill(r1, sid).status_code == 400
    assert r1.post(f"/api/track/submissions/{sid}/uploads", data={"doc_name": "Travel claim"}, files={"file": ("a.pdf", b"%PDF-1.4", "application/pdf")}).status_code == 400


def test_other_researcher_and_anonymous_cannot_fill(env):
    _, sid, tid, _ = env
    publish_form(tid)
    assert fill(client("r2"), sid).status_code == 404 and fill(client("s2"), sid).status_code == 404  # staff not in charge
    assert fill(TestClient(server.app), sid).status_code == 401


def test_staff_in_charge_fills_sends_and_reviews_for_the_researcher(env):
    _, sid, tid, _ = env
    publish_form(tid)
    s1 = client("s1")
    r = fill(s1, sid)
    assert r.status_code == 200
    uid = r.json()["upload_id"]
    assert s1.post(f"/api/track/uploads/{uid}/send").json()["status"] == "sent"
    assert s1.post(f"/api/track/uploads/{uid}/review", json={"decision": "approve", "dismissed": [], "note": ""}).status_code == 200
    assert client("r1").get(f"/api/track/submissions/{sid}").json()["current_step"] == 1


def test_model_failure_while_screening_still_saves_the_form(env, monkeypatch):
    _, sid, tid, _ = env
    publish_form(tid)
    monkeypatch.setattr(tracker_api, "llm", lambda m: "garbage")
    assert fill(client("r1"), sid).json()["status"] == "cannot_check"


def test_attachment_may_be_a_photo_but_not_an_executable(env):
    _, sid, tid, llm = env
    publish_form(tid)
    llm.reply = "[]"
    assert fill(client("r1"), sid, files={"f5": ("scan.jpg", b"\xff\xd8\xff", "image/jpeg")}).status_code == 200
    assert fill(client("r1"), sid, files={"f5": ("x.exe", b"MZ", "application/octet-stream")}).status_code == 400


def test_progress_lines_stream_status_then_done_and_plain_json_is_unchanged(env):
    _, sid, tid, llm = env
    publish_form(tid)
    llm.reply = "[]"
    r1 = client("r1")
    r = r1.post(f"/api/track/submissions/{sid}/forms", headers={"accept": "application/x-ndjson"},
                data={"doc_name": "Travel claim", "answers": json.dumps({"f1": "a", "f2": "5", "f3": "2026-01-01", "f4": "Economy"}), "file_keys": ["f5"]},
                files=[("files", ("r.pdf", b"%PDF-1.4", "application/pdf"))])
    lines = [json.loads(l) for l in r.text.splitlines()]
    assert r.headers["content-type"].startswith("application/x-ndjson")
    assert [next(iter(l)) for l in lines] == ["status", "status", "done"] and "5 ช่อง" in lines[0]["status"] and lines[-1]["done"]["status"] == "screened"
    plain = fill(r1, sid)  # no Accept header: the same JSON as before
    assert plain.status_code == 200 and plain.json()["status"] == "screened"


def test_progress_error_comes_as_an_error_line_and_validation_stays_a_plain_400(env):
    _, _, tid, _ = env
    s1 = client("s1")
    s1.post(f"/api/track/types/{tid}/forms/approve", json={"doc_name": "Travel claim"})  # nothing drafted: plain 404 before streaming
    import tracker_api as t
    old = t.llm
    t.llm = lambda m: "garbage"
    try:
        r = s1.post(f"/api/track/types/{tid}/forms/draft", headers={"accept": "application/x-ndjson"}, json={"doc_name": "Travel claim"})
    finally:
        t.llm = old
    lines = [json.loads(l) for l in r.text.splitlines()]
    assert lines[-1].keys() == {"error"} and "could not draft" in lines[-1]["error"]
    assert s1.get(f"/api/track/types/{tid}/forms").json() == []
