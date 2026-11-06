"""LLM helpers for the tracking dashboard. The model is passed in (default rag.chat) so tests need no network."""
import json
import re

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
