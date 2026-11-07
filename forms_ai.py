"""AI-drafted online forms: for a required document the model proposes the fields (text, number, date, choice, file) from the type guide. Staff edit and approve them."""
from pathlib import Path

from extract import extract_text
from rag import chat
from steps_ai import _json
from tracker import validate_form

FORM_PROMPT = (
    "You design an online form an applicant fills in on a website for ONE required document of a university research-administration request "
    "(grant, expense claim, approval, leave, etc). Base it on the guide text when it describes this document; otherwise use only what is reasonable, and do not invent policy. "
    'Answer with a JSON object only: {"title": form title, "fields": [{"label": field name, "hint": short help or empty string, '
    '"type": one of text|longtext|number|date|choice|file, "required": true or false, "options": [choices, only for type choice]}]}. '
    "Use file for anything the applicant must attach (signed copy, receipt, passport). Use number for amounts, date for dates, choice for a fixed list of 2 or more answers. "
    "4 to 15 fields, in the order a person would fill them. Write in the language of the document name."
)
GUIDE_CHARS = 6000


def draft_form(doc_name: str, step: dict, type_name: str, guide: Path | None = None, llm=chat) -> dict:
    ctx = f"Request type: {type_name}\nStep: {step['title']}\nOther documents in this step: {', '.join(d for d in step['documents'] if d != doc_name) or 'none'}\nDocument to make a form for: {doc_name}"
    try:
        text = extract_text(guide)[:GUIDE_CHARS] if guide else ""
    except Exception:  # a missing or unreadable guide only means less context
        text = ""
    if text:
        ctx += f"\n\nGuide text:\n{text}"
    form = _json(llm([{"role": "system", "content": FORM_PROMPT}, {"role": "user", "content": ctx}]))
    if not isinstance(form, dict):
        raise ValueError("bad form: expected a JSON object")
    title = form.get("title") if isinstance(form.get("title"), str) and form["title"].strip() else doc_name
    raw = form.get("fields") if isinstance(form.get("fields"), list) else []
    for f in raw:  # the model may name an unknown type; fall back to text rather than fail the whole draft
        if isinstance(f, dict) and f.get("type") == "choice" and len([o for o in f.get("options") or [] if isinstance(o, str) and o.strip()]) < 2:
            f["type"] = "text"
    raw = [{**f, "type": f.get("type") if f.get("type") in ("text", "longtext", "number", "date", "choice", "file") else "text"} for f in raw if isinstance(f, dict)]
    return {"title": title.strip(), "fields": validate_form(title, raw)}
