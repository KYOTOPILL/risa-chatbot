"""Tracking dashboard API: mock login, submissions, step moves. Rules live in tracker.py; this only maps users and HTTP."""
import json
import queue
import re
import secrets
import threading
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

import state
from app.core.auth import User, authenticate, current_user, login_allowed, login_failed, require_staff, session_value
from app.core.config import COOKIE_SECURE, MAX_UPLOAD_BYTES, MOCK_USERS, SESSION_TTL, UPLOAD_DIR
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
def login(body: LoginIn, request: Request, response: Response):
    key = f"{request.client.host if request.client else ''}|{body.username.lower()}"
    if not login_allowed(key):
        raise HTTPException(429, "too many wrong tries, wait a few minutes")
    uid = authenticate(body.username, body.password)
    if uid is None:
        login_failed(key)
        raise HTTPException(401, "wrong username or password")
    response.set_cookie("uid", session_value(uid), httponly=True, samesite="lax", secure=COOKIE_SECURE, max_age=SESSION_TTL)
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
def create_submission(body: SubmissionIn, user: User = Depends(require_staff)):
    people = [*body.researcher_ids, body.staff_id]
    if any(p not in MOCK_USERS for p in people) or MOCK_USERS[body.staff_id]["role"] != "staff" \
            or any(MOCK_USERS[r]["role"] != "researcher" for r in body.researcher_ids):
        raise HTTPException(400, "unknown user or wrong role")
    try:
        return {"id": state.get_tracker().create_submission(body.title, body.version_id, body.researcher_ids, body.staff_id, user.id)}
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


@router.get("/notifications")
def notifications(user: User = Depends(current_user)):
    return state.get_tracker().notifications(user.id)


@router.post("/notifications/seen")
def notifications_seen(user: User = Depends(current_user)):
    state.get_tracker().mark_seen(user.id)
    return {"ok": True}


class StaffIn(BaseModel):
    staff_id: str


@router.post("/submissions/{sid}/staff")
def reassign(sid: int, body: StaffIn, user: User = Depends(require_staff)):
    """Any staff member may hand a request over, so one person being away never strands it."""
    if body.staff_id not in MOCK_USERS or MOCK_USERS[body.staff_id]["role"] != "staff":
        raise HTTPException(400, "the person in charge must be a staff member")
    try:
        state.get_tracker().set_staff(sid, body.staff_id, user.id)
    except ValueError:
        raise HTTPException(404, "not found")
    return {"ok": True}


MAX_DIR_BYTES = 200 * 1024 * 1024  # all files of one request
MAX_FORM_FILES = 10
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
    if subdir != "types" and sum(p.stat().st_size for p in dest.iterdir()) + len(data) > MAX_DIR_BYTES:
        raise HTTPException(413, "too many files for this request")
    path = dest / f"{secrets.token_hex(4)}_{name}"
    path.write_bytes(data)
    return path


def _progress(request: Request, work):
    """Runs work(say). A client that sends `Accept: application/x-ndjson` gets JSON lines while it runs: {"status": text} for each thing the server is doing,
    then {"done": result} or {"error": text}. Anyone else gets the plain JSON result, so scripts and tests are unchanged."""
    if "application/x-ndjson" not in request.headers.get("accept", ""):
        return work(lambda text: None)
    q: queue.Queue = queue.Queue()

    def run():
        try:
            q.put(("done", work(lambda text: q.put(("status", text)))))
        except HTTPException as e:
            q.put(("error", e.detail if isinstance(e.detail, str) else "ผิดพลาด"))
        except Exception:
            q.put(("error", "เกิดข้อผิดพลาดที่เซิร์ฟเวอร์ กรุณาลองใหม่"))

    def events():
        threading.Thread(target=run, daemon=True).start()
        while True:
            kind, val = q.get()
            yield json.dumps({kind: val}, ensure_ascii=False) + "\n"
            if kind != "status":
                return

    return StreamingResponse(events(), media_type="application/x-ndjson", headers={"X-Accel-Buffering": "no"})


def _type_name(path: Path, filename: str) -> str:
    """A short name for a new type: the AI reads the start of the guide; if it gives nothing, the file name without its extension and brackets."""
    stem = re.sub(r"\s*[(\[].*?[)\]]", "", Path(filename).stem).replace("_", " ").strip() or "ประเภทงานใหม่"
    try:
        text = " ".join(extract_pages(path))[:1500]
        out = llm([{"role": "user", "content": "ตั้งชื่อประเภทงานสั้นๆ ไม่เกิน 60 ตัวอักษร (เช่น ทุน CMU Presidential, ขอเบิกค่าเดินทาง) จากเอกสารนี้ "
                    "ตอบเฉพาะชื่อ ไม่ต้องมีเครื่องหมายคำพูดหรือคำอธิบาย ไม่ใส่นามสกุลไฟล์\n\n" + text}])
        name = out.strip().splitlines()[0].strip(" \"'“”") if out and out.strip() else ""
        return name[:80] or stem
    except Exception:
        return stem


