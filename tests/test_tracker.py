import pytest

from tracker import Tracker

STEPS = [{"title": "Submit", "documents": ["Form A"], "page": 1, "unsure": False}]


@pytest.fixture
def tk(tmp_path):
    return Tracker(tmp_path / "t.db")


def test_new_type_is_a_draft_and_not_listed(tk):
    v = tk.create_type("CMU", STEPS, "cmu.pdf")
    assert tk.get_version(v)["status"] == "draft"
    assert tk.list_types() == []


def test_approve_lists_the_type(tk):
    v = tk.create_type("CMU", STEPS, "cmu.pdf")
    tk.approve(v)
    assert [t["id"] for t in tk.list_types()] == [v]


def test_update_draft_rejected_after_approval(tk):
    v = tk.create_type("CMU", STEPS, "cmu.pdf")
    tk.approve(v)
    with pytest.raises(ValueError):
        tk.update_draft(v, [])


def test_new_version_does_not_replace_approved_until_approved(tk):
    v1 = tk.create_type("CMU", STEPS, "cmu.pdf")
    tk.approve(v1)
    v2 = tk.new_version(tk.get_version(v1)["type_id"], STEPS, "cmu2.pdf")
    assert [t["id"] for t in tk.list_types()] == [v1]
    tk.approve(v2)
    listed = tk.list_types()
    assert [t["id"] for t in listed] == [v2] and listed[0]["version"] == 2


STEPS3 = [{"title": t, "documents": [], "page": None, "unsure": False} for t in ("Submit", "Review", "Sign")]


@pytest.fixture
def sub(tk):
    """(tracker, submission id) for r1 only, staff s1 in charge, on an approved 3-step type."""
    v = tk.create_type("CMU", STEPS3, "cmu.pdf")
    tk.approve(v)
    return tk, tk.create_submission("Somchai CMU", v, ["r1"], "s1"), v


def test_create_submission_needs_approved_version_and_researchers(tk):
    v = tk.create_type("CMU", STEPS3, "cmu.pdf")
    with pytest.raises(ValueError):
        tk.create_submission("x", v, ["r1"], "s1")  # still a draft
    tk.approve(v)
    with pytest.raises(ValueError):
        tk.create_submission("x", v, [], "s1")


def test_researcher_sees_only_own(sub):
    tk, sid, v = sub
    tk.create_submission("Nida CMU", v, ["r2"], "s1")
    assert [s["id"] for s in tk.list_submissions("r1", "researcher")] == [sid]


def test_shared_submission_visible_to_all_its_researchers(tk):
    v = tk.create_type("CMU", STEPS3, "cmu.pdf")
    tk.approve(v)
    sid = tk.create_submission("Team", v, ["r1", "r2"], "s1")
    for r in ("r1", "r2"):
        assert tk.get_submission(sid, r, "researcher")["id"] == sid


def test_other_researchers_submission_is_none(sub):
    tk, sid, _ = sub
    assert tk.get_submission(sid, "r2", "researcher") is None
    assert tk.get_submission(999, "r1", "researcher") is None


def test_staff_sees_all_but_only_in_charge_moves(sub):
    tk, sid, v = sub
    tk.create_submission("Other", v, ["r2"], "s2")
    assert len(tk.list_submissions("s2", "staff")) == 2
    with pytest.raises(PermissionError):
        tk.move_step(sid, "s2", 1)
    tk.move_step(sid, "s1", 1)
    got = tk.get_submission(sid, "s1", "staff")
    assert got["current_step"] == 1 and len(got["events"]) == 1


def test_move_step_bounds_and_backward(sub):
    tk, sid, _ = sub
    for bad in (-1, 4):
        with pytest.raises(ValueError):
            tk.move_step(sid, "s1", bad)
    tk.move_step(sid, "s1", 2)
    tk.move_step(sid, "s1", 1)
    got = tk.get_submission(sid, "s1", "staff")
    assert got["current_step"] == 1 and [e["to_step"] for e in got["events"]] == [2, 1]


def test_in_flight_submission_keeps_its_version(sub):
    tk, sid, v = sub
    v2 = tk.new_version(tk.get_version(v)["type_id"], STEPS, "cmu2.pdf")
    tk.approve(v2)
    assert len(tk.get_submission(sid, "s1", "staff")["steps"]) == 3


def test_list_drafts_returns_only_drafts(tk):
    v1 = tk.create_type("A", STEPS, "a.pdf")
    tk.approve(v1)
    v2 = tk.create_type("B", STEPS, "b.pdf")
    assert [d["id"] for d in tk.list_drafts()] == [v2]


# ---- Task 5: uploads ----
def test_uploads_latest_wins_and_status_changes(sub):
    tk, sid, _ = sub
    u1 = tk.add_upload(sid, 0, "Form A", "a.pdf", "/p/a.pdf", [{"kind": "missing", "text": "x"}], "screened")
    u2 = tk.add_upload(sid, 0, "Form A", "a2.pdf", "/p/a2.pdf", [], "screened")
    assert tk.latest_uploads(sid, 0)["Form A"]["id"] == u2
    tk.set_upload_status(u2, "sent")
    got = tk.get_upload(u2)
    assert got["status"] == "sent" and got["submission_id"] == sid and got["findings"] == []
    assert tk.get_upload(u1)["findings"][0]["kind"] == "missing"
    assert tk.get_upload(999) is None
    with pytest.raises(ValueError):
        tk.set_upload_status(u2, "bogus")
