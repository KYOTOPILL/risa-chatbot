"""What the chat may tell a researcher about their own requests. Built only from that researcher's data."""
from app.core.config import MOCK_USERS

DOC_STATUS = {"draft": "บันทึกแบบร่างไว้ ยังกรอกไม่ครบและยังไม่ได้ส่ง", "screened": "AI ตรวจสอบแล้ว แต่ยังไม่ได้ส่งให้เจ้าหน้าที่", "cannot_check": "บันทึกแล้ว AI ตรวจสอบไม่ได้ ยังไม่ได้ส่งให้เจ้าหน้าที่",
              "sent": "ส่งแล้ว รอเจ้าหน้าที่ตรวจสอบ", "approved": "อนุมัติแล้ว"}


def _doc_line(name: str, up: dict | None) -> str:
    if up is None:
        return f"  - {name}: ยังไม่ได้ส่ง"
    if up["status"] == "returned":
        return f"  - {name}: เจ้าหน้าที่ส่งกลับให้แก้ไข ({up['note'] or 'ไม่มีหมายเหตุ'})"
    line = f"  - {name}: {DOC_STATUS[up['status']]}"
    if up["status"] in ("screened", "sent") and up["findings"]:
        line += " | ข้อสังเกตจาก AI: " + "; ".join(f["text"] for f in up["findings"][:3])
    return line


def describe(tk, user_id: str) -> str:
    subs = tk.list_submissions(user_id, "researcher")
    if not subs:
        return "ผู้ใช้ยังไม่มีงานที่เริ่มไว้"
    out = []
    for s in subs:
        d = tk.get_submission(s["id"], user_id, "researcher")
        staff = MOCK_USERS.get(d["staff_id"], {}).get("name", d["staff_id"])
        head = f"งาน: {d['title']} (ประเภท {d['type_name']}) เจ้าหน้าที่ผู้รับผิดชอบ: {staff}"
        if d["current_step"] >= d["step_count"]:
            out.append(head + "\n  ดำเนินการเสร็จสิ้น")
            continue
        step = d["steps"][d["current_step"]]
        by = {u["doc_name"]: u for u in d["uploads"]}
        later = [x["title"] for x in d["steps"][d["current_step"] + 1:]]
        out.append(head + f"\n  ขั้นตอนปัจจุบัน {d['current_step'] + 1}/{d['step_count']}: {step['title']}\n"
                   + ("\n".join(_doc_line(n, by.get(n)) for n in step["documents"]) or "  ขั้นตอนนี้ไม่ต้องส่งเอกสาร")
                   + (f"\n  ขั้นตอนถัดไป: {', '.join(later)}" if later else ""))
    return "\n\n".join(out)
