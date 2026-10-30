from pathlib import Path

import pymupdf
import pytest

from extract import extract_text



def test_pdf_thai(mock_content):
    assert "ลาพักร้อน" in extract_text(mock_content / "policy/leave-policy-th.pdf")


def test_docx_english(mock_content):
    assert "Overtime" in extract_text(mock_content / "policy/leave-policy-en.docx")


def test_txt_and_md_utf8(mock_content):
    assert "ประกาศ" in extract_text(mock_content / "general-notice.txt")
    assert "Alpha" in extract_text(mock_content / "projects/project-alpha-status.md")


def test_unsupported_ext_raises(tmp_path):
    p = tmp_path / "a.xls"
    p.write_bytes(b"x")
    with pytest.raises(ValueError):
        extract_text(p)


def test_image_only_pdf_returns_empty(tmp_path):
    doc = pymupdf.open()
    page = doc.new_page()
    page.draw_rect(pymupdf.Rect(50, 50, 200, 200), fill=(0, 0, 0))
    p = tmp_path / "scan.pdf"
    doc.save(p)
    assert extract_text(p) == ""


def test_thai_private_use_glyphs_are_mapped_back():
    from extract import clean_thai

    raw = "ตองสมัคร ไม เปน ออนไลน  รายการ"
    assert clean_thai(raw) == "ต้องสมัคร ไม่ เป็น ออนไลน์ • รายการ"


def test_extract_text_cleans_thai_glyphs(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("ผาน", encoding="utf-8")
    assert extract_text(p) == "ผ่าน"


def test_split_sara_am_is_recomposed():
    from extract import clean_thai

    assert clean_thai("ส\u0e4d\u0e32คัญ ต\u0e4d\u0e32บล") == "สำคัญ ตำบล"


def test_xlsx_rows_keep_their_column_names_and_empty_rows_are_skipped(tmp_path):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "งบประมาณ"
    ws.append(["รายการ", "จำนวนเงิน"])
    ws.append([])
    ws.append(["ค่าเดินทาง", 1500])
    ws.append(["ค่าหนังสือ", None])
    wb.create_sheet("Notes").append(["Item", "Owner"])
    wb["Notes"].append(["Laptop", "Somchai"])
    p = tmp_path / "budget.xlsx"
    wb.save(p)
    rows = extract_text(p).split("\n\n")
    assert rows == ["[งบประมาณ] รายการ | จำนวนเงิน", "[งบประมาณ] รายการ: ค่าเดินทาง | จำนวนเงิน: 1500",
                    "[งบประมาณ] รายการ: ค่าหนังสือ", "[Notes] Item | Owner", "[Notes] Item: Laptop | Owner: Somchai"]


def test_pptx_text_tables_groups_and_notes_per_slide(tmp_path):
    from pptx import Presentation
    from pptx.util import Inches
    prs = Presentation()
    s1 = prs.slides.add_slide(prs.slide_layouts[5])
    s1.shapes.title.text = "แผนงานปี 2569"
    table = s1.shapes.add_table(2, 2, Inches(1), Inches(2), Inches(4), Inches(1)).table
    for (r, c), v in {(0, 0): "ไตรมาส", (0, 1): "เป้าหมาย", (1, 0): "Q1", (1, 1): "เปิดตัว"}.items():
        table.cell(r, c).text = v
    s1.notes_slide.notes_text_frame.text = "พูดช้าๆ"
    group = s1.shapes.add_group_shape()
    group.shapes.add_textbox(0, 0, Inches(1), Inches(1)).text_frame.text = "ข้อความในกลุ่ม"
    prs.slides.add_slide(prs.slide_layouts[6])  # empty slide: no paragraph
    p = tmp_path / "plan.pptx"
    prs.save(p)
    text = extract_text(p)
    assert text.startswith("Slide 1\nแผนงานปี 2569") and "ไตรมาส | เป้าหมาย" in text and "Q1 | เปิดตัว" in text
    assert "ข้อความในกลุ่ม" in text and "Notes: พูดช้าๆ" in text and "Slide 2" not in text


def test_docx_tables_are_read_in_order_with_merged_cells_once(tmp_path):
    from docx import Document
    d = Document()
    d.add_paragraph("before")
    t = d.add_table(rows=2, cols=3)
    t.cell(0, 0).text, t.cell(0, 1).text, t.cell(0, 2).text = "งบ", "จำนวน", "หมายเหตุ"
    t.cell(1, 0).merge(t.cell(1, 1)).text = "ค่าเดินทาง"
    t.cell(1, 2).text = "15,000"
    d.add_paragraph("after")
    d.save(tmp_path / "t.docx")
    assert extract_text(tmp_path / "t.docx") == "before\nงบ | จำนวน | หมายเหตุ\nค่าเดินทาง | 15,000\nafter"
