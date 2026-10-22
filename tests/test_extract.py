from pathlib import Path

import pymupdf
import pytest

from extract import extract_text

C = Path("content")


def test_pdf_thai():
    assert "ลาพักร้อน" in extract_text(C / "policy/leave-policy-th.pdf")


def test_docx_english():
    assert "Overtime" in extract_text(C / "policy/leave-policy-en.docx")


def test_txt_and_md_utf8():
    assert "ประกาศ" in extract_text(C / "general-notice.txt")
    assert "Alpha" in extract_text(C / "projects/project-alpha-status.md")


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