def _draft(path: Path, say=lambda text: None) -> list[dict]:
    try:
        say("กำลังอ่านข้อความจากเอกสาร")
        pages = extract_pages(path)
        if not any(pages):
            raise ValueError("document has no text (scanned PDF?)")
        say(f"อ่านแล้ว {len(pages)} หน้า ({sum(len(p) for p in pages):,} ตัวอักษร) กำลังให้ AI ร่างขั้นตอนและเอกสารที่ต้องส่ง (ประมาณ 10-30 วินาที)")
        steps = draft_steps(pages, llm=llm)
        unsure = sum(1 for st in steps if st["unsure"])
        say(f"AI ร่างได้ {len(steps)} ขั้นตอน" + (f" มี {unsure} ขั้นตอนที่ AI ไม่แน่ใจ ให้ตรวจสอบเป็นพิเศษ" if unsure else ""))
        return steps
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception:  # corrupt or unreadable file
        raise HTTPException(422, "cannot read this document")


@router.get("/types")
def types(_: User = Depends(require_staff)):
    tk = state.get_tracker()
    return tk.list_types() + tk.list_drafts()


@router.post("/types")
def create_type(request: Request, name: str = Form(""), file: UploadFile = File(...), _: User = Depends(require_staff)):
    path = _save_upload(file, "types")

    def work(say):
        try:
            steps = _draft(path, say)
        except HTTPException:
            path.unlink(missing_ok=True)
            raise
        title = name.strip()
        if not title:
            say("AI กำลังตั้งชื่อประเภทงานจากเอกสาร")
            title = _type_name(path, file.filename or "")
        say("กำลังบันทึกฉบับร่าง")
        return {"version_id": state.get_tracker().create_type(title, steps, str(path)), "steps": steps, "name": title}
    return _progress(request, work)


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


def _delete(call, arg: int) -> dict:
    try:
        files = call(arg)
    except KeyError:
        raise HTTPException(404, "not found")
    except ValueError:
        raise HTTPException(409, "มีงานที่ใช้อยู่แล้ว ลบไม่ได้")
    for f in files:
        Path(f).unlink(missing_ok=True)
    return {"ok": True}


@router.delete("/types/{type_id}")
def delete_type(type_id: int, _: User = Depends(require_staff)):
    return _delete(state.get_tracker().delete_type, type_id)


@router.delete("/versions/{vid}")
def delete_version(vid: int, _: User = Depends(require_staff)):
    return _delete(state.get_tracker().delete_version, vid)


# ---- categories: any logged-in user may read the list (researchers group types by it); staff change it ----
class CategoryIn(BaseModel):
    name: str


class OrderIn(BaseModel):
    ids: list[int]


class TypeCategoryIn(BaseModel):
    category_id: int | None = None


def _category(call, *args) -> dict:
    try:
        out = call(*args)
    except KeyError:
        raise HTTPException(404, "not found")
    except ValueError as e:
        raise HTTPException(409 if "not empty" in str(e) or "exists" in str(e) else 400, str(e))
    return {"ok": True, **({"id": out} if isinstance(out, int) else {})}


@router.get("/categories")
def categories(_: User = Depends(current_user)):
    return state.get_tracker().list_categories()


@router.post("/categories")
def add_category(body: CategoryIn, _: User = Depends(require_staff)):
    return _category(state.get_tracker().add_category, body.name)


@router.put("/categories/order")
def order_categories(body: OrderIn, _: User = Depends(require_staff)):
    return _category(state.get_tracker().reorder_categories, body.ids)


@router.put("/categories/{cid}")
def rename_category(cid: int, body: CategoryIn, _: User = Depends(require_staff)):
    return _category(state.get_tracker().rename_category, cid, body.name)


@router.delete("/categories/{cid}")
def delete_category(cid: int, _: User = Depends(require_staff)):
    return _category(state.get_tracker().delete_category, cid)


@router.put("/types/{type_id}/category")
def set_type_category(type_id: int, body: TypeCategoryIn, _: User = Depends(require_staff)):
    return _category(state.get_tracker().set_type_category, type_id, body.category_id)


