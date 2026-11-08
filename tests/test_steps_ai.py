import json

import pymupdf
import pytest

from app.rag.extract import extract_pages
from app.features.steps_ai import draft_steps

GOOD = json.dumps([
    {"title": "ยื่นใบสมัคร", "documents": ["transcript"], "page": 2, "unsure": False},
    {"title": "พิจารณา", "page": 3, "unsure": True},
], ensure_ascii=False)


class FakeLLM:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def __call__(self, messages):
        self.calls.append(messages)
        return self.reply


def test_draft_parses_steps_with_pages_and_unsure():
    steps = draft_steps(["a", "b"], llm=FakeLLM(GOOD))
    assert steps[0] == {"title": "ยื่นใบสมัคร", "documents": ["transcript"], "page": 2, "unsure": False}
    assert steps[1] == {"title": "พิจารณา", "documents": [], "page": 3, "unsure": True}


def test_draft_accepts_json_fence():
    assert len(draft_steps(["a"], llm=FakeLLM("```json\n" + GOOD + "\n```"))) == 2


@pytest.mark.parametrize("reply", ["sorry, no", "[]", '{"title": "x"}', '[{"documents": []}]', '[{"title": 5}]'])
def test_draft_rejects_garbage_empty_and_wrong_shape(reply):
    with pytest.raises(ValueError):
        draft_steps(["a"], llm=FakeLLM(reply))


def test_draft_prompt_contains_page_markers():
    llm = FakeLLM(GOOD)
    draft_steps(["first page", "second page"], llm=llm)
    user = llm.calls[0][-1]["content"]
    assert "[page 1]\nfirst page" in user and "[page 2]\nsecond page" in user


def test_extract_pages_one_entry_per_pdf_page(tmp_path):
    p = tmp_path / "two.pdf"
    doc = pymupdf.open()
    for text in ("alpha", "beta"):
        doc.new_page().insert_text((72, 72), text)
    doc.save(p)
    pages = extract_pages(p)
    assert len(pages) == 2 and "alpha" in pages[0] and "beta" in pages[1]


def test_extract_pages_non_pdf_is_single_page(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("hello")
    assert extract_pages(p) == ["hello"]


# ---- Task 5: screening ----
from app.features.steps_ai import find_template, screen_document

STEP = {"title": "Submit", "documents": ["Proposal", "Budget"], "page": 1, "unsure": False}
FINDINGS = json.dumps([{"kind": "missing", "text": "Budget section empty"}, {"kind": "unclear", "text": "Dates odd"}])


def test_screen_parses_findings_and_rejects_bad_kind():
    got = screen_document("text", STEP, "Proposal", None, llm=FakeLLM(FINDINGS))
    assert got == [{"kind": "missing", "text": "Budget section empty"}, {"kind": "unclear", "text": "Dates odd"}]
    assert screen_document("text", STEP, "Proposal", None, llm=FakeLLM("[]")) == []  # clean document is valid
    for bad in ("nope", '[{"kind": "bad", "text": "x"}]', '[{"kind": "missing"}]', '{"kind": "missing"}'):
        with pytest.raises(ValueError):
            screen_document("text", STEP, "Proposal", None, llm=FakeLLM(bad))


def test_screen_prompt_includes_step_documents_and_template_when_given():
    llm = FakeLLM("[]")
    screen_document("UPLOADED BODY", STEP, "Proposal", "TEMPLATE BODY", llm=llm)
    sent = " ".join(m["content"] for m in llm.calls[0])
    assert "Proposal" in sent and "Budget" in sent and "UPLOADED BODY" in sent and "TEMPLATE BODY" in sent
    llm2 = FakeLLM("[]")
    screen_document("UPLOADED BODY", STEP, "Proposal", None, llm=llm2)
    assert "TEMPLATE BODY" not in " ".join(m["content"] for m in llm2.calls[0])


def test_find_template_matches_stem_and_returns_none(tmp_path):
    d = tmp_path / "Form template" / "shareable"
    d.mkdir(parents=True)
    (d / "04_Proposal_template.docx").write_bytes(b"x")
    (tmp_path / "Proposal_elsewhere.docx").write_bytes(b"x")  # not in a Form template folder
    assert find_template("proposal", tmp_path) == d / "04_Proposal_template.docx"
    assert find_template("budget", tmp_path) is None


def test_screen_keeps_field_and_fix_sorts_by_kind_and_caps_at_eight():
    import json
    from app.features.steps_ai import screen_document
    items = [{"kind": "unclear", "text": " vague "}, {"kind": "missing", "field": "Budget", "text": "absent", "fix": "add it"}] + [{"kind": "incorrect", "text": f"x{i}"} for i in range(9)]
    out = screen_document("t", {"title": "S", "documents": ["D"]}, "D", None, llm=lambda m: json.dumps(items))
    assert len(out) == 8 and out[0] == {"kind": "missing", "text": "absent", "field": "Budget", "fix": "add it"}
    assert [f["kind"] for f in out].count("unclear") == 0 and "field" not in out[1]  # 8 kept: missing first, then incorrect; unclear fell off the cap
