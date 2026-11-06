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


# ---- Task 6: staff review ----
DSTEPS = [{"title": "Submit", "documents": ["Form A", "Form B"], "page": None, "unsure": False},
          {"title": "Review", "documents": [], "page": None, "unsure": False}]


@pytest.fixture
def docs(tk):
    v = tk.create_type("CMU", DSTEPS, "cmu.pdf")
    tk.approve(v)
    sid = tk.create_submission("S", v, ["r1"], "s1")

    def sent(doc, step=0):
        u = tk.add_upload(sid, step, doc, f"{doc}.pdf", f"/p/{doc}.pdf", [{"kind": "missing", "text": "x"}], "screened")
        tk.set_upload_status(u, "sent")
        return u
    return tk, sid, sent


def test_approve_one_of_two_documents_does_not_advance(docs):
    tk, sid, sent = docs
    assert tk.review_upload(sent("Form A"), "s1", "approve", [], "") is False
    assert tk.get_submission(sid, "s1", "staff")["current_step"] == 0


def test_approve_last_document_advances_exactly_one_step_and_logs_event(docs):
    tk, sid, sent = docs
    tk.review_upload(sent("Form A"), "s1", "approve", [], "")
    assert tk.review_upload(sent("Form B"), "s1", "approve", [], "") is True
    got = tk.get_submission(sid, "s1", "staff")
    assert got["current_step"] == 1 and [(e["from_step"], e["to_step"]) for e in got["events"]] == [(0, 1)]


def test_return_keeps_step_and_stores_note(docs):
    tk, sid, sent = docs
    u = sent("Form A")
    assert tk.review_upload(u, "s1", "return", [], "fix budget") is False
    assert tk.get_upload(u)["status"] == "returned" and tk.get_upload(u)["note"] == "fix budget"
    assert tk.get_submission(sid, "s1", "staff")["current_step"] == 0


def test_reupload_after_return_then_approve_advances(docs):
    tk, sid, sent = docs
    tk.review_upload(sent("Form A"), "s1", "return", [], "again")
    tk.review_upload(sent("Form A"), "s1", "approve", [], "")  # newer upload replaces the returned one
    assert tk.review_upload(sent("Form B"), "s1", "approve", [], "") is True


def test_review_by_other_staff_and_unsent_upload_rejected(docs):
    tk, sid, sent = docs
    u = sent("Form A")
    with pytest.raises(PermissionError):
        tk.review_upload(u, "s2", "approve", [], "")
    fresh = tk.add_upload(sid, 0, "Form B", "b.pdf", "/p/b.pdf", [], "screened")
    with pytest.raises(ValueError):
        tk.review_upload(fresh, "s1", "approve", [], "")
    with pytest.raises(ValueError):
        tk.review_upload(u, "s1", "maybe", [], "")


def test_dismissed_findings_stored(docs):
    tk, sid, sent = docs
    u = sent("Form A")
    tk.review_upload(u, "s1", "approve", [0], "advisor counted")
    assert tk.get_upload(u)["dismissed"] == [0]


def test_step_with_no_documents_never_auto_advances(docs):
    tk, sid, sent = docs
    tk.move_step(sid, "s1", 1)
    assert tk.review_upload(sent("Anything", step=1), "s1", "approve", [], "") is False
    assert tk.get_submission(sid, "s1", "staff")["current_step"] == 1


def test_review_queue_lists_only_sent(docs):
    tk, sid, sent = docs
    u = sent("Form A")
    tk.add_upload(sid, 0, "Form B", "b.pdf", "/p/b.pdf", [], "screened")
    q = tk.review_queue()
    assert [x["id"] for x in q] == [u] and q[0]["submission_title"] == "S" and q[0]["staff_id"] == "s1"


# ---- Final review fixes ----
@pytest.mark.parametrize("bad", [[], [{"title": ""}], [{"title": "a"}], [{"title": "a", "documents": "x"}],
                                 [{"title": "a", "documents": [""]}], "nope", [5]])
def test_malformed_steps_rejected_everywhere(tk, bad):
    with pytest.raises(ValueError):
        tk.create_type("X", bad, "x.pdf")
    v = tk.create_type("Y", STEPS, "y.pdf")
    with pytest.raises(ValueError):
        tk.update_draft(v, bad)
    with pytest.raises(ValueError):
        tk.new_version(tk.get_version(v)["type_id"], bad, "z.pdf")


def test_send_upload_only_from_screened_or_cannot_check(sub):
    tk, sid, _ = sub
    u = tk.add_upload(sid, 0, "Form A", "a.pdf", "/p", [], "screened")
    tk.send_upload(u)
    assert tk.get_upload(u)["status"] == "sent"
    for status in ("sent", "approved", "returned"):
        tk.set_upload_status(u, status)
        with pytest.raises(ValueError):
            tk.send_upload(u)  # never overwrites a staff decision


def test_stale_approval_does_not_log_a_second_advance(docs):
    tk, sid, sent = docs
    a, b = sent("Form A"), sent("Form B")
    tk.review_upload(a, "s1", "approve", [], "")
    real = tk.latest_uploads

    def racing(sid_, step):  # another request advances the submission just before ours does
        tk.latest_uploads = real
        tk.move_step(sid_, "s1", 1, "other request")
        return real(sid_, step)
    tk.latest_uploads = racing
    assert tk.review_upload(b, "s1", "approve", [], "") is False
    assert [e["to_step"] for e in tk.get_submission(sid, "s1", "staff")["events"]] == [1]
