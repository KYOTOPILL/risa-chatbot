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
