"""Tracking dashboard API: mock login, submissions, step moves. Rules live in tracker.py; this only maps users and HTTP."""
import json
import re
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

import state
from auth import User, authenticate, current_user, require_staff, session_value
from config import MAX_UPLOAD_BYTES, MOCK_USERS, UPLOAD_DIR
from extract import extract_pages, extract_text
from rag import chat as llm
from forms_ai import draft_form
from steps_ai import draft_steps, screen_document

router = APIRouter(prefix="/api/track")


class LoginIn(BaseModel):
    username: str
    password: str


class SubmissionIn(BaseModel):
    title: str
    version_id: int
    researcher_ids: list[str]
    staff_id: str


class StepsIn(BaseModel):
    steps: list[dict]


class ReviewIn(BaseModel):
    decision: str
    dismissed: list[int] = []
    note: str = ""


class MoveIn(BaseModel):
    to_step: int
    note: str = ""


@router.get("/mock-users")
def mock_users(_user: User = Depends(current_user)):
    return [{"id": i, "name": u["name"], "role": u["role"]} for i, u in MOCK_USERS.items()]


@router.post("/login")
def login(body: LoginIn, response: Response):
    uid = authenticate(body.username, body.password)
    if uid is None:
        raise HTTPException(401, "wrong username or password")
    response.set_cookie("uid", session_value(uid), httponly=True, samesite="lax")
    return {"id": uid, "name": MOCK_USERS[uid]["name"], "role": MOCK_USERS[uid]["role"]}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("uid")
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "name": user.name, "role": user.role}


@router.get("/submissions")
def submissions(user: User = Depends(current_user)):
    return state.get_tracker().list_submissions(user.id, user.role)


@router.get("/submissions/{sid}")
def submission(sid: int, user: User = Depends(current_user)):
    sub = state.get_tracker().get_submission(sid, user.id, user.role)
    if sub is None:  # missing and not-yours look the same
        raise HTTPException(404, "not found")
    forms = {}
    for st in sub["steps"]:
        for d in st["documents"]:
            f = state.get_tracker().get_form(sub["type_id"], d)
            if f and f["status"] == "approved":
                forms[d] = {"title": f["title"], "fields": f["fields"]}
    return {**sub, "forms": forms, "uploads": [_public(u) for u in sub["uploads"]]}


@router.post("/submissions")
def create_submission(body: SubmissionIn, _: User = Depends(require_staff)):
    people = [*body.researcher_ids, body.staff_id]
    if any(p not in MOCK_USERS for p in people) or MOCK_USERS[body.staff_id]["role"] != "staff" \
            or any(MOCK_USERS[r]["role"] != "researcher" for r in body.researcher_ids):
        raise HTTPException(400, "unknown user or wrong role")
    try:
        return {"id": state.get_tracker().create_submission(body.title, body.version_id, body.researcher_ids, body.staff_id)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/submissions/{sid}/move")
def move(sid: int, body: MoveIn, user: User = Depends(require_staff)):
    try:
        state.get_tracker().move_step(sid, user.id, body.to_step, body.note)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


UPLOAD_EXTS = {".pdf", ".docx"}


def _save_upload(file: UploadFile, subdir: str, exts=None) -> Path:
    """Checks type and size, then stores under UPLOAD_DIR/subdir with a sanitized, unique name."""
    name = re.sub(r"[^\w.\-]", "_", Path(file.filename or "").name)  # drops any directory part
    if Path(name).suffix.lower() not in (exts or UPLOAD_EXTS):
        raise HTTPException(400, "only " + ", ".join(sorted(exts or UPLOAD_EXTS)) + " files are accepted")
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "file too large")
    dest = UPLOAD_DIR / subdir
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / f"{secrets.token_hex(4)}_{name}"
    path.write_bytes(data)
    return path


def _draft(path: Path) -> list[dict]:
    try:
        pages = extract_pages(path)
        if not any(pages):
            raise ValueError("document has no text (scanned PDF?)")
        return draft_steps(pages, llm=llm)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception:  # corrupt or unreadable file
        raise HTTPException(422, "cannot read this document")


@router.get("/types")
def types(_: User = Depends(require_staff)):
    tk = state.get_tracker()
    return tk.list_types() + tk.list_drafts()


@router.post("/types")
def create_type(name: str = Form(...), file: UploadFile = File(...), _: User = Depends(require_staff)):
    path = _save_upload(file, "types")
    try:
        steps = _draft(path)
    except HTTPException:
        path.unlink(missing_ok=True)
        raise
    return {"version_id": state.get_tracker().create_type(name, steps, str(path)), "steps": steps}


