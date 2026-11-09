"""LINE Official Account chatbot. LINE posts each message to /api/line/webhook; a researcher who linked their LINE account
(code from the website) gets the same AI answers as the web chat. Replies go back through LINE's reply API."""
import base64
import hashlib
import hmac
import logging
import re
import secrets
import threading
import time
from pathlib import Path
from urllib.parse import quote

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from app.core import config, state
from app.core.auth import User, login_allowed, login_failed, require_researcher
from app.features import my_requests
from app.rag import rag

log = logging.getLogger("chatbot")
router = APIRouter(prefix="/api/line")

CODE_MINUTES = 10
LINK_HELP = "เปิดเว็บ RiSA แล้วกดปุ่ม “เชื่อม LINE” จากนั้นพิมพ์รหัส 6 หลักที่ได้ส่งมาที่นี่"
WELCOME = "สวัสดีค่ะ นี่คือผู้ช่วย AI ของ RiSA ก่อนเริ่มใช้งาน กรุณาเชื่อมบัญชีนักวิจัยของคุณ: " + LINK_HELP
LINKED_OK = "เชื่อมบัญชีเรียบร้อยแล้วค่ะ ถามได้เลย เช่น “ขอแบบฟอร์มใบลา” หรือ “งานของฉันตอนนี้ถึงขั้นไหน”"
BAD_CODE = f"รหัสไม่ถูกต้องหรือหมดอายุ (ใช้ได้ {CODE_MINUTES} นาที) กรุณากดเชื่อม LINE บนเว็บเพื่อรับรหัสใหม่"
LOCKED = "พิมพ์รหัสผิดหลายครั้ง กรุณารอสักครู่แล้วลองใหม่"
STAFF_ONLY = "แชทนี้ใช้ได้เฉพาะนักวิจัย เจ้าหน้าที่ใช้งานผ่านเว็บ RiSA"
NOT_TEXT = "รองรับเฉพาะข้อความ หากต้องการส่งเอกสารให้ตรวจสอบ กรุณาอัปโหลดผ่านเว็บ RiSA"
BUSY = "กำลังตอบคำถามก่อนหน้าอยู่ กรุณารอสักครู่แล้วลองใหม่อีกครั้ง"
ERROR = "ขออภัย ระบบขัดข้อง กรุณาลองใหม่อีกครั้งหรือติดต่อผู้ดูแลระบบ"
UNLINK_WORD = "ยกเลิกการเชื่อมต่อ"
UNLINKED = "ยกเลิกการเชื่อมบัญชีแล้วค่ะ"

_codes: dict[str, tuple[str, float]] = {}  # code -> (user id, expiry); in memory, so a restart only voids unused codes
_history: dict[str, list[rag.Turn]] = {}  # ponytail: chat memory per LINE user in memory (lost on restart, last 12 turns); a table if it must survive


def _post(path: str, body: dict) -> None:
    r = httpx.post("https://api.line.me/v2/bot/" + path, json=body, timeout=10, headers={"Authorization": "Bearer " + config.LINE_CHANNEL_ACCESS_TOKEN})
    r.raise_for_status()


def _say(token: str, to: str, text: str) -> None:
    """Reply with the reply token; if it has expired (a slow answer), push instead."""
    messages = [{"type": "text", "text": text[:4900]}]
    try:
        _post("message/reply", {"replyToken": token, "messages": messages})
    except httpx.HTTPError:
        try:
            _post("message/push", {"to": to, "messages": messages})
        except httpx.HTTPError:
            log.exception("LINE reply failed")


def _run(fn, *args) -> None:
    threading.Thread(target=fn, args=args, daemon=True).start()


def _push_all(line_ids: list[str], text: str) -> None:
    for line_id in line_ids:
        try:
            _post("message/push", {"to": line_id, "messages": [{"type": "text", "text": text[:4900]}]})
        except httpx.HTTPError:
            log.exception("LINE alert failed")


def alert(tk, user_ids: list[str], text: str) -> None:
    """Tracker hook: send each new in-app notification to the recipients' linked LINE accounts.
    ponytail: every notification is one push and pushes count against the LINE monthly quota; batch or let people opt out if that runs short."""
    if not (config.LINE_CHANNEL_SECRET and config.LINE_CHANNEL_ACCESS_TOKEN):
        return
    ids = tk.lines_for(user_ids)
    if ids:
        _run(_push_all, ids, text + (f"\nเปิดดูที่ {config.PUBLIC_URL}" if config.PUBLIC_URL else ""))


