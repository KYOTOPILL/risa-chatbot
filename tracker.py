"""Submission tracking store (SQLite): submission types with versioned step lists. All rules live here, no web or LLM code."""
import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS types (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
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
CREATE TABLE IF NOT EXISTS uploads (
    id INTEGER PRIMARY KEY, submission_id INTEGER NOT NULL REFERENCES submissions(id), step_index INTEGER NOT NULL,
    doc_name TEXT NOT NULL, filename TEXT NOT NULL, path TEXT NOT NULL, findings TEXT NOT NULL, status TEXT NOT NULL,
    dismissed TEXT NOT NULL DEFAULT '[]', note TEXT NOT NULL DEFAULT '', reviewed_by TEXT,
    created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
"""
UPLOAD_STATUSES = {"screened", "cannot_check", "sent", "approved", "returned"}


def validate_steps(steps) -> list:
    """Every step needs a title and a list of document names; anything else would crash upload and review later."""
    if not isinstance(steps, list) or not steps:
        raise ValueError("steps must be a non-empty list")
    for s in steps:
        if (not isinstance(s, dict) or not isinstance(s.get("title"), str) or not s["title"].strip()
                or not isinstance(s.get("documents"), list) or not all(isinstance(d, str) and d.strip() for d in s["documents"])):
            raise ValueError("each step needs a title and a documents list")
    return steps


class Tracker:
    def __init__(self, path: Path):
        self.path = path
        with self._db() as db:
            db.executescript(SCHEMA)

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

    _VERSION_SQL = "SELECT v.*, t.name AS type_name FROM versions v JOIN types t ON t.id = v.type_id"

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

    # ---- submissions ----
    def create_submission(self, title: str, version_id: int, researcher_ids: list[str], staff_id: str) -> int:
        v = self.get_version(version_id)
        if not v or v["status"] != "approved":
            raise ValueError("submission needs an approved type version")
        if not researcher_ids:
            raise ValueError("submission needs at least one researcher")
        with self._db() as db:
            sid = db.execute("INSERT INTO submissions (title, version_id, staff_id) VALUES (?, ?, ?)",
                             (title, version_id, staff_id)).lastrowid
            db.executemany("INSERT OR IGNORE INTO submission_researchers VALUES (?, ?)", [(sid, r) for r in researcher_ids])
        return sid

    def _submission(self, db, row) -> dict:
        v = json.loads(row["steps"])
        rs = [r[0] for r in db.execute("SELECT user_id FROM submission_researchers WHERE submission_id = ? ORDER BY user_id", (row["id"],))]
        return {"id": row["id"], "title": row["title"], "type_name": row["type_name"], "staff_id": row["staff_id"],
                "researcher_ids": rs, "current_step": row["current_step"], "step_count": len(v), "steps": v}

    _SUB_SQL = ("SELECT s.*, v.steps, t.name AS type_name FROM submissions s JOIN versions v ON v.id = s.version_id "
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

    # ---- uploads ----
    def add_upload(self, sid: int, step_index: int, doc_name: str, filename: str, path: str, findings: list | None, status: str) -> int:
        if status not in UPLOAD_STATUSES:
            raise ValueError("bad upload status")
        with self._db() as db:
            return db.execute("INSERT INTO uploads (submission_id, step_index, doc_name, filename, path, findings, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                              (sid, step_index, doc_name, filename, path, json.dumps(findings or [], ensure_ascii=False), status)).lastrowid

    @staticmethod
    def _upload(row) -> dict:
        return {**dict(row), "findings": json.loads(row["findings"]), "dismissed": json.loads(row["dismissed"])}

    def get_upload(self, upload_id: int) -> dict | None:
        with self._db() as db:
            row = db.execute("SELECT * FROM uploads WHERE id = ?", (upload_id,)).fetchone()
        return self._upload(row) if row else None

    def send_upload(self, upload_id: int) -> None:
        """Researcher sends a screened upload to staff. Conditional, so it never overwrites a staff decision."""
        with self._db() as db:
            n = db.execute("UPDATE uploads SET status = 'sent' WHERE id = ? AND status IN ('screened', 'cannot_check')", (upload_id,)).rowcount
        if not n:
            raise ValueError("upload cannot be sent")

    def set_upload_status(self, upload_id: int, status: str) -> None:
        if status not in UPLOAD_STATUSES:
            raise ValueError("bad upload status")
        with self._db() as db:
            db.execute("UPDATE uploads SET status = ? WHERE id = ?", (status, upload_id))

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
            return bool(moved)
        return False
        steps = json.loads(row["steps"])
        docs = steps[up["step_index"]]["documents"] if up["step_index"] < len(steps) else []
        latest = self.latest_uploads(up["submission_id"], up["step_index"])
        if up["step_index"] == row["current_step"] and docs and all(latest.get(d, {}).get("status") == "approved" for d in docs):
            self.move_step(up["submission_id"], staff_id, row["current_step"] + 1, "auto: all documents approved")
            return True
        return False
