import pytest
from fastapi.testclient import TestClient

from app.api import server
from app.core import state
from creds import CREDS
from app.features.tracker import Tracker

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
    r = c.post("/api/track/login", json=CREDS[user_id])
    assert r.status_code == 200
    return c


def test_login_with_wrong_or_unknown_credentials_401():
    c = TestClient(server.app)
    assert c.post("/api/track/login", json={"username": "nobody", "password": "x"}).status_code == 401
    assert c.post("/api/track/login", json={**CREDS["s1"], "password": "wrong"}).status_code == 401
    assert c.get("/api/track/me").status_code == 401


def test_forged_or_tampered_cookie_is_rejected():
    c = TestClient(server.app)
    for bad in ("s1", "s1.deadbeef", "x.y"):
        c.cookies.clear()
        c.cookies.set("uid", bad)
        assert c.get("/api/track/me").status_code == 401, bad
    login("r1")  # a real session cookie for r1 must not work when re-labelled as s1
    real = login("r1").cookies.get("uid")
    c.cookies.clear()
    c.cookies.set("uid", "s1" + real[real.index("."):])
    assert c.get("/api/track/me").status_code == 401


def test_user_list_needs_login_and_never_shows_passwords(env):
    assert TestClient(server.app).get("/api/track/users").status_code == 401
    got = login("r1").get("/api/track/users").json()
    assert "password" not in str(got) and {"id": "s1", "name": "Malee", "role": "staff", "active": True} in got


def test_login_sets_cookie_and_me_returns_role(env):
    assert login("s1").get("/api/track/me").json() == {"id": "s1", "name": "Malee", "role": "staff", "avatar_color": "", "photo": False}


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


# ---- Task 4: AI-drafted type steps ----
import json

from app.features import tracker_api

GOOD = json.dumps([{"title": "Submit", "documents": ["Form A"], "page": 1, "unsure": False}])


@pytest.fixture
def ai(env, tmp_path, monkeypatch):
    monkeypatch.setattr(tracker_api, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(tracker_api, "llm", lambda messages: GOOD)
    return tmp_path / "uploads"


def pdf_bytes(text="hello scholarship"):
    import pymupdf
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), text)
    return doc.tobytes()


def post_type(client, name="New", filename="doc.pdf", data=None):
    return client.post("/api/track/types", data={"name": name}, files={"file": (filename, data or pdf_bytes(), "application/pdf")})


def test_upload_type_creates_draft_not_live(env, ai):
    tk, _, _ = env
    r = post_type(login("s1"))
    assert r.status_code == 200 and r.json()["steps"][0]["title"] == "Submit"
    assert tk.get_version(r.json()["version_id"])["status"] == "draft"
    assert "New" not in [t["type_name"] for t in tk.list_types()]


def test_bad_draft_saves_nothing_422(env, ai, monkeypatch):
    tk, _, _ = env
    monkeypatch.setattr(tracker_api, "llm", lambda messages: "not json")
    assert post_type(login("s1")).status_code == 422
    assert tk.list_drafts() == []


def test_researcher_cannot_draft_403(env, ai):
    assert post_type(login("r1")).status_code == 403


def test_hostile_filename_stays_inside_upload_dir(env, ai):
    assert post_type(login("s1"), filename="../../evil.pdf").status_code == 200
    saved = [p for p in ai.rglob("*") if p.is_file()]
    assert len(saved) == 1 and saved[0].resolve().is_relative_to(ai.resolve())


def test_oversize_and_wrong_ext_rejected(env, ai, monkeypatch):
    monkeypatch.setattr(tracker_api, "MAX_UPLOAD_BYTES", 100)
    s1 = login("s1")
    assert post_type(s1, data=b"x" * 101).status_code == 413
    assert post_type(s1, filename="evil.exe").status_code == 400
    assert not ai.exists() or not [p for p in ai.rglob("*") if p.is_file()]


def test_edit_redraft_and_approve_a_draft(env, ai, monkeypatch):
    tk, _, _ = env
    s1 = login("s1")
    vid = post_type(s1).json()["version_id"]
    new = [{"title": "Edited", "documents": [], "page": None, "unsure": False}]
    assert s1.put(f"/api/track/versions/{vid}", json={"steps": new}).status_code == 200
    assert tk.get_version(vid)["steps"][0]["title"] == "Edited"
    assert s1.post(f"/api/track/versions/{vid}/redraft").json()["steps"][0]["title"] == "Submit"
    assert s1.post(f"/api/track/versions/{vid}/approve").status_code == 200
    assert s1.put(f"/api/track/versions/{vid}", json={"steps": new}).status_code == 200  # live: text can still be fixed
    assert s1.put(f"/api/track/versions/{vid}", json={"steps": []}).status_code == 400


