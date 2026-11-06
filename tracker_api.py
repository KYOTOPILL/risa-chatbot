"""Tracking dashboard API: mock login, submissions, step moves. Rules live in tracker.py; this only maps users and HTTP."""
from dataclasses import dataclass

import re
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

import state
from config import MAX_UPLOAD_BYTES, MOCK_USERS, UPLOAD_DIR
from extract import extract_pages, extract_text
from rag import chat as llm
from steps_ai import draft_steps, find_template, screen_document

router = APIRouter(prefix="/api/track")


@dataclass
class User:
    id: str
    name: str
    role: str


def current_user(request: Request) -> User:
    # ponytail: plain uid cookie, anyone can forge it; replaced by CMU email login before real use
    uid = request.cookies.get("uid")
    if uid not in MOCK_USERS:
        raise HTTPException(401, "login required")
    return User(uid, **MOCK_USERS[uid])


def require_staff(user: User = Depends(current_user)) -> User:
    if user.role != "staff":
        raise HTTPException(403, "staff only")
    return user


class LoginIn(BaseModel):
    user_id: str


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
def mock_users():
    return [{"id": i, **u} for i, u in MOCK_USERS.items()]


@router.post("/login")
def login(body: LoginIn, response: Response):
    if body.user_id not in MOCK_USERS:
        raise HTTPException(401, "unknown user")
    response.set_cookie("uid", body.user_id, httponly=True, samesite="lax")
    return {"id": body.user_id, **MOCK_USERS[body.user_id]}


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
    return sub


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


def _save_upload(file: UploadFile, subdir: str) -> Path:
    """Checks type and size, then stores under UPLOAD_DIR/subdir with a sanitized, unique name."""
    name = re.sub(r"[^\w.\-]", "_", Path(file.filename or "").name)  # drops any directory part
    if Path(name).suffix.lower() not in UPLOAD_EXTS:
        raise HTTPException(400, "only .pdf and .docx files are accepted")
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
    if doc_name not in step["documents"]:
        raise HTTPException(400, "not a document of the current step")
    if any(u["doc_name"] == doc_name and u["status"] in ("sent", "approved") for u in sub["uploads"]):
        raise HTTPException(400, "document is already with staff or approved")
    path = _save_upload(file, f"submissions/{sid}")
    findings, status = None, "cannot_check"  # a failed check never blocks sending
    try:
        text = extract_text(path)
        if text:
            tpl = find_template(doc_name)
            findings = screen_document(text, step, doc_name, extract_text(tpl) if tpl else None, llm=llm)
            status = "screened"
    except Exception:  # unreadable file or bad model output: report "cannot check", keep the upload
        findings, status = None, "cannot_check"
    uid = state.get_tracker().add_upload(sid, n, doc_name, file.filename or path.name, str(path), findings, status)
    return {"upload_id": uid, "status": status, "findings": findings or []}


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
    return {k: v for k, v in up.items() if k != "path"}  # server file paths stay on the server


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
    return FileResponse(up["path"], filename=up["filename"])
