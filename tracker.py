"""Submission tracking store (SQLite): submission types with versioned step lists. All rules live here, no web or LLM code."""
import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS types (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS versions (
    id INTEGER PRIMARY KEY, type_id INTEGER NOT NULL REFERENCES types(id), version INTEGER NOT NULL,
    status TEXT NOT NULL, steps TEXT NOT NULL, source_file TEXT NOT NULL);
"""


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
        with self._db() as db:
            tid = db.execute("INSERT INTO types (name) VALUES (?)", (name,)).lastrowid
            return self._add_version(db, tid, 1, steps, source_file)

    def new_version(self, type_id: int, steps: list, source_file: str) -> int:
        with self._db() as db:
            n = db.execute("SELECT COALESCE(MAX(version), 0) FROM versions WHERE type_id = ?", (type_id,)).fetchone()[0]
            return self._add_version(db, type_id, n + 1, steps, source_file)

    @staticmethod
    def _add_version(db, type_id, version, steps, source_file) -> int:
        return db.execute("INSERT INTO versions (type_id, version, status, steps, source_file) VALUES (?, ?, 'draft', ?, ?)",
                          (type_id, version, json.dumps(steps, ensure_ascii=False), source_file)).lastrowid

    def update_draft(self, version_id: int, steps: list) -> None:
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

    def list_types(self) -> list[dict]:
        """Newest approved version of each type."""
        with self._db() as db:
            rows = db.execute(self._VERSION_SQL + " WHERE v.status = 'approved' AND v.version = "
                              "(SELECT MAX(version) FROM versions WHERE type_id = v.type_id AND status = 'approved') ORDER BY t.name").fetchall()
        return [self._version(r) for r in rows]