def test_new_version_of_existing_type(env, ai):
    tk, v, _ = env
    tid = tk.get_version(v)["type_id"]
    r = login("s1").post(f"/api/track/types/{tid}/versions", files={"file": ("n.pdf", pdf_bytes(), "application/pdf")})
    assert r.status_code == 200 and tk.get_version(r.json()["version_id"])["version"] == 2


def test_list_types_for_staff_has_approved_and_drafts(env, ai):
    s1 = login("s1")
    post_type(s1)
    got = s1.get("/api/track/types").json()
    assert {t["status"] for t in got} == {"approved", "draft"}
    assert login("r1").get("/api/track/types").status_code == 403


# ---- Task 5: upload and screening ----
DOC_STEPS = [{"title": "Submit", "documents": ["Form A", "Form B"], "page": 1, "unsure": False},
             {"title": "Review", "documents": [], "page": 2, "unsure": False}]
FIND = json.dumps([{"kind": "missing", "text": "Budget empty"}])


class CountingLLM:
    def __init__(self, reply):
        self.reply, self.n = reply, 0

    def __call__(self, messages):
        self.n += 1
        return self.reply


@pytest.fixture
def up(tmp_path, monkeypatch):
    tk = Tracker(tmp_path / "t.db")
    monkeypatch.setattr(state, "get_tracker", lambda: tk)
    monkeypatch.setattr(tracker_api, "UPLOAD_DIR", tmp_path / "uploads")
    llm = CountingLLM(FIND)
    monkeypatch.setattr(tracker_api, "llm", llm)
    v = tk.create_type("CMU", DOC_STEPS, "cmu.pdf")
    tk.approve(v)
    sid = tk.create_submission("S", v, ["r1"], "s1")
    return tk, sid, llm


def put(client, sid, doc="Form A", data=None, name="a.pdf"):
    return client.post(f"/api/track/submissions/{sid}/uploads", data={"doc_name": doc},
                       files={"file": (name, data if data is not None else pdf_bytes(), "application/pdf")})


def test_upload_returns_findings_and_screened(up):
    _, sid, _ = up
    r = put(login("r1"), sid)
    assert r.status_code == 200 and r.json()["status"] == "screened" and r.json()["findings"][0]["kind"] == "missing"


def test_scanned_pdf_is_cannot_check_without_llm_call(up):
    import pymupdf
    doc = pymupdf.open()
    doc.new_page()  # no text layer
    _, sid, llm = up
    r = put(login("r1"), sid, data=doc.tobytes())
    assert r.json()["status"] == "cannot_check" and llm.n == 0
    assert login("r1").post(f"/api/track/uploads/{r.json()['upload_id']}/send").status_code == 200


def test_llm_failure_is_cannot_check_still_sendable(up, monkeypatch):
    _, sid, _ = up
    monkeypatch.setattr(tracker_api, "llm", CountingLLM("garbage"))
    r = put(login("r1"), sid)
    assert r.json()["status"] == "cannot_check"
    assert login("r1").post(f"/api/track/uploads/{r.json()['upload_id']}/send").json()["status"] == "sent"


def test_send_with_findings_allowed(up):
    tk, sid, _ = up
    r = login("r1")
    uid = put(r, sid).json()["upload_id"]
    assert r.post(f"/api/track/uploads/{uid}/send").status_code == 200
    assert tk.get_upload(uid)["status"] == "sent"


def test_upload_to_foreign_submission_404(up):
    _, sid, _ = up
    assert put(login("r2"), sid).status_code == 404


def test_foreign_researcher_cannot_send_someone_elses_upload(up):
    _, sid, _ = up
    uid = put(login("r1"), sid).json()["upload_id"]
    assert login("r2").post(f"/api/track/uploads/{uid}/send").status_code == 404


def test_only_staff_in_charge_may_upload_for_researcher_and_unknown_doc_name_400(up):
    _, sid, _ = up
    assert put(login("s2"), sid).status_code == 404
    assert put(login("s1"), sid).status_code == 200
    assert put(login("r1"), sid, doc="Nope").status_code == 400


def test_upload_rejected_when_submission_completed(up):
    tk, sid, _ = up
    tk.move_step(sid, "s1", 2)
    assert put(login("r1"), sid).status_code == 400


def test_reupload_replaces_latest_not_history(up):
    tk, sid, _ = up
    r = login("r1")
    put(r, sid)
    u2 = put(r, sid).json()["upload_id"]
    assert tk.latest_uploads(sid, 0)["Form A"]["id"] == u2


