"""Admin page for managing the content folder. Local-machine only: not the final product."""
import re
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

import state
from config import CONTENT_DIR, ROOT, SUPPORTED_EXTS
from docmeta import SHAREABLE, doc_meta
from ingest import build_index

MAX_BYTES = 25 * 1024 * 1024
LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}
BAD_CATEGORY = re.compile(r"[/\\\x00-\x1f]")


def require_local(request: Request) -> None:
    # ponytail: loopback-only instead of login; add real auth before exposing admin to the office LAN
    if not request.client or request.client.host not in LOCAL_HOSTS:
        raise HTTPException(403, "admin is only available on the server machine")


router = APIRouter(dependencies=[Depends(require_local)])


def _category_dir(category: str, downloadable: bool) -> Path:
    category = category.strip()
    if category and (BAD_CATEGORY.search(category) or category.startswith(".")
                     or category.lower() == SHAREABLE or len(category) > 60):
        raise HTTPException(400, "ชื่อหมวดหมู่ไม่ถูกต้อง")
    path = CONTENT_DIR / category if category else CONTENT_DIR
    return path / SHAREABLE if downloadable else path


def _safe_name(filename: str) -> str:
    name = Path((filename or "").replace("\\", "/")).name
    if not name or name.startswith(".") or Path(name).suffix.lower() not in SUPPORTED_EXTS:
        raise HTTPException(400, f"ไม่รองรับไฟล์นี้ (รองรับ {', '.join(sorted(SUPPORTED_EXTS))})")
    return name


@router.get("/admin")
def page():
    return FileResponse(ROOT / "web" / "admin.html")


@router.get("/api/admin/files")
def list_files():
    rows = []
    for p in sorted(CONTENT_DIR.rglob("*")):
        if not p.is_file() or p.name.startswith("."):
            continue
        m = doc_meta(p, CONTENT_DIR)
        rows.append({"path": m.rel_path, "category": m.category, "downloadable": m.downloadable,
                     "size": p.stat().st_size, "mtime": m.mtime, "supported": p.suffix.lower() in SUPPORTED_EXTS})
    return rows


@router.post("/api/admin/upload")
def upload(files: list[UploadFile] = File(...), category: str = Form(""), downloadable: bool = Form(False)):
    target = _category_dir(category, downloadable)
    saved = []
    for f in files:
        name = _safe_name(f.filename)
        data = f.file.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise HTTPException(413, f"ไฟล์ใหญ่เกินไป (สูงสุด {MAX_BYTES // 1024 // 1024} MB)")
        target.mkdir(parents=True, exist_ok=True)
        tmp = target / f".{name}.part"
        tmp.write_bytes(data)
        tmp.replace(target / name)  # same-name upload replaces the old file
        saved.append((target / name).relative_to(CONTENT_DIR).as_posix())
    return {"saved": saved}


class DeleteIn(BaseModel):
    path: str


@router.post("/api/admin/delete")
def delete(body: DeleteIn):
    root = CONTENT_DIR.resolve()
    path = (root / body.path).resolve()
    if not path.is_relative_to(root) or path == root:
        raise HTTPException(400, "path not allowed")
    if not path.is_file():
        raise HTTPException(404, "ไม่พบไฟล์")
    path.unlink()
    for parent in path.parents:  # drop folders left empty
        if parent == root or any(parent.iterdir()):
            break
        parent.rmdir()
    return {"deleted": body.path}


@router.post("/api/admin/reindex")
def reindex():
    with state.lock:  # chat waits while the index is rebuilt
        return build_index(CONTENT_DIR, state.get_store())