class PublishIn(BaseModel):
    owner_id: str | None = None


@router.post("/types/{type_id}/publish")
def publish(type_id: int, body: PublishIn, user: User = Depends(require_staff)):
    """Open a type for researchers. The owner (default: whoever publishes) is staff in charge of every request started from it."""
    tk = state.get_tracker()
    owner = body.owner_id or user.id
    if owner not in MOCK_USERS or MOCK_USERS[owner]["role"] != "staff":
        raise HTTPException(400, "the owner must be a staff member")
    if not any(v["type_id"] == type_id for v in tk.list_types()):
        if any(v["type_id"] == type_id for v in tk.list_drafts()):
            raise HTTPException(400, "approve the type first")
        raise HTTPException(404, "no such type")
    tk.set_type_open(type_id, True, owner)
    return {"ok": True, "owner_id": owner}


@router.post("/types/{type_id}/close")
def close(type_id: int, _: User = Depends(require_staff)):
    state.get_tracker().set_type_open(type_id, False)
    return {"ok": True}


@router.get("/open-types")
def open_types(_: User = Depends(current_user)):
    return [{"type_id": v["type_id"], "type_name": v["type_name"], "owner_id": v["owner_id"], "owner_name": MOCK_USERS.get(v["owner_id"], {}).get("name", ""),
             "steps": [{"title": st["title"], "documents": st["documents"]} for st in v["steps"]]} for v in state.get_tracker().list_open_types()]


@router.post("/open-types/{type_id}/start")
def start_request(type_id: int, user: User = Depends(current_user)):
    if user.role != "researcher":
        raise HTTPException(403, "researchers only")
    tk = state.get_tracker()
    v = next((v for v in tk.list_open_types() if v["type_id"] == type_id), None)
    if v is None:
        raise HTTPException(404, "this post is not open")
    mine = next((s for s in tk.list_submissions(user.id, "researcher") if s["type_id"] == type_id), None)
    if mine:  # one request per post: go back to it and edit instead of starting a copy
        return {"id": mine["id"]}
    return {"id": tk.create_submission(f"{v['type_name']} - {user.name}", v["id"], [user.id], v["owner_id"])}


@router.post("/types/{type_id}/versions")
def new_version(type_id: int, file: UploadFile = File(...), _: User = Depends(require_staff)):
    path = _save_upload(file, "types")
    try:
        steps = _draft(path)
    except HTTPException:
        path.unlink(missing_ok=True)
        raise
    return {"version_id": state.get_tracker().new_version(type_id, steps, str(path)), "steps": steps}


@router.put("/versions/{vid}")
def edit_version(vid: int, body: StepsIn, _: User = Depends(require_staff)):
    try:
        state.get_tracker().update_draft(vid, body.steps)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@router.post("/versions/{vid}/redraft")
def redraft(vid: int, _: User = Depends(require_staff)):
    tk = state.get_tracker()
    v = tk.get_version(vid)
    if not v or v["status"] != "draft":
        raise HTTPException(400, "not an editable draft")
    steps = _draft(Path(v["source_file"]))
    tk.update_draft(vid, steps)
    return {"steps": steps}


@router.post("/versions/{vid}/approve")
def approve(vid: int, _: User = Depends(require_staff)):
    if not state.get_tracker().get_version(vid):
        raise HTTPException(404, "not found")
    state.get_tracker().approve(vid)
    return {"ok": True}


def _own_submission(sid: int, user: User) -> dict:
    """Researcher's own submission; anything else is a 404."""
    if user.role != "researcher":
        raise HTTPException(403, "researchers only")
    sub = state.get_tracker().get_submission(sid, user.id, "researcher")
    if sub is None:
        raise HTTPException(404, "not found")
    return sub


@router.post("/submissions/{sid}/uploads")
def upload(sid: int, doc_name: str = Form(...), file: UploadFile = File(...), user: User = Depends(current_user)):
    sub = _own_submission(sid, user)
    n = sub["current_step"]
    if n >= sub["step_count"]:
        raise HTTPException(400, "submission is already complete")
    step = sub["steps"][n]
    _check_slot(sub, step, doc_name)
    if _approved_form(sub["type_id"], doc_name):
        raise HTTPException(400, "this document is filled in on the website, not uploaded")
    path = _save_upload(file, f"submissions/{sid}")
    findings, status = None, "cannot_check"  # a failed check never blocks sending
    try:
        text = extract_text(path)
        if text:
            findings = screen_document(text, step, doc_name, None, llm=llm)
            status = "screened"
    except Exception:  # unreadable file or bad model output: report "cannot check", keep the upload
        findings, status = None, "cannot_check"
    uid = state.get_tracker().add_upload(sid, n, doc_name, file.filename or path.name, str(path), findings, status)
    return {"upload_id": uid, "status": status, "findings": findings or []}