def test_hostile_upload_rejected_and_nothing_written(up, tmp_path):
    _, sid, _ = up
    assert put(login("r1"), sid, name="x.exe").status_code == 400
    assert not (tmp_path / "uploads").exists() or not [p for p in (tmp_path / "uploads").rglob("*") if p.is_file()]


# ---- Task 6: review ----
def review(client, uid, decision="approve", dismissed=(), note=""):
    return client.post(f"/api/track/uploads/{uid}/review", json={"decision": decision, "dismissed": list(dismissed), "note": note})


def sent_upload(sid, doc="Form A"):
    r = login("r1")
    uid = put(r, sid, doc=doc).json()["upload_id"]
    r.post(f"/api/track/uploads/{uid}/send")
    return uid


def test_review_queue_and_approve_advances(up):
    tk, sid, _ = up
    a, b = sent_upload(sid, "Form A"), sent_upload(sid, "Form B")
    s1 = login("s1")
    q = s1.get("/api/track/review-queue").json()
    assert {x["id"] for x in q} == {a, b} and "path" not in q[0]
    assert review(s1, a).json() == {"advanced": False}
    assert review(s1, b).json() == {"advanced": True}
    assert tk.get_submission(sid, "s1", "staff")["current_step"] == 1


def test_return_shows_note_to_researcher(up):
    _, sid, _ = up
    uid = sent_upload(sid)
    review(login("s1"), uid, "return", note="fix budget")
    docs = login("r1").get(f"/api/track/submissions/{sid}").json()["uploads"]
    assert docs[0]["status"] == "returned" and docs[0]["note"] == "fix budget" and "path" not in docs[0]


def test_review_permissions_and_errors(up):
    _, sid, _ = up
    uid = sent_upload(sid)
    assert review(login("r1"), uid).status_code == 403
    assert login("r1").get("/api/track/review-queue").status_code == 403
    assert review(login("s2"), uid).status_code == 403
    assert review(login("s1"), 999).status_code == 404
    assert review(login("s1"), uid, "maybe").status_code == 400
    assert review(login("s1"), uid).status_code == 200
    assert review(login("s1"), uid).status_code == 400  # already reviewed


def test_uploaded_file_download_is_limited_to_staff_and_owners(up):
    _, sid, _ = up
    uid = sent_upload(sid)
    assert login("s1").get(f"/api/track/uploads/{uid}/file").status_code == 200
    assert login("r1").get(f"/api/track/uploads/{uid}/file").status_code == 200
    assert login("r2").get(f"/api/track/uploads/{uid}/file").status_code == 404
    assert TestClient(server.app).get(f"/api/track/uploads/{uid}/file").status_code == 401


# ---- Task 7: page ----
def test_track_page_and_assets_served():
    c = TestClient(server.app)
    r = c.get("/")
    assert r.status_code == 200 and "home.js" in r.text
    assert c.get("/static/home.js").status_code == 200 and c.get("/static/home.css").status_code == 200


# ---- Final review fixes ----
def test_corrupt_type_document_is_422_and_leaves_no_file(env, ai):
    r = post_type(login("s1"), data=b"%PDF-1.4 this is not a pdf")
    assert r.status_code == 422
    assert not [p for p in ai.rglob("*") if p.is_file()]


def test_scanned_type_document_is_422_without_llm_call(env, ai, monkeypatch):
    import pymupdf
    doc = pymupdf.open()
    doc.new_page()
    calls = CountingLLM(GOOD)
    monkeypatch.setattr(tracker_api, "llm", calls)
    assert post_type(login("s1"), data=doc.tobytes()).status_code == 422 and calls.n == 0


def test_malformed_steps_put_is_400(env, ai):
    s1 = login("s1")
    vid = post_type(s1).json()["version_id"]
    for bad in ([], [{"title": "x"}], [{"documents": []}]):
        assert s1.put(f"/api/track/versions/{vid}", json={"steps": bad}).status_code == 400


def test_reupload_blocked_while_sent_or_approved(up):
    tk, sid, _ = up
    r = login("r1")
    uid = put(r, sid).json()["upload_id"]
    r.post(f"/api/track/uploads/{uid}/send")
    assert put(r, sid).status_code == 400  # under staff review
    review(login("s1"), uid)
    assert put(r, sid).status_code == 400  # approved: cannot be silently replaced
    assert tk.latest_uploads(sid, 0)["Form A"]["id"] == uid


