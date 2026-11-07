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


def call(fn, *args):
    code = f"console.log(JSON.stringify(require({json.dumps(str(JS))}).{fn}(...{json.dumps(list(args))})))"
    return json.loads(subprocess.run(["node", "-e", code], capture_output=True, text=True, check=True).stdout)


NOW = "2026-11-10T12:00:00Z"


def test_staff_stats_counts_waiting_active_and_old():
    queue = [{"created": "2026-11-09 12:00:00"}, {"created": "2026-11-01 08:00:00"}]  # 1 day old, 9 days old
    subs = [{"current_step": 0, "step_count": 3}, {"current_step": 3, "step_count": 3}]  # second one is finished
    assert call("staffStats", queue, subs, NOW) == {"waiting": 2, "active": 1, "old": 1}


def test_staff_stats_when_nothing_exists():
    assert call("staffStats", [], [], NOW) == {"waiting": 0, "active": 0, "old": 0}


def test_ago_text_in_thai_units():
    assert call("agoText", "2026-11-10 11:59:30", NOW) == "เมื่อสักครู่"
    assert call("agoText", "2026-11-10 09:00:00", NOW) == "3 ชั่วโมงก่อน"
    assert call("agoText", "2026-11-09 12:00:00", NOW) == "เมื่อวาน"
    assert call("agoText", "2026-11-05 12:00:00", NOW) == "5 วันก่อน"