def _doc_step(sub_or_version: dict, doc: str) -> dict | None:
    return next((s for s in sub_or_version["steps"] if doc in s["documents"]), None)


def _approved_form(type_id: int, doc: str) -> dict | None:
    f = state.get_tracker().get_form(type_id, doc)
    return f if f and f["status"] == "approved" else None


def _check_slot(sub: dict, step: dict, doc_name: str) -> None:
    if doc_name not in step["documents"]:
        raise HTTPException(400, "not a document of the current step")
    if any(u["doc_name"] == doc_name and u["status"] in ("sent", "approved") for u in sub["uploads"]):
        raise HTTPException(400, "document is already with staff or approved")


ATTACH_EXTS = UPLOAD_EXTS | {".jpg", ".jpeg", ".png"}  # a scanned receipt or signed page is often a photo
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _answers(form: dict, raw: dict, files: dict, prev: list, sid: int) -> list:
    """Checks the researcher's answers against the approved form. Returns a snapshot (label and type included) so later form edits never change what staff review."""
    old = {a["key"]: a["value"] for a in prev}
    out = []
    for f in form["fields"]:
        k, kind, v = f["key"], f["type"], raw.get(f["key"])
        if kind == "file":
            if k in files:
                path = _save_upload(files[k], f"submissions/{sid}", ATTACH_EXTS)
                v = {"name": files[k].filename or path.name, "path": str(path)}
            else:
                v = old.get(k) if isinstance(old.get(k), dict) else None
        else:
            v = v.strip() if isinstance(v, str) else ("" if v is None else str(v))
            if v and kind == "number":
                try:
                    float(v)
                except ValueError:
                    raise HTTPException(400, f"{f['label']}: ต้องเป็นตัวเลข")
            if v and kind == "date" and not DATE_RE.match(v):
                raise HTTPException(400, f"{f['label']}: รูปแบบวันที่ไม่ถูกต้อง")
            if v and kind == "choice" and v not in f["options"]:
                raise HTTPException(400, f"{f['label']}: เลือกได้เฉพาะตัวเลือกที่กำหนด")
        if f["required"] and not v:
            raise HTTPException(400, f"กรุณากรอก: {f['label']}")
        out.append({"key": k, "label": f["label"], "type": kind, "value": v})
    return out


def _answers_text(title: str, answers: list) -> str:
    lines = [title]
    for a in answers:
        v = a["value"]
        if isinstance(v, dict):
            try:
                body = extract_text(Path(v["path"]))[:2000]
            except Exception:
                body = ""
            v = f"(ไฟล์แนบ: {v['name']})" + (f"\n{body}" if body else "")
        lines.append(f"{a['label']}: {v or '(ว่าง)'}")
    return "\n".join(lines)


@router.post("/submissions/{sid}/forms")
def submit_form(sid: int, doc_name: str = Form(...), answers: str = Form("{}"), file_keys: list[str] = Form([]), files: list[UploadFile] = File([]),
                user: User = Depends(current_user)):
    """Researcher fills the online form of a document. Saving again replaces the earlier answers until the document is sent."""
    sub = _own_submission(sid, user)
    n = sub["current_step"]
    if n >= sub["step_count"]:
        raise HTTPException(400, "submission is already complete")
    step = sub["steps"][n]
    _check_slot(sub, step, doc_name)
    form = _approved_form(sub["type_id"], doc_name)
    if form is None:
        raise HTTPException(400, "this document has no online form")
    try:
        raw = json.loads(answers)
        assert isinstance(raw, dict)
    except Exception:
        raise HTTPException(400, "answers must be a JSON object")
    prev = next((u["answers"] for u in sorted(sub["uploads"], key=lambda u: -u["id"]) if u["doc_name"] == doc_name), [])
    snap = _answers(form, raw, dict(zip(file_keys, files)), prev, sid)
    findings, status = None, "cannot_check"
    try:
        findings = screen_document(_answers_text(form["title"], snap), step, doc_name, None, llm=llm)
        status = "screened"
    except Exception:
        findings, status = None, "cannot_check"
    uid = state.get_tracker().add_upload(sid, n, doc_name, form["title"], "", findings, status, snap)
    return {"upload_id": uid, "status": status, "findings": findings or []}


