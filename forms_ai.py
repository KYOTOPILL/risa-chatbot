"""AI-made blank forms: for a required document that has no official template, the model lists the fields and we build a .docx."""
from pathlib import Path

from docx import Document

from rag import chat
from steps_ai import _json

NOTICE = "แบบฟอร์มนี้ร่างโดย AI ใช้เป็นแนวทาง กรุณาตรวจกับแบบฟอร์มทางการของหน่วยงานก่อนส่ง"
FORM_PROMPT = (
    "You design a blank form an applicant fills in for ONE required document of a university research-administration request "
    "(grant, expense claim, approval, leave, etc). Use only what is reasonable for that document; do not invent policy. "
    'Answer with a JSON object only: {"title": form title, "fields": [{"label": field name, "hint": short help or empty string}]}. '
    "5 to 15 fields, in the order a person would fill them. Write in the language of the document name."
)


def draft_form(doc_name: str, step: dict, type_name: str, llm=chat) -> dict:
    ctx = f"Request type: {type_name}\nStep: {step['title']}\nOther documents in this step: {', '.join(d for d in step['documents'] if d != doc_name) or 'none'}\nDocument to make a form for: {doc_name}"
    form = _json(llm([{"role": "system", "content": FORM_PROMPT}, {"role": "user", "content": ctx}]))
    fields = form.get("fields") if isinstance(form, dict) else None
    if not isinstance(fields, list) or not fields or any(not isinstance(f, dict) or not isinstance(f.get("label"), str) or not f["label"].strip() for f in fields):
        raise ValueError("bad form: expected a title and a non-empty list of fields with labels")
    title = form.get("title") if isinstance(form.get("title"), str) and form["title"].strip() else doc_name
    return {"title": title.strip(), "fields": [{"label": f["label"].strip(), "hint": f.get("hint") if isinstance(f.get("hint"), str) else ""} for f in fields]}


def build_docx(form: dict, path) -> None:  # path: a file path or any binary file object
    doc = Document()
    doc.add_heading(form["title"], level=1)
    doc.add_paragraph(NOTICE)
    table = doc.add_table(rows=0, cols=2)
    table.style = "Table Grid"
    for f in form["fields"]:
        row = table.add_row().cells
        row[0].text = f["label"] + (f"\n({f['hint']})" if f["hint"] else "")
    doc.add_paragraph()
    doc.add_paragraph("ลงชื่อ ______________________________    วันที่ ____________________")
    if isinstance(path, Path):
        path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)
