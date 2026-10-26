import logging
from pathlib import Path
from typing import Literal

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StringConstraints
from typing_extensions import Annotated

import admin
import downloads
import rag
import state
from config import CONTENT_DIR, ROOT

log = logging.getLogger("chatbot")
if not log.handlers:  # answer sources go here, never to the browser
    log.addHandler(logging.StreamHandler())
log.setLevel(logging.INFO)

WEB = ROOT / "web"
ERROR_TEXT = "ขออภัย ระบบขัดข้อง กรุณาลองใหม่อีกครั้งหรือติดต่อผู้ดูแลระบบ"
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


@app.post("/api/chat")
def chat(body: ChatIn):
    history = [rag.Turn(t.role, t.content) for t in body.history]
    key = " ".join(body.message.split()).casefold() if not history else None
    try:
        reply = state.cache.get(key)
        if reply is None:
            with state.lock:
                reply = rag.answer(history, body.message, state.get_store())
            if key and len(state.cache) < state.CACHE_MAX:  # full: stop adding, a reindex clears it
                state.cache[key] = reply
    except Exception:
        log.exception("answer failed")
        return JSONResponse({"text": ERROR_TEXT, "files": []}, status_code=503)
    log.info("q=%r sources=%s", body.message, reply.sources)
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


@app.get("/download/{doc_id}")
def download(doc_id: str):
    path = downloads.resolve_download(doc_id, state.get_store(), CONTENT_DIR)
    if path is None:
        return JSONResponse({"text": "ไม่พบไฟล์"}, status_code=404)
    return FileResponse(path, filename=path.name)


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


@app.get("/mockup")
def mockup():  # static design preview: fake chat, no model calls
    return FileResponse(WEB / "mockup.html")


@app.get("/admin-mockup")
def admin_mockup():  # static design preview: fake files, touches nothing
    return FileResponse(WEB / "admin-mockup.html")


app.mount("/static", RevalidatingStatic(directory=WEB), name="static")
