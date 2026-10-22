import logging
import threading
from functools import lru_cache
from typing import Literal

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StringConstraints
from typing_extensions import Annotated

import downloads
import rag
from config import CONTENT_DIR, ROOT
from store import Store

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


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
# one local model serves everyone: the lock makes concurrent questions wait their turn
_lock = threading.Lock()


@lru_cache
def get_store() -> Store:
    return Store()


@app.post("/api/chat")
def chat(body: ChatIn):
    history = [rag.Turn(t.role, t.content) for t in body.history]
    try:
        with _lock:
            reply = rag.answer(history, body.message, get_store())
    except Exception:
        log.exception("answer failed")
        return JSONResponse({"text": ERROR_TEXT, "files": []}, status_code=503)
    log.info("q=%r sources=%s", body.message, reply.sources)
    return {"text": reply.text, "files": reply.file_doc_ids}


@app.get("/download/{doc_id}")
def download(doc_id: str):
    path = downloads.resolve_download(doc_id, get_store(), CONTENT_DIR)
    if path is None:
        return JSONResponse({"text": "ไม่พบไฟล์"}, status_code=404)
    return FileResponse(path, filename=path.name)


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


app.mount("/static", StaticFiles(directory=WEB), name="static")