@router.get("/open-types")
def open_types(_: User = Depends(current_user)):
    return [{"type_id": v["type_id"], "type_name": v["type_name"], "category_id": v["category_id"], "owner_id": v["owner_id"], "owner_name": MOCK_USERS.get(v["owner_id"], {}).get("name", ""),
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
    return {"id": tk.create_submission(f"{v['type_name']} - {user.name}", v["id"], [user.id], v["owner_id"], user.id)}


@router.post("/types/{type_id}/versions")
def new_version(request: Request, type_id: int, file: UploadFile = File(...), _: User = Depends(require_staff)):
    path = _save_upload(file, "types")

    def work(say):
        try:
            steps = _draft(path, say)
        except HTTPException:
            path.unlink(missing_ok=True)
            raise
        say("กำลังบันทึกฉบับร่าง")
        return {"version_id": state.get_tracker().new_version(type_id, steps, str(path)), "steps": steps}
    return _progress(request, work)


@router.put("/versions/{vid}")
def edit_version(vid: int, body: StepsIn, _: User = Depends(require_staff)):
    try:
        state.get_tracker().update_draft(vid, body.steps)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@router.post("/versions/{vid}/redraft")
def redraft(request: Request, vid: int, _: User = Depends(require_staff)):
    tk = state.get_tracker()
    v = tk.get_version(vid)
    if not v or v["status"] != "draft":
        raise HTTPException(400, "not an editable draft")

    def work(say):
        steps = _draft(Path(v["source_file"]), say)
        say("กำลังบันทึกฉบับร่าง")
        tk.update_draft(vid, steps)
        return {"steps": steps}
    return _progress(request, work)


@router.post("/versions/{vid}/approve")
def approve(vid: int, _: User = Depends(require_staff)):
    if not state.get_tracker().get_version(vid):
        raise HTTPException(404, "not found")
    state.get_tracker().approve(vid)
    return {"ok": True}


def _own_submission(sid: int, user: User) -> dict:
    """The researcher's own submission, or one staff in charge may fill in on the researcher's behalf; anything else is a 404."""
    sub = state.get_tracker().get_submission(sid, user.id, user.role)
    if sub is None or (user.role == "staff" and sub["staff_id"] != user.id):
        raise HTTPException(404, "not found")
    return sub


@router.post("/submissions/{sid}/uploads")
def upload(request: Request, sid: int, doc_name: str = Form(...), file: UploadFile = File(...), user: User = Depends(current_user)):
    sub = _own_submission(sid, user)
    n = sub["current_step"]
    if n >= sub["step_count"]:
        raise HTTPException(400, "submission is already complete")
    step = sub["steps"][n]
    _check_slot(sub, step, doc_name)
    if _approved_form(sub["type_id"], doc_name):
        raise HTTPException(400, "this document is filled in on the website, not uploaded")
    path = _save_upload(file, f"submissions/{sid}")

    def work(say):
        findings, status = None, "cannot_check"  # a failed check never blocks sending
        try:
            say("รับไฟล์แล้ว กำลังอ่านข้อความจากไฟล์")
            text = extract_text(path)
            if text:
                say(f"อ่านได้ {len(text):,} ตัวอักษร AI กำลังตรวจสอบเอกสาร (ประมาณ 5-20 วินาที)")
                findings = screen_document(text, step, doc_name, None, llm=llm)
                status = "screened"
            else:
                say("อ่านข้อความจากไฟล์ไม่ได้ (อาจเป็นไฟล์สแกน) จึงข้ามการตรวจสอบโดย AI")
        except Exception:  # unreadable file or bad model output: report "cannot check", keep the upload
            findings, status = None, "cannot_check"
            say("AI ตรวจสอบไม่สำเร็จ บันทึกไฟล์ไว้แล้ว ส่งให้เจ้าหน้าที่ได้")
        uid = state.get_tracker().add_upload(sid, n, doc_name, file.filename or path.name, str(path), findings, status)
        return {"upload_id": uid, "status": status, "findings": findings or []}
    return _progress(request, work)


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


def _answers(form: dict, raw: dict, files: dict, prev: list, sid: int, draft: bool = False) -> list:
    """Checks the researcher's answers against the approved form. Returns a snapshot (label and type included) so later form edits never change what staff review."""
    old = {a["key"]: a["value"] for a in prev}
    out, saved = [], []
    try:
        return _check_answers(form, raw, files, old, sid, draft, out, saved)
    except HTTPException:
        for p in saved:  # a rejected save must not leave its files behind
            p.unlink(missing_ok=True)
        raise


def _check_answers(form, raw, files, old, sid, draft, out, saved) -> list:
    for f in form["fields"]:
        k, kind, v = f["key"], f["type"], raw.get(f["key"])
        if kind == "file":
            if k in files:
                path = _save_upload(files[k], f"submissions/{sid}", ATTACH_EXTS)
                saved.append(path)
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
        if f["required"] and not v and not draft:
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
def submit_form(request: Request, sid: int, doc_name: str = Form(...), answers: str = Form("{}"), draft: bool = Form(False), file_keys: list[str] = Form([]), files: list[UploadFile] = File([]),
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
    if len(files) > MAX_FORM_FILES:
        raise HTTPException(400, "too many files")
    prev = next((u["answers"] for u in sorted(sub["uploads"], key=lambda u: -u["id"]) if u["doc_name"] == doc_name), [])
    snap = _answers(form, raw, dict(zip(file_keys, files)), prev, sid, draft)  # checked and files saved before streaming: the uploads are closed once this handler returns

    if draft:  # a half-filled form is only kept: no AI check, and it cannot be sent until saved in full
        uid = state.get_tracker().add_upload(sid, n, doc_name, form["title"], "", None, "draft", snap)
        return {"upload_id": uid, "status": "draft", "findings": []}

    def work(say):
        findings, status = None, "cannot_check"
        say(f"ตรวจคำตอบครบแล้ว {len(snap)} ช่อง บันทึกไฟล์แนบแล้ว AI กำลังตรวจสอบคำตอบ (ประมาณ 5-20 วินาที)")
        try:
            findings = screen_document(_answers_text(form["title"], snap), step, doc_name, None, llm=llm)
            status = "screened"
            say(f"AI ตรวจสอบเสร็จ พบข้อสังเกต {len(findings)} ข้อ" if findings else "AI ตรวจสอบเสร็จ ไม่พบข้อสังเกต")
        except Exception:
            findings, status = None, "cannot_check"
            say("AI ตรวจสอบไม่สำเร็จ บันทึกคำตอบไว้แล้ว ส่งให้เจ้าหน้าที่ได้")
        uid = state.get_tracker().add_upload(sid, n, doc_name, form["title"], "", findings, status, snap)
        return {"upload_id": uid, "status": status, "findings": findings or []}
    return _progress(request, work)


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
def draft_type_form(request: Request, type_id: int, body: FormRef, _: User = Depends(require_staff)):
    v, step = _known_doc(type_id, body.doc_name)

    def work(say):
        say(f"กำลังอ่านคู่มือของ “{v['type_name']}” และขั้นตอน “{step['title']}”")
        say(f"AI กำลังออกแบบช่องกรอกของ “{body.doc_name}” (ประมาณ 10-30 วินาที)")
        try:
            form = draft_form(body.doc_name, step, v["type_name"], Path(v["source_file"]) if v.get("source_file") else None, llm=llm)
        except Exception as e:  # bad model output or model unreachable: nothing is saved
            raise HTTPException(502, f"could not draft the form: {e}")
        kinds = sorted({f["type"] for f in form["fields"]})
        say(f"AI ร่างได้ {len(form['fields'])} ช่อง ({len(kinds)} ชนิด) กำลังบันทึกฉบับร่าง")
        state.get_tracker().put_form(type_id, body.doc_name, form["title"], form["fields"])
        return {"doc_name": body.doc_name, "status": "draft", **form}
    return _progress(request, work)


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


@router.post("/uploads/{uid}/withdraw")
def withdraw(uid: int, user: User = Depends(current_user)):
    tk = state.get_tracker()
    up = tk.get_upload(uid)
    if up is None:
        raise HTTPException(404, "not found")
    _own_submission(up["submission_id"], user)
    try:
        tk.withdraw_upload(uid)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"status": "screened"}


@router.delete("/submissions/{sid}")
def delete_submission(sid: int, user: User = Depends(current_user)):
    """The researcher cancels their own request until a document is sent; the staff in charge may delete it at any time."""
    _own_submission(sid, user)
    try:
        files = state.get_tracker().delete_submission(sid, force=user.role == "staff")
    except ValueError:
        raise HTTPException(409, "ส่งเอกสารแล้ว ยกเลิกเองไม่ได้ ติดต่อเจ้าหน้าที่")
    for f in files:
        Path(f).unlink(missing_ok=True)
    return {"ok": True}


@router.post("/uploads/{uid}/send")
def send_upload(uid: int, user: User = Depends(current_user)):
    tk = state.get_tracker()
    up = tk.get_upload(uid)
    if up is None:
        raise HTTPException(404, "not found")
    _own_submission(up["submission_id"], user)
    try:
        tk.send_upload(uid, user.id)
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
