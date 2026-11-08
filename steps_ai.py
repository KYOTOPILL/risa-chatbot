"""LLM helpers for the tracking dashboard. The model is passed in (default rag.chat) so tests need no network."""
import json
import re

from pathlib import Path

from app.core.config import CONTENT_DIR
from rag import chat

DRAFT_PROMPT = (
    "You read a document that describes how to apply for a scholarship or research funding. "
    "List the application steps in order. Answer with a JSON array only, no other text. Each item: "
    '{"title": step name, "documents": [documents the applicant must prepare for this step], '
    '"page": page number the step comes from, "unsure": true if the step or its documents are not clearly stated}. '
    "Write titles and documents in the document's own language."
)


def _json(reply: str):
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", reply.strip())
    try:
        return json.loads(text)
    except ValueError:
        raise ValueError("bad draft: model did not return JSON")


def draft_steps(pages: list[str], llm=chat) -> list[dict]:
    body = "\n\n".join(f"[page {n}]\n{t}" for n, t in enumerate(pages, 1))
    items = _json(llm([{"role": "system", "content": DRAFT_PROMPT}, {"role": "user", "content": body}]))
    if not isinstance(items, list) or not items:
        raise ValueError("bad draft: expected a non-empty list")
    steps = []
    for it in items:
        if not isinstance(it, dict) or not isinstance(it.get("title"), str) or not it["title"].strip():
            raise ValueError("bad draft: step without a title")
        docs = it.get("documents")
        page = it.get("page")
        steps.append({"title": it["title"].strip(),
                      "documents": [d for d in docs if isinstance(d, str)] if isinstance(docs, list) else [],
                      "page": page if isinstance(page, int) else None,
                      "unsure": it.get("unsure") is True})
    return steps


SCREEN_PROMPT = (
    "You do a quick quality check of a document an applicant submitted for a scholarship or funding step. It is a check of completeness and basic logic, "
    "not a decision: staff decide whether the content makes sense. Report ONLY these: "
    '"missing" (a required field or part is empty, or something the step requires is absent); '
    '"incorrect" (a plain error anyone can see: placeholder or meaningless text such as "test" or "123" where a name or description is expected, a wrong format, '
    "an end date before its start date, numbers that contradict each other inside the document such as a total that is not the sum of its parts); "
    '"unclear" (text that cannot be read or understood). '
    "Do NOT judge whether amounts, dates, reasons, plans or choices are sensible, sufficient, allowed or fit the funder's rules. "
    "Do NOT ask for more justification or detail, and do NOT compare figures against each other unless they must be equal or must add up. "
    "If you are not sure it is a plain error, do not report it. "
    'Answer with a JSON array only: [{"kind": "missing"|"incorrect"|"unclear", "field": the name of the one field or section concerned (short, optional), '
    '"text": ONE sentence, at most 120 characters, saying what is wrong, "fix": what the applicant should do, at most 80 characters (optional)}]. '
    "One finding per problem, merge findings that say the same thing, at most 8, most important first. "
    "Do not repeat the field name inside the text. Answer [] if there are no problems. Write in the document's own language."
)
KINDS = {"missing", "incorrect", "unclear"}


def find_template(doc_name: str, content_dir: Path = CONTENT_DIR) -> Path | None:
    # ponytail: substring match on the file name, use an explicit template link on the step if names stop matching
    for p in sorted(content_dir.rglob("*")):
        if p.is_file() and "Form template" in p.relative_to(content_dir).parts and doc_name.lower() in p.stem.lower():
            return p
    return None


def screen_document(text: str, step: dict, doc_name: str, template_text: str | None, llm=chat) -> list[dict]:
    parts = [f"Step: {step['title']}", f"Documents required in this step: {', '.join(step['documents'])}",
             f"Document being checked: {doc_name}"]
    if template_text:
        parts.append(f"Blank form template for it:\n{template_text}")
    parts.append(f"Uploaded document:\n{text}")
    items = _json(llm([{"role": "system", "content": SCREEN_PROMPT}, {"role": "user", "content": "\n\n".join(parts)}]))
    if not isinstance(items, list) or any(not isinstance(i, dict) or i.get("kind") not in KINDS or not isinstance(i.get("text"), str) for i in items):
        raise ValueError("bad screening result")
    order = {"missing": 0, "incorrect": 1, "unclear": 2}
    out = [{"kind": i["kind"], "text": i["text"].strip(), **{k: i[k].strip() for k in ("field", "fix") if isinstance(i.get(k), str) and i[k].strip()}} for i in items]
    return sorted(out, key=lambda f: order[f["kind"]])[:8]  # sorted is stable: the model's own order holds within a kind
