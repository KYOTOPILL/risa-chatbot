import json
import logging
import queue
import threading
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StringConstraints
from typing_extensions import Annotated

from app.api import admin
from app.features import my_requests
from app.features import tracker_api
from app.features import downloads
from app.rag import rag
from app.core import state
from app.core.auth import User, current_user, require_researcher
from app.core.config import CONTENT_DIR, ROOT

log = logging.getLogger("chatbot")
if not log.handlers:  # answer sources go here, never to the browser
    log.addHandler(logging.StreamHandler())
log.setLevel(logging.INFO)

WEB = ROOT / "web"
ERROR_TEXT = "ขออภัย ระบบขัดข้อง กรุณาลองใหม่อีกครั้งหรือติดต่อผู้ดูแลระบบ"
BUSY_TEXT = "กำลังตอบคำถามก่อนหน้าอยู่ กรุณารอสักครู่แล้วลองใหม่อีกครั้ง"
Text = Annotated[str, StringConstraints(max_length=4000)]


class TurnIn(BaseModel):
    role: Literal["user", "assistant"]
    content: Text


class ChatIn(BaseModel):
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    history: list[TurnIn] = Field(default_factory=list, max_length=12)


class RevalidatingStatic(StaticFiles):
    """Without a Cache-Control header browsers reuse stale js/css after an edit."""

    async def get_response(self, path, scope):
        resp = await super().get_response(path, scope)
        resp.headers["Cache-Control"] = "no-cache"
        return resp


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(admin.router)
app.include_router(tracker_api.router)


@app.post("/api/chat")
def chat(body: ChatIn, request: Request, user: User = Depends(require_researcher)):
    history = [rag.Turn(t.role, t.content) for t in body.history]
    key = " ".join(body.message.split()).casefold() if not history else None
    try:
        reply = state.cache.get(key)
        if reply is None:
            with state.slot(user.id) as ok:
                if not ok:  # this IP already has its allowed questions being answered
                    return JSONResponse({"text": BUSY_TEXT, "files": []}, status_code=429)
                reply = rag.answer(history, body.message, state.get_store(), me=lambda: my_requests.describe(state.get_tracker(), user.id))
            if key and not reply.personal and len(state.cache) < state.CACHE_MAX:  # full: stop adding, a reindex clears it
                state.cache[key] = reply
    except Exception:
        log.exception("answer failed")
        return JSONResponse({"text": ERROR_TEXT, "files": []}, status_code=503)
    return _payload(body.message, reply)


def _payload(message: str, reply: rag.Reply) -> dict:
    log.info("q=%r sources=%s", message, reply.sources)
    store = state.get_store()
    summaries = store.summaries(reply.file_doc_ids)
    files = []
    for i in reply.file_doc_ids:
        rel = store.doc_path(i)
        if rel:
            path = CONTENT_DIR / rel
            files.append({"id": i, "name": Path(rel).name, "summary": summaries.get(i, ""),
                          "size": path.stat().st_size if path.is_file() else None})
    return {"text": reply.text, "files": files}


@app.post("/api/chat/stream")
def chat_stream(body: ChatIn, request: Request, user: User = Depends(require_researcher)):
    """Same answer as /api/chat, sent as JSON lines: {"status": text} while tools run, {"delta": text} while the answer is written ({"delta": null} = discard
    the text so far), then {"done": true, "text", "files"} with the final text, or {"error": text}."""
    history = [rag.Turn(t.role, t.content) for t in body.history]
    key = " ".join(body.message.split()).casefold() if not history else None
    line = lambda o: json.dumps(o, ensure_ascii=False) + "\n"

    def events():
        reply = state.cache.get(key)
        if reply is None:
            q: queue.Queue = queue.Queue()

            def work():
                try:
                    with state.slot(user.id) as ok:
                        if not ok:
                            q.put(("error", BUSY_TEXT))
                            return
                        q.put(("reply", rag.answer(history, body.message, state.get_store(), llm=rag.chat_tools_stream,
                                                   on_delta=lambda d: q.put(("delta", d)),
                                                   on_status=lambda t: q.put(("status", t)),
                                                   me=lambda: my_requests.describe(state.get_tracker(), user.id))))
                except Exception:
                    log.exception("answer failed")
                    q.put(("error", ERROR_TEXT))

            threading.Thread(target=work, daemon=True).start()  # the answer blocks; this generator relays what it reports
            while True:
                kind, val = q.get()
                if kind in ("delta", "status"):
                    yield line({kind: val})
                elif kind == "error":
                    yield line({"error": val})
                    return
                else:
                    reply = val
                    break
            if key and not reply.personal and len(state.cache) < state.CACHE_MAX:
                state.cache[key] = reply
        try:
            yield line({"done": True, **_payload(body.message, reply)})
        except Exception:
            log.exception("answer failed")
            yield line({"error": ERROR_TEXT})

    return StreamingResponse(events(), media_type="application/x-ndjson", headers={"X-Accel-Buffering": "no"})


@app.get("/download/{doc_id}")
def download(doc_id: str):
    path = downloads.resolve_download(doc_id, state.get_store(), CONTENT_DIR)
    if path is None:
        return JSONResponse({"text": "ไม่พบไฟล์"}, status_code=404)
    return FileResponse(path, filename=path.name)


@app.get("/")
def home():
    return FileResponse(WEB / "home.html")


@app.get("/chat")
def chat_page(request: Request):
    """The chat is for logged-in researchers. Everyone else goes to the login or to their own workspace."""
    try:
        require_researcher(current_user(request))
    except HTTPException:
        return RedirectResponse("/")
    return FileResponse(WEB / "index.html")


@app.get("/track")
@app.get("/admin")  # the file manager now lives in the staff workspace
def moved():
    return RedirectResponse("/")


app.mount("/static", RevalidatingStatic(directory=WEB), name="static")