def _files(reply: rag.Reply) -> str:
    out = []
    for i in reply.file_doc_ids:
        rel = state.get_store().doc_path(i)
        if rel:  # LINE bots cannot attach files: send the name and a download link
            out.append(Path(rel).name + (f"\n{config.PUBLIC_URL}/download/{quote(i)}" if config.PUBLIC_URL else ""))
    return "\n\n" + "\n\n".join(out) if out else ""


def _link(sender: str, code: str) -> str:
    key = "line|" + sender
    if not login_allowed(key):
        return LOCKED
    uid, exp = _codes.pop(code, (None, 0))
    if uid is None or exp < time.time():
        login_failed(key)
        return BAD_CODE
    state.get_tracker().link_line(sender, uid)
    return LINKED_OK


def _ask(tk, uid: str, sender: str, text: str) -> str:
    try:
        with state.slot(uid) as ok:
            if not ok:
                return BUSY
            history = _history.get(sender, [])
            reply = rag.answer(history, text[:2000], state.get_store(), me=lambda: my_requests.describe(tk, uid))
    except Exception:
        log.exception("answer failed")
        return ERROR
    sent = _files(reply)
    _history[sender] = (history + [rag.Turn("user", text), rag.Turn("assistant", reply.text + (f" [ส่งไฟล์: {sent.strip()}]" if sent else ""))])[-12:]
    return reply.text + sent


def _event(ev: dict) -> None:
    src, token = ev.get("source", {}), ev.get("replyToken", "")
    sender = src.get("userId", "")
    if src.get("type") != "user" or not sender:  # groups and rooms: the bot is for one-to-one help
        return
    tk = state.get_tracker()
    if ev.get("type") == "follow":
        return _say(token, sender, WELCOME)
    if ev.get("type") != "message":
        return
    msg = ev.get("message", {})
    if msg.get("type") != "text":
        return _say(token, sender, NOT_TEXT)
    text = msg.get("text", "").strip()
    if re.fullmatch(r"\d{6}", text):
        return _say(token, sender, _link(sender, text))
    uid = tk.user_for_line(sender)
    if text == UNLINK_WORD and uid:
        tk.unlink_line(sender)
        _history.pop(sender, None)
        return _say(token, sender, UNLINKED)
    if uid is None:
        return _say(token, sender, WELCOME)
    if tk.role_of(uid) != "researcher":
        return _say(token, sender, STAFF_ONLY)
    try:
        _post("chat/loading/start", {"chatId": sender, "loadingSeconds": 30})  # the "typing" dots while the AI works
    except httpx.HTTPError:
        pass
    _say(token, sender, _ask(tk, uid, sender, text))


def process(events: list[dict]) -> None:
    for ev in events:
        try:
            _event(ev)
        except Exception:
            log.exception("LINE event failed")


@router.post("/webhook")
async def webhook(request: Request, background: BackgroundTasks):
    if not config.LINE_CHANNEL_SECRET:
        raise HTTPException(404, "LINE is not set up")
    body = await request.body()
    want = base64.b64encode(hmac.new(config.LINE_CHANNEL_SECRET.encode(), body, hashlib.sha256).digest()).decode()
    if not hmac.compare_digest(want, request.headers.get("X-Line-Signature", "")):
        raise HTTPException(400, "bad signature")
    try:
        events = (await request.json()).get("events", [])
    except ValueError:
        raise HTTPException(400, "bad body")
    background.add_task(process, events)  # answer after replying 200: LINE gives up on a slow webhook
    return {}


@router.get("/status")
def status(user: User = Depends(require_researcher)):
    return {"enabled": bool(config.LINE_CHANNEL_SECRET), "linked": state.get_tracker().has_line(user.id), "bot_id": config.LINE_BOT_ID}


@router.post("/code")
def code(user: User = Depends(require_researcher)):
    """A one-time code the researcher types into the LINE chat to link that LINE account to this user."""
    now = time.time()
    for c in [c for c, (_, exp) in _codes.items() if exp < now]:
        del _codes[c]
    c = f"{secrets.randbelow(10**6):06d}"
    while c in _codes:
        c = f"{secrets.randbelow(10**6):06d}"
    _codes[c] = (user.id, now + CODE_MINUTES * 60)
    return {"code": c, "minutes": CODE_MINUTES}
