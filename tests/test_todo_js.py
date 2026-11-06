import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
JS = Path(__file__).resolve().parent.parent / "web" / "todo.js"


def run(subs):
    code = f"console.log(JSON.stringify(require({json.dumps(str(JS))}).todoItems({json.dumps(subs)})))"
    return json.loads(subprocess.run(["node", "-e", code], capture_output=True, text=True, check=True).stdout)


def sub(sid, uploads):
    return {"id": sid, "current_step": 0, "steps": [{"title": "S", "documents": ["Form A"]}], "uploads": uploads}


def up(status, id_=1, note=""):
    return {"id": id_, "doc_name": "Form A", "status": status, "step_index": 0, "note": note}


def test_empty_when_nothing_pending():
    assert run([sub(1, [up("approved")]), sub(2, [])]) == []


def test_returned_comes_before_waiting_across_submissions():
    got = run([sub(1, [up("sent")]), sub(2, [up("returned", note="fix")])])
    assert [(g["kind"], g["sub"]["id"]) for g in got] == [("returned", 2), ("waiting", 1)]
    assert got[0]["note"] == "fix"


def test_only_latest_upload_per_document_counts():
    got = run([sub(1, [up("returned", id_=1), up("sent", id_=2)])])
    assert [g["kind"] for g in got] == ["waiting"]
