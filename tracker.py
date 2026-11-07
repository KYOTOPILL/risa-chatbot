"""Submission tracking store (SQLite): submission types with versioned step lists. All rules live here, no web or LLM code."""
import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS types (id INTEGER PRIMARY KEY, name TEXT NOT NULL, open INTEGER NOT NULL DEFAULT 0, owner_id TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS versions (
    id INTEGER PRIMARY KEY, type_id INTEGER NOT NULL REFERENCES types(id), version INTEGER NOT NULL,
    status TEXT NOT NULL, steps TEXT NOT NULL, source_file TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS submissions (
    id INTEGER PRIMARY KEY, title TEXT NOT NULL, version_id INTEGER NOT NULL REFERENCES versions(id),
    staff_id TEXT NOT NULL, current_step INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS submission_researchers (
    submission_id INTEGER NOT NULL REFERENCES submissions(id), user_id TEXT NOT NULL, PRIMARY KEY (submission_id, user_id));
CREATE TABLE IF NOT EXISTS step_events (
    id INTEGER PRIMARY KEY, submission_id INTEGER NOT NULL REFERENCES submissions(id),
    from_step INTEGER NOT NULL, to_step INTEGER NOT NULL, staff_id TEXT NOT NULL,
    at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, note TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS forms (
    type_id INTEGER NOT NULL REFERENCES types(id), doc_name TEXT NOT NULL, title TEXT NOT NULL, fields TEXT NOT NULL,
    status TEXT NOT NULL, file_path TEXT NOT NULL DEFAULT '', PRIMARY KEY (type_id, doc_name));
CREATE TABLE IF NOT EXISTS uploads (
    id INTEGER PRIMARY KEY, submission_id INTEGER NOT NULL REFERENCES submissions(id), step_index INTEGER NOT NULL,
    doc_name TEXT NOT NULL, filename TEXT NOT NULL, path TEXT NOT NULL, findings TEXT NOT NULL, status TEXT NOT NULL,
    dismissed TEXT NOT NULL DEFAULT '[]', note TEXT NOT NULL DEFAULT '', reviewed_by TEXT, answers TEXT NOT NULL DEFAULT '[]',
    created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY, user_id TEXT NOT NULL, submission_id INTEGER NOT NULL, text TEXT NOT NULL,
    seen INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
"""
UPLOAD_STATUSES = {"draft", "screened", "cannot_check", "sent", "approved", "returned"}


def validate_steps(steps) -> list:
    """Every step needs a title and a list of document names; anything else would crash upload and review later."""
    if not isinstance(steps, list) or not steps:
        raise ValueError("steps must be a non-empty list")
    for s in steps:
        if (not isinstance(s, dict) or not isinstance(s.get("title"), str) or not s["title"].strip()
                or not isinstance(s.get("documents"), list) or not all(isinstance(d, str) and d.strip() for d in s["documents"])):
            raise ValueError("each step needs a title and a documents list")
    return steps


FIELD_TYPES = ("text", "longtext", "number", "date", "choice", "file")


def validate_form(title: str, fields: list) -> list:
    """Checks a form and returns its fields in full shape: key, label, hint, type, required, options. Keys stay stable when staff edit labels."""
    if not isinstance(title, str) or not title.strip():
        raise ValueError("form needs a title")
    if not isinstance(fields, list) or not fields or len(fields) > 60:
        raise ValueError("form needs 1 to 60 fields")
    out, keys = [], set()
    for f in fields:
        if not isinstance(f, dict) or not isinstance(f.get("label"), str) or not f["label"].strip() or not isinstance(f.get("hint", ""), str):
            raise ValueError("every field needs a label")
        kind = f.get("type") or "text"
        if kind not in FIELD_TYPES:
            raise ValueError("unknown field type: " + str(kind))
        options = [o.strip() for o in f.get("options") or [] if isinstance(o, str) and o.strip()] if kind == "choice" else []
        if kind == "choice" and len(options) < 2:
            raise ValueError("a choice field needs at least 2 options")
        key = f.get("key") if isinstance(f.get("key"), str) and f["key"] and f["key"] not in keys else None
        n = len(out) + 1
        while key is None:
            if f"f{n}" not in keys:
                key = f"f{n}"
            n += 1
        keys.add(key)
        out.append({"key": key, "label": f["label"].strip(), "hint": f.get("hint", "").strip(), "type": kind, "required": bool(f.get("required")), "options": options})
    return out


class Tracker:
    def __init__(self, path: Path):
        self.path = path
        with self._db() as db:
            db.executescript(SCHEMA)
            have = {r["name"] for r in db.execute("PRAGMA table_info(types)")}
            for col, ddl in (("open", "INTEGER NOT NULL DEFAULT 0"), ("owner_id", "TEXT NOT NULL DEFAULT ''")):  # databases made before posts existed
                if col not in have:
                    db.execute(f"ALTER TABLE types ADD COLUMN {col} {ddl}")
            if "answers" not in {r["name"] for r in db.execute("PRAGMA table_info(uploads)")}:
                db.execute("ALTER TABLE uploads ADD COLUMN answers TEXT NOT NULL DEFAULT '[]'")

    def _db(self) -> sqlite3.Connection:  # one connection per call, so request threads never share one
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        return db

    # ---- types and versions ----
    def create_type(self, name: str, steps: list, source_file: str) -> int:
        validate_steps(steps)
        with self._db() as db:
            tid = db.execute("INSERT INTO types (name) VALUES (?)", (name,)).lastrowid
            return self._add_version(db, tid, 1, steps, source_file)

    def new_version(self, type_id: int, steps: list, source_file: str) -> int:
        validate_steps(steps)
        with self._db() as db:
            n = db.execute("SELECT COALESCE(MAX(version), 0) FROM versions WHERE type_id = ?", (type_id,)).fetchone()[0]
            return self._add_version(db, type_id, n + 1, steps, source_file)

    @staticmethod
    def _add_version(db, type_id, version, steps, source_file) -> int:
        return db.execute("INSERT INTO versions (type_id, version, status, steps, source_file) VALUES (?, ?, 'draft', ?, ?)",
                          (type_id, version, json.dumps(steps, ensure_ascii=False), source_file)).lastrowid

    def update_draft(self, version_id: int, steps: list) -> None:
        validate_steps(steps)
        with self._db() as db:
            n = db.execute("UPDATE versions SET steps = ? WHERE id = ? AND status = 'draft'",
                           (json.dumps(steps, ensure_ascii=False), version_id)).rowcount
        if not n:
            raise ValueError("version is not an editable draft")

    def approve(self, version_id: int) -> None:
        with self._db() as db:
            db.execute("UPDATE versions SET status = 'approved' WHERE id = ?", (version_id,))

    def _used(self, db, where: str, arg: int) -> bool:
        return bool(db.execute(f"SELECT 1 FROM submissions s JOIN versions v ON v.id = s.version_id WHERE {where} = ?", (arg,)).fetchone())

    def delete_version(self, version_id: int) -> list[str]:
        """Delete one version, and its type when it was the last. Refused while requests use it. Returns source files to remove."""
        with self._db() as db:
            row = db.execute("SELECT type_id, source_file FROM versions WHERE id = ?", (version_id,)).fetchone()
            if not row:
                raise KeyError(version_id)
            if self._used(db, "v.id", version_id):
                raise ValueError("requests already use this version")
            db.execute("DELETE FROM versions WHERE id = ?", (version_id,))
            files = [row["source_file"]]
            if not db.execute("SELECT 1 FROM versions WHERE type_id = ?", (row["type_id"],)).fetchone():
                db.execute("DELETE FROM forms WHERE type_id = ?", (row["type_id"],))
                db.execute("DELETE FROM types WHERE id = ?", (row["type_id"],))
        return files

    def delete_type(self, type_id: int) -> list[str]:
        """Delete a type with all its versions and forms. Refused while any request uses it. Returns source files to remove."""
        with self._db() as db:
            rows = db.execute("SELECT source_file FROM versions WHERE type_id = ?", (type_id,)).fetchall()
            if not db.execute("SELECT 1 FROM types WHERE id = ?", (type_id,)).fetchone():
                raise KeyError(type_id)
            if self._used(db, "v.type_id", type_id):
                raise ValueError("requests already use this type")
            for t in ("forms", "versions"):
                db.execute(f"DELETE FROM {t} WHERE type_id = ?", (type_id,))
            db.execute("DELETE FROM types WHERE id = ?", (type_id,))
        return [r["source_file"] for r in rows]

    _VERSION_SQL = "SELECT v.*, t.name AS type_name, t.open AS open, t.owner_id AS owner_id FROM versions v JOIN types t ON t.id = v.type_id"

    @staticmethod
    def _version(row) -> dict:
        return {**dict(row), "steps": json.loads(row["steps"])}

    def get_version(self, version_id: int) -> dict | None:
        with self._db() as db:
            row = db.execute(self._VERSION_SQL + " WHERE v.id = ?", (version_id,)).fetchone()
        return self._version(row) if row else None

    def list_drafts(self) -> list[dict]:
        with self._db() as db:
            rows = db.execute(self._VERSION_SQL + " WHERE v.status = 'draft' ORDER BY v.id").fetchall()
        return [self._version(r) for r in rows]

    def list_types(self) -> list[dict]:
        """Newest approved version of each type."""
        with self._db() as db:
            rows = db.execute(self._VERSION_SQL + " WHERE v.status = 'approved' AND v.version = "
                              "(SELECT MAX(version) FROM versions WHERE type_id = v.type_id AND status = 'approved') ORDER BY t.name").fetchall()
        return [self._version(r) for r in rows]

    # ---- blank forms: fields staff can edit; researchers see only approved ones ----
    @staticmethod
    def _form(row) -> dict:
        return {**dict(row), "fields": json.loads(row["fields"])}

    def put_form(self, type_id: int, doc_name: str, title: str, fields: list, status: str = "draft") -> None:
        """Insert or replace the form of one document of a type."""
        fields = validate_form(title, fields)
        with self._db() as db:
            db.execute("INSERT OR REPLACE INTO forms (type_id, doc_name, title, fields, status) VALUES (?, ?, ?, ?, ?)",
                       (type_id, doc_name, title.strip(), json.dumps(fields, ensure_ascii=False), status))

    def get_form(self, type_id: int, doc_name: str) -> dict | None:
        with self._db() as db:
            row = db.execute("SELECT * FROM forms WHERE type_id = ? AND doc_name = ?", (type_id, doc_name)).fetchone()
        return self._form(row) if row else None

    def list_forms(self, type_id: int) -> list[dict]:
        with self._db() as db:
            return [self._form(r) for r in db.execute("SELECT * FROM forms WHERE type_id = ? ORDER BY doc_name", (type_id,))]

    def approve_form(self, type_id: int, doc_name: str) -> bool:
        with self._db() as db:
            return db.execute("UPDATE forms SET status = 'approved' WHERE type_id = ? AND doc_name = ?", (type_id, doc_name)).rowcount > 0

    # ---- posts: an open type is listed for researchers, who start their own request; the owner is staff in charge of those ----
    def set_type_open(self, type_id: int, is_open: bool, owner_id: str | None = None) -> None:
        with self._db() as db:
            if owner_id is None:
                db.execute("UPDATE types SET open = ? WHERE id = ?", (int(is_open), type_id))
            else:
                db.execute("UPDATE types SET open = ?, owner_id = ? WHERE id = ?", (int(is_open), owner_id, type_id))

    def list_open_types(self) -> list[dict]:
        return [v for v in self.list_types() if v["open"]]

    # ---- submissions ----
    def create_submission(self, title: str, version_id: int, researcher_ids: list[str], staff_id: str, actor: str | None = None) -> int:
        v = self.get_version(version_id)
        if not v or v["status"] != "approved":
            raise ValueError("submission needs an approved type version")
        if not researcher_ids:
            raise ValueError("submission needs at least one researcher")
        with self._db() as db:
            sid = db.execute("INSERT INTO submissions (title, version_id, staff_id) VALUES (?, ?, ?)",
                             (title, version_id, staff_id)).lastrowid
            db.executemany("INSERT OR IGNORE INTO submission_researchers VALUES (?, ?)", [(sid, r) for r in researcher_ids])
        self._notify(sid, f"งานใหม่ “{title}”", [staff_id, *researcher_ids], actor)
        return sid

    def _submission(self, db, row) -> dict:
        v = json.loads(row["steps"])
        rs = [r[0] for r in db.execute("SELECT user_id FROM submission_researchers WHERE submission_id = ? ORDER BY user_id", (row["id"],))]
        return {"id": row["id"], "title": row["title"], "type_id": row["type_id"], "type_name": row["type_name"], "staff_id": row["staff_id"],
                "researcher_ids": rs, "current_step": row["current_step"], "step_count": len(v), "steps": v}

    _SUB_SQL = ("SELECT s.*, v.steps, v.type_id, t.name AS type_name FROM submissions s JOIN versions v ON v.id = s.version_id "
                "JOIN types t ON t.id = v.type_id")

    def list_submissions(self, user_id: str, role: str) -> list[dict]:
        sql, args = self._SUB_SQL, ()
        if role != "staff":  # anything but staff is treated as a researcher: least privilege
            sql += " WHERE s.id IN (SELECT submission_id FROM submission_researchers WHERE user_id = ?)"
            args = (user_id,)
        with self._db() as db:
            out = [self._submission(db, r) for r in db.execute(sql + " ORDER BY s.id", args)]
        for s in out:
            del s["steps"]
        return out

    def get_submission(self, sid: int, user_id: str, role: str) -> dict | None:
        with self._db() as db:
            row = db.execute(self._SUB_SQL + " WHERE s.id = ?", (sid,)).fetchone()
            if not row:
                return None
            sub = self._submission(db, row)
            if role != "staff" and user_id not in sub["researcher_ids"]:
                return None
            sub["events"] = [dict(e) for e in db.execute(
                "SELECT from_step, to_step, staff_id, at, note FROM step_events WHERE submission_id = ? ORDER BY id", (sid,))]
        cur = sub["current_step"]
        sub["uploads"] = [{k: v for k, v in u.items() if k != "path"}
                          for u in (self.latest_uploads(sid, cur).values() if cur < sub["step_count"] else [])]
        return sub

    # ---- notifications: what changed on a request, for each person involved except the one who did it ----
    def _notify(self, sid: int, text: str, to: list[str], actor: str | None) -> None:
        with self._db() as db:
            db.executemany("INSERT INTO notifications (user_id, submission_id, text) VALUES (?, ?, ?)", [(u, sid, text) for u in dict.fromkeys(to) if u != actor])

    def _researchers(self, sid: int) -> list[str]:
        with self._db() as db:
            return [r[0] for r in db.execute("SELECT user_id FROM submission_researchers WHERE submission_id = ?", (sid,))]

    def _title_staff(self, sid: int) -> tuple[str, str]:
        with self._db() as db:
            r = db.execute("SELECT title, staff_id FROM submissions WHERE id = ?", (sid,)).fetchone()
        return r["title"], r["staff_id"]

    def notifications(self, user_id: str, limit: int = 30) -> dict:
        with self._db() as db:
            rows = [dict(r) for r in db.execute("SELECT * FROM notifications WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit))]
            unread = db.execute("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND seen = 0", (user_id,)).fetchone()[0]
        return {"items": rows, "unread": unread}

    def mark_seen(self, user_id: str) -> None:
        with self._db() as db:
            db.execute("UPDATE notifications SET seen = 1 WHERE user_id = ?", (user_id,))

    def set_staff(self, sid: int, staff_id: str, actor: str | None = None) -> None:
        """Hand a request to another staff member. Who may do it is the caller's rule."""
        with self._db() as db:
            if not db.execute("UPDATE submissions SET staff_id = ? WHERE id = ?", (staff_id, sid)).rowcount:
                raise ValueError("no such submission")
        self._notify(sid, f"คุณได้รับมอบหมายให้ดูแลงาน “{self._title_staff(sid)[0]}”", [staff_id], actor)

    def move_step(self, sid: int, staff_id: str, to_step: int, note: str = "") -> None:
        """Only the staff in charge may move; to_step == step_count means completed."""
        with self._db() as db:
            row = db.execute(self._SUB_SQL + " WHERE s.id = ?", (sid,)).fetchone()
            if not row:
                raise ValueError("no such submission")
            if row["staff_id"] != staff_id:
                raise PermissionError("only the staff in charge can change this submission")
            if not 0 <= to_step <= len(json.loads(row["steps"])):
                raise ValueError("step out of range")
            db.execute("UPDATE submissions SET current_step = ? WHERE id = ?", (to_step, sid))
            db.execute("INSERT INTO step_events (submission_id, from_step, to_step, staff_id, note) VALUES (?, ?, ?, ?, ?)",
                       (sid, row["current_step"], to_step, staff_id, note))
        self._notify(sid, f"งาน “{row['title']}” ย้ายไปขั้นตอนที่ {to_step + 1}" if to_step < len(json.loads(row["steps"])) else f"งาน “{row['title']}” ดำเนินการเสร็จสิ้น", self._researchers(sid), staff_id)

    # ---- uploads ----
    def add_upload(self, sid: int, step_index: int, doc_name: str, filename: str, path: str, findings: list | None, status: str, answers: list | None = None) -> int:
        if status not in UPLOAD_STATUSES:
            raise ValueError("bad upload status")
        with self._db() as db:
            last = db.execute("SELECT note FROM uploads WHERE submission_id = ? AND step_index = ? AND doc_name = ? ORDER BY id DESC LIMIT 1", (sid, step_index, doc_name)).fetchone()
            note = last["note"] if last else ""  # the staff's reason for a return stays visible while the researcher keeps editing
            return db.execute("INSERT INTO uploads (submission_id, step_index, doc_name, filename, path, findings, status, answers, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                              (sid, step_index, doc_name, filename, path, json.dumps(findings or [], ensure_ascii=False), status, json.dumps(answers or [], ensure_ascii=False), note)).lastrowid

    @staticmethod
    def _upload(row) -> dict:
        return {**dict(row), "findings": json.loads(row["findings"]), "dismissed": json.loads(row["dismissed"]), "answers": json.loads(row["answers"])}

    def get_upload(self, upload_id: int) -> dict | None:
        with self._db() as db:
            row = db.execute("SELECT * FROM uploads WHERE id = ?", (upload_id,)).fetchone()
        return self._upload(row) if row else None

    def send_upload(self, upload_id: int, actor: str | None = None) -> None:
        """Researcher sends a screened upload to staff. Conditional, so it never overwrites a staff decision."""
        with self._db() as db:
            n = db.execute("UPDATE uploads SET status = 'sent' WHERE id = ? AND status IN ('screened', 'cannot_check')", (upload_id,)).rowcount
        if not n:
            raise ValueError("upload cannot be sent")
        up = self.get_upload(upload_id)
        title, staff = self._title_staff(up["submission_id"])
        self._notify(up["submission_id"], f"{up['doc_name']} ส่งแล้ว รอตรวจสอบ ({title})", [staff], actor)

    def latest_uploads(self, sid: int, step_index: int) -> dict[str, dict]:
        """Newest upload per document name for one step; older ones stay as history."""
        with self._db() as db:
            rows = db.execute("SELECT * FROM uploads WHERE submission_id = ? AND step_index = ? ORDER BY id", (sid, step_index)).fetchall()
        return {r["doc_name"]: self._upload(r) for r in rows}

    def review_queue(self) -> list[dict]:
        """Sent uploads waiting for the staff check, oldest first."""
        with self._db() as db:
            rows = db.execute("SELECT u.*, s.title AS submission_title, s.staff_id FROM uploads u "
                              "JOIN submissions s ON s.id = u.submission_id WHERE u.status = 'sent' ORDER BY u.id").fetchall()
        return [self._upload(r) for r in rows]

    def review_upload(self, upload_id: int, staff_id: str, decision: str, dismissed: list[int], note: str) -> bool:
        """Staff final check. Returns True when approving this upload advanced the submission to its next step."""
        up = self.get_upload(upload_id)
        if up is None:
            raise ValueError("no such upload")
        with self._db() as db:
            row = db.execute(self._SUB_SQL + " WHERE s.id = ?", (up["submission_id"],)).fetchone()
        if row["staff_id"] != staff_id:
            raise PermissionError("only the staff in charge can review this upload")
        if up["status"] != "sent" or decision not in ("approve", "return"):
            raise ValueError("upload is not waiting for review, or bad decision")
        with self._db() as db:
            n = db.execute("UPDATE uploads SET status = ?, dismissed = ?, note = ?, reviewed_by = ? WHERE id = ? AND status = 'sent'",
                           ("approved" if decision == "approve" else "returned", json.dumps(dismissed), note, staff_id, upload_id)).rowcount
        if not n:
            raise ValueError("upload is not waiting for review")
        title = self._title_staff(up["submission_id"])[0]
        self._notify(up["submission_id"], (f"{up['doc_name']} อนุมัติแล้ว ({title})" if decision == "approve" else f"{up['doc_name']} ถูกส่งกลับให้แก้ไข ({title})" + (f": {note}" if note else "")),
                     self._researchers(up["submission_id"]), staff_id)
        if decision != "approve":
            return False
        steps = json.loads(row["steps"])
        docs = steps[up["step_index"]]["documents"] if up["step_index"] < len(steps) else []
        latest = self.latest_uploads(up["submission_id"], up["step_index"])
        if up["step_index"] == row["current_step"] and docs and all(latest.get(d, {}).get("status") == "approved" for d in docs):
            cur = row["current_step"]
            with self._db() as db:  # only the request that still sees the old step advances it, so no double move or duplicate event
                moved = db.execute("UPDATE submissions SET current_step = ? WHERE id = ? AND current_step = ?", (cur + 1, up["submission_id"], cur)).rowcount
                if moved:
                    db.execute("INSERT INTO step_events (submission_id, from_step, to_step, staff_id, note) VALUES (?, ?, ?, ?, ?)",
                               (up["submission_id"], cur, cur + 1, staff_id, "auto: all documents approved"))
            if moved:
                self._notify(up["submission_id"], f"งาน “{title}” ไปขั้นตอนถัดไปแล้ว" if cur + 1 < len(steps) else f"งาน “{title}” ดำเนินการเสร็จสิ้น", self._researchers(up["submission_id"]), staff_id)
            return bool(moved)
        return False
