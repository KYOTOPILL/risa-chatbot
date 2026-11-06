import json

import pymupdf
import pytest

from extract import extract_pages
from steps_ai import draft_steps

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