def test_send_twice_is_400(up):
    _, sid, _ = up
    r = login("r1")
    uid = put(r, sid).json()["upload_id"]
    assert r.post(f"/api/track/uploads/{uid}/send").status_code == 200
    assert r.post(f"/api/track/uploads/{uid}/send").status_code == 400


def test_blank_type_name_is_made_by_the_ai_from_the_document(ai, monkeypatch):
    monkeypatch.setattr(tracker_api, "llm", lambda m: "ทุนวิจัยตัวอย่าง" if "ตั้งชื่อ" in m[0]["content"] else GOOD)
    s1 = login("s1")
    r = s1.post("/api/track/types", data={"name": ""}, files={"file": ("แบบ (ลงนามแล้ว).pdf", pdf_bytes(), "application/pdf")})
    assert r.status_code == 200 and r.json()["name"] == "ทุนวิจัยตัวอย่าง"
    assert any(t["type_name"] == "ทุนวิจัยตัวอย่าง" for t in s1.get("/api/track/types").json())


def test_blank_type_name_falls_back_to_a_clean_file_name(ai, monkeypatch):
    def llm(m):
        if "ตั้งชื่อ" in m[0]["content"]:
            raise RuntimeError("model down")
        return GOOD
    monkeypatch.setattr(tracker_api, "llm", llm)
    r = login("s1").post("/api/track/types", data={"name": ""}, files={"file": ("แบบรายงาน_สถานะ (ลงนามแล้ว).pdf", pdf_bytes(), "application/pdf")})
    assert r.status_code == 200 and r.json()["name"] == "แบบรายงาน สถานะ"


def test_a_type_can_be_made_by_hand_without_a_file(tmp_path, monkeypatch):
    tk = Tracker(tmp_path / "t.db")
    monkeypatch.setattr(state, "get_tracker", lambda: tk)
    s = login("s1")
    assert s.post("/api/track/types", data={"name": ""}).status_code == 400  # no file and no name
    out = s.post("/api/track/types", data={"name": "ขอลา"})
    assert out.status_code == 200
    vid = out.json()["version_id"]
    assert tk.get_version(vid)["status"] == "draft" and tk.get_version(vid)["type_name"] == "ขอลา" and tk.get_version(vid)["steps"][0]["documents"] == []
    assert s.put(f"/api/track/versions/{vid}", json={"steps": [{"title": "ยื่นใบลา", "documents": ["ใบลา"]}]}).status_code == 200
    assert s.post(f"/api/track/versions/{vid}/redraft").status_code == 400  # nothing for the AI to read
    assert s.delete(f"/api/track/versions/{vid}").status_code == 200  # no file to remove, and no crash on the empty path


def _with_formats(tk, formats):
    steps = [{"title": "Submit", "documents": ["Form A", "Form B"], "page": None, "unsure": False, "formats": formats}, DOC_STEPS[1]]
    v = tk.create_type("Fmt", steps, "f.pdf")
    tk.approve(v)
    return tk.create_submission("S2", v, ["r1"], "s1")


def test_a_document_accepts_only_the_formats_staff_chose(up):
    tk, _, _ = up
    sid = _with_formats(tk, {"Form A": ["pdf"], "Form B": ["xlsx", "image"]})
    r = login("r1")
    assert put(r, sid, "Form A", name="a.docx", data=b"x").status_code == 400  # Word not allowed here
    assert put(r, sid, "Form A", name="a.pdf").status_code == 200
    assert put(r, sid, "Form B", name="b.pdf").status_code == 400
    assert put(r, sid, "Form B", name="photo.JPG", data=b"\xff\xd8\xff").json()["status"] == "cannot_check"  # accepted, but the AI cannot read an image


def test_without_a_setting_pdf_and_word_are_accepted_as_before(up):
    _, sid, _ = up
    r = login("r1")
    assert put(r, sid, name="a.docx", data=b"x").status_code in (200,)  # unreadable bytes only mean cannot_check
    assert put(r, sid, name="a.xlsx", data=b"x").status_code == 400


def test_bad_format_settings_are_refused(up):
    tk, _, _ = up
    s = login("s1")
    v = tk.create_type("Bad", [{"title": "S", "documents": ["Doc"]}], "")
    ok = lambda f: s.put(f"/api/track/versions/{v}", json={"steps": [{"title": "S", "documents": ["Doc"], "formats": f}]}).status_code
    assert ok({"Doc": ["pdf", "image"]}) == 200
    assert ok({"Doc": []}) == 400 and ok({"Doc": ["exe"]}) == 400 and ok({"Other": ["pdf"]}) == 400 and ok(["pdf"]) == 400