# ---- staff: draft, edit, approve the blank form of each document of a type ----
class FormRef(BaseModel):
    doc_name: str


class FormIn(FormRef):
    title: str
    fields: list[dict]


def _type_version(type_id: int) -> dict:
    tk = state.get_tracker()
    v = next((v for v in tk.list_types() + tk.list_drafts() if v["type_id"] == type_id), None)
    if v is None:
        raise HTTPException(404, "no such type")
    return v


def _known_doc(type_id: int, doc: str) -> tuple[dict, dict]:
    v = _type_version(type_id)
    step = _doc_step(v, doc)
    if step is None:
        raise HTTPException(400, "not a document of this type")
    return v, step


@router.get("/types/{type_id}/forms")
def list_forms(type_id: int, _: User = Depends(require_staff)):
    return state.get_tracker().list_forms(type_id)


@router.post("/types/{type_id}/forms/draft")
def draft_type_form(type_id: int, body: FormRef, _: User = Depends(require_staff)):
    v, step = _known_doc(type_id, body.doc_name)
    try:
        form = draft_form(body.doc_name, step, v["type_name"], Path(v["source_file"]) if v.get("source_file") else None, llm=llm)
    except Exception as e:  # bad model output or model unreachable: nothing is saved
        raise HTTPException(502, f"could not draft the form: {e}")
    state.get_tracker().put_form(type_id, body.doc_name, form["title"], form["fields"])
    return {"doc_name": body.doc_name, "status": "draft", **form}


@router.put("/types/{type_id}/forms")
def edit_form(type_id: int, body: FormIn, _: User = Depends(require_staff)):
    _known_doc(type_id, body.doc_name)
    tk = state.get_tracker()
    old = tk.get_form(type_id, body.doc_name)
    try:  # an approved form stays approved after an edit: the editor is staff
        tk.put_form(type_id, body.doc_name, body.title, body.fields, old["status"] if old else "draft")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@router.post("/types/{type_id}/forms/approve")
def approve_form(type_id: int, body: FormRef, _: User = Depends(require_staff)):
    if not state.get_tracker().approve_form(type_id, body.doc_name):
        raise HTTPException(404, "draft a form first")
    return {"ok": True}


@router.post("/uploads/{uid}/send")
def send_upload(uid: int, user: User = Depends(current_user)):
    tk = state.get_tracker()
    up = tk.get_upload(uid)
    if up is None:
        raise HTTPException(404, "not found")
    _own_submission(up["submission_id"], user)
    try:
        tk.send_upload(uid)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"status": "sent"}


def _public(up: dict) -> dict:
    """Server file paths stay on the server; a file answer keeps only its name."""
    answers = [{**a, "value": {"name": a["value"]["name"]}} if isinstance(a["value"], dict) else a for a in up["answers"]]
    return {**{k: v for k, v in up.items() if k != "path"}, "answers": answers}


@router.get("/review-queue")
def review_queue(_: User = Depends(require_staff)):
    return [_public(u) for u in state.get_tracker().review_queue()]


@router.post("/uploads/{uid}/review")
def review(uid: int, body: ReviewIn, user: User = Depends(require_staff)):
    tk = state.get_tracker()
    if tk.get_upload(uid) is None:
        raise HTTPException(404, "not found")
    try:
        return {"advanced": tk.review_upload(uid, user.id, body.decision, body.dismissed, body.note)}
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/uploads/{uid}/file")
def upload_file(uid: int, user: User = Depends(current_user)):
    tk = state.get_tracker()
    up = tk.get_upload(uid)
    if up is None or tk.get_submission(up["submission_id"], user.id, user.role) is None:
        raise HTTPException(404, "not found")
    if not up["path"]:
        raise HTTPException(404, "this document is a form, not a file")
    return FileResponse(up["path"], filename=up["filename"])


@router.get("/uploads/{uid}/answer-file")
def answer_file(uid: int, key: str, user: User = Depends(current_user)):
    """A file attached inside a filled form. Same access as the upload itself."""
    tk = state.get_tracker()
    up = tk.get_upload(uid)
    if up is None or tk.get_submission(up["submission_id"], user.id, user.role) is None:
        raise HTTPException(404, "not found")
    a = next((a for a in up["answers"] if a["key"] == key and isinstance(a["value"], dict)), None)
    if a is None:
        raise HTTPException(404, "not found")
    return FileResponse(a["value"]["path"], filename=a["value"]["name"])
