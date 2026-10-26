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
    p = tmp_path / "a.xlsx"
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
