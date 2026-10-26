"""Admin page for managing the content folder. Set ADMIN_PASSWORD to enable login (user: admin); unset = loopback only."""
import os
import re
import secrets
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

import state
from config import CONTENT_DIR, ROOT, SUPPORTED_EXTS
from docmeta import SHAREABLE, doc_meta
from ingest import build_index, summarize

MAX_BYTES = 25 * 1024 * 1024
ADMIN_USER = "admin"
LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}
BAD_CATEGORY = re.compile(r"[/\\\x00-\x1f]")


basic = HTTPBasic(auto_error=False)


def require_admin(request: Request, creds: HTTPBasicCredentials | None = Depends(basic)) -> None:
    password = os.environ.get("ADMIN_PASSWORD")
    if not password:  # no password set: loopback only, as before
        if not request.client or request.client.host not in LOCAL_HOSTS:
            raise HTTPException(403, "admin is only available on the server machine")
        return
    # ponytail: one shared login, no lockout or rate limit; add both before exposing beyond a trusted LAN
    ok = creds is not None and all(
        secrets.compare_digest(got.encode(), want.encode())
        for got, want in ((creds.username, ADMIN_USER), (creds.password, password))
    )
    if not ok:
        raise HTTPException(401, "login required", headers={"WWW-Authenticate": 'Basic realm="admin"'})


router = APIRouter(dependencies=[Depends(require_admin)])


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


def _read(f: UploadFile) -> bytes:
    data = f.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, f"ไฟล์ใหญ่เกินไป (สูงสุด {MAX_BYTES // 1024 // 1024} MB)")
    return data


def _write(dst: Path, data: bytes) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.parent / f".{dst.name}.part"
    tmp.write_bytes(data)
    tmp.replace(dst)  # same-name write replaces the old file


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
        _write(target / name, _read(f))
        saved.append((target / name).relative_to(CONTENT_DIR).as_posix())
    return {"saved": saved}


def _file(root: Path, rel: str) -> Path:
    path = (root / rel).resolve()
    if not path.is_relative_to(root) or path == root:
        raise HTTPException(400, "path not allowed")
    if not path.is_file():
        raise HTTPException(404, "ไม่พบไฟล์")
    return path


def _prune(path: Path, root: Path) -> None:
    for parent in path.parents:  # drop folders left empty
        if parent == root or any(parent.iterdir()):
            break
        parent.rmdir()


@router.post("/api/admin/replace")
def replace(path: str = Form(...), file: UploadFile = File(...)):
    """New version of an existing file: same path (so folder, name and downloadable stay), new content."""
    dst = _file(CONTENT_DIR.resolve(), path)
    if Path(file.filename or "").suffix.lower() != dst.suffix.lower():
        raise HTTPException(400, f"ต้องเป็นไฟล์ชนิดเดียวกัน ({dst.suffix})")
    _write(dst, _read(file))
    return {"path": path}


class DeleteIn(BaseModel):
    path: str


@router.post("/api/admin/delete")
def delete(body: DeleteIn):
    root = CONTENT_DIR.resolve()
    path = _file(root, body.path)
    path.unlink()
    _prune(path, root)
    return {"deleted": body.path}


@router.get("/api/admin/folders")
def list_folders():
    return sorted(p.name for p in CONTENT_DIR.glob("*")
                  if p.is_dir() and not p.name.startswith(".") and p.name != SHAREABLE)


class FolderIn(BaseModel):
    folder: str


@router.post("/api/admin/mkdir")
def mkdir(body: FolderIn):
    folder = body.folder.strip()
    if not folder:
        raise HTTPException(400, "ชื่อหมวดหมู่ไม่ถูกต้อง")
    _category_dir(folder, False).mkdir(parents=True, exist_ok=True)
    return {"folder": folder}


class MoveIn(BaseModel):
    path: str
    folder: str | None = None  # None = keep
    name: str | None = None
    downloadable: bool | None = None


@router.post("/api/admin/move")
def move(body: MoveIn):
    """Rename, move to another folder and/or flip downloadable, in one call."""
    root = CONTENT_DIR.resolve()
    src = _file(root, body.path)
    dirs = src.relative_to(root).parts[:-1]
    folder = next((d for d in dirs if d != SHAREABLE), "") if body.folder is None else body.folder
    downloadable = SHAREABLE in dirs if body.downloadable is None else body.downloadable
    name = src.name if body.name is None else _safe_name(body.name)
    dst = _category_dir(folder, downloadable) / name
    if dst.exists() and not dst.samefile(src):
        raise HTTPException(409, "มีไฟล์ชื่อนี้อยู่ในโฟลเดอร์ปลายทางแล้ว")
    dst.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dst)
    if dst.resolve() != src:
        _prune(src, root)
    return {"path": dst.resolve().relative_to(root).as_posix()}


@router.post("/api/admin/reindex")
def reindex():
    with state.lock:  # chat waits while the index is rebuilt
        return build_index(CONTENT_DIR, state.get_store(), summarize)


def _folder(name: str) -> Path:
    if not name.strip():
        raise HTTPException(400, "ชื่อหมวดหมู่ไม่ถูกต้อง")
    d = _category_dir(name, False)
    if not d.is_dir() or d.is_symlink():
        raise HTTPException(404, "ไม่พบโฟลเดอร์")
    return d


class RenameFolderIn(BaseModel):
    folder: str
    name: str


@router.post("/api/admin/rename-folder")
def rename_folder(body: RenameFolderIn):
    if not body.name.strip():
        raise HTTPException(400, "ชื่อหมวดหมู่ไม่ถูกต้อง")
    src, dst = _folder(body.folder), _category_dir(body.name, False)
    if dst.exists() and not dst.samefile(src):
        raise HTTPException(409, "มีโฟลเดอร์ชื่อนี้อยู่แล้ว")
    src.rename(dst)
    return {"folder": body.name.strip()}


@router.post("/api/admin/delete-folder")
def delete_folder(body: FolderIn):
    shutil.rmtree(_folder(body.folder))  # the page confirms with the file count first
    return {"deleted": body.folder}
