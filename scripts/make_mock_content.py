"""Generate mock documents under content/. Dev helper only; real files replace these."""
from pathlib import Path

import fitz  # pymupdf
from docx import Document

ROOT = Path(__file__).resolve().parent.parent / "content"
FONT = "/System/Library/Fonts/Supplemental/Ayuthaya.ttf"

LEAVE_TH = [
    "นโยบายการลา บริษัท ตัวอย่าง จำกัด",
    "พนักงานมีสิทธิ์ลาพักร้อน 10 วันต่อปี หลังผ่านการทดลองงาน",
    "ลาป่วยได้ไม่เกิน 30 วันต่อปี หากลาเกิน 3 วันต้องแนบใบรับรองแพทย์",
    "ลากิจได้ 3 วันต่อปี ต้องแจ้งหัวหน้างานล่วงหน้าอย่างน้อย 2 วัน",
]


def thai_pdf(path: Path, lines: list[str]) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_font(fontname="th", fontfile=FONT)
    y = 72
    for line in lines:
        page.insert_text((60, y), line, fontname="th", fontsize=14)
        y += 28
    doc.save(path)


def docx(path: Path, lines: list[str]) -> None:
    d = Document()
    for line in lines:
        d.add_paragraph(line)
    d.save(path)


def main() -> None:
    thai_pdf(ROOT / "policy/leave-policy-th.pdf", LEAVE_TH)
    docx(ROOT / "policy/leave-policy-en.docx", [
        "Overtime Policy",
        "Overtime must be approved by a line manager in advance.",
        "Overtime is paid at 1.5 times the hourly rate on working days.",
    ])
    docx(ROOT / "forms/shareable/expense-claim-th.docx", [
        "แบบฟอร์มเบิกค่าใช้จ่าย",
        "กรอกชื่อพนักงาน วันที่ รายการ จำนวนเงิน และแนบใบเสร็จ",
        "ส่งแบบฟอร์มให้ฝ่ายบัญชีภายใน 7 วันหลังจากวันที่จ่ายเงิน",
    ])
    (ROOT / "projects/project-alpha-status.md").write_text(
        "# Project Alpha สถานะโครงการ\n\nอัปเดตเมื่อ 2026-10-01\n\n"
        "โครงการ Alpha คืบหน้า 60% ขณะนี้อยู่ในขั้นตอนทดสอบระบบ "
        "กำหนดส่งมอบวันที่ 30 พฤศจิกายน 2026\n",
        encoding="utf-8",
    )
    (ROOT / "general-notice.txt").write_text(
        "ประกาศ: สำนักงานปิดทำการวันหยุดนักขัตฤกษ์ทุกวัน เวลาทำการปกติ 09:00-18:00 น.\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
