from app.core.config import HR_CONTACT
from evals.run_eval import check, run
from rag import Reply

THAI = "ลาพักร้อน 10 วัน"


def fake(text, files=()):
    return lambda history, q: Reply(text, list(files))


def one(q, answer_fn):
    return run([q], answer_fn)[0]


def test_passing_case():
    assert one({"q": "x", "must_include": ["10"]}, fake(THAI)).passed


def test_missing_must_include_fails():
    assert not one({"q": "x", "must_include": ["99"]}, fake(THAI)).passed


def test_present_must_not_include_fails():
    assert not one({"q": "x", "must_not_include": ["10"]}, fake(THAI)).passed


def test_wrong_expect_file_fails():
    assert not one({"q": "x", "expect_file": True}, fake(THAI)).passed
    assert one({"q": "x", "expect_file": True}, fake(THAI, ["d"])).passed


def test_expect_not_found():
    assert one({"q": "x", "expect_not_found": True}, fake(f"ไม่พบ {HR_CONTACT}")).passed
    assert not one({"q": "x", "expect_not_found": True}, fake(THAI)).passed


def test_english_answer_fails():
    assert not one({"q": "x"}, fake("Ten days of leave.")).passed


def test_expect_files_matches_names_exactly():
    reply = Reply(THAI, ["a", "b"])
    case = {"q": "x", "expect_files": ["alpha", "beta"]}
    assert not check(case, reply, ["Alpha.pdf"]) == []
    assert check(case, reply, ["Alpha.pdf", "beta.pdf"]) == []
    assert check(case, reply, ["Alpha.pdf", "beta.pdf", "gamma.pdf"]) == ["unexpected file 'gamma.pdf'"]
    assert check({"q": "x", "expect_files": []}, Reply(THAI), []) == []
