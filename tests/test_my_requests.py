import my_requests
from tracker import Tracker

STEPS = [{"title": "Submit", "documents": ["Form A", "Passport"], "page": 1, "unsure": False}, {"title": "Sign", "documents": [], "page": 1, "unsure": False}]


def make(tmp_path):
    tk = Tracker(tmp_path / "t.db")
    v = tk.create_type("Grant", STEPS, "g.pdf")
    tk.approve(v)
    return tk, v


def test_no_requests(tmp_path):
    tk, _ = make(tmp_path)
    assert "ยังไม่มีงาน" in my_requests.describe(tk, "r1")


def test_describes_step_documents_and_staff_for_this_researcher_only(tmp_path):
    tk, v = make(tmp_path)
    sid = tk.create_submission("Grant - Somchai", v, ["r1"], "s2")
    tk.create_submission("Grant - Nida", v, ["r2"], "s1")
    tk.add_upload(sid, 0, "Form A", "a.pdf", "/x/a.pdf", [{"kind": "missing", "text": "no budget"}], "screened")
    tk.add_upload(sid, 0, "Passport", "p.pdf", "/x/p.pdf", None, "returned")
    text = my_requests.describe(tk, "r1")
    assert "Grant - Somchai" in text and "Anan" in text and "ขั้นตอนปัจจุบัน 1/2: Submit" in text
    assert "Form A: AI ตรวจสอบแล้ว" in text and "no budget" in text and "Passport: เจ้าหน้าที่ส่งกลับให้แก้ไข" in text and "ขั้นตอนถัดไป: Sign" in text
    assert "Nida" not in text  # never another researcher's request


def test_completed_request(tmp_path):
    tk, v = make(tmp_path)
    sid = tk.create_submission("Done", v, ["r1"], "s1")
    tk.move_step(sid, "s1", 2)
    assert "ดำเนินการเสร็จสิ้น" in my_requests.describe(tk, "r1")
