import math
from pathlib import Path

import pymupdf

from ingest import build_index
from store import Store


def fake_embed(texts):
    out = []
    for t in texts:
        v = [0.0] * 64
        for ch in t.lower():
            v[ord(ch) % 64] += 1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        out.append([x / n for x in v])
    return out


def make(tmp_path):
    content = tmp_path / "content"
    (content / "policy").mkdir(parents=True)
    (content / "forms" / "shareable").mkdir(parents=True)
    (content / "policy" / "leave.txt").write_text("annual leave is ten days per year", encoding="utf-8")
    (content / "forms" / "shareable" / "expense.txt").write_text("expense claim form for receipts", encoding="utf-8")
    return content, Store(tmp_path / "index", embed_fn=fake_embed)


def test_ingest_indexes_supported_and_skips_unsupported(tmp_path):
    content, store = make(tmp_path)
    (content / "data.xlsx").write_bytes(b"x")
    (content / ".DS_Store").write_bytes(b"x")
    result = build_index(content, store)
    assert result["indexed"] == 2
    assert any("data.xlsx" in s for s in result["skipped"])
    assert any(".DS_Store" in s for s in result["skipped"])


def test_empty_extraction_is_skipped_with_warning(tmp_path):
    content, store = make(tmp_path)
    doc = pymupdf.open()
    page = doc.new_page()
    page.draw_rect(pymupdf.Rect(50, 50, 200, 200), fill=(0, 0, 0))
    doc.save(content / "policy" / "scan.pdf")
    result = build_index(content, store)
    assert result["indexed"] == 2
    assert any("scan.pdf" in s for s in result["skipped"])
    assert all("scan.pdf" not in h.rel_path for h in store.query("anything", k=10))


def test_reingest_removes_deleted_file_chunks(tmp_path):
    content, store = make(tmp_path)
    build_index(content, store)
    (content / "policy" / "leave.txt").unlink()
    build_index(content, store)
    assert all("leave.txt" not in h.rel_path for h in store.query("annual leave", k=10))


def test_query_category_filter(tmp_path):
    content, store = make(tmp_path)
    build_index(content, store)
    hits = store.query("leave expense", k=10, category="forms")
    assert hits and all(h.category == "forms" for h in hits)


def test_metadata_roundtrip_and_doc_path(tmp_path):
    content, store = make(tmp_path)
    build_index(content, store)
    h = store.query("expense claim", k=1)[0]
    assert (h.category, h.downloadable) == ("forms", True)
    assert len(h.mtime) == 10 and h.text and 0 <= h.distance <= 2
    assert store.doc_path(h.doc_id) == "forms/shareable/expense.txt"
    assert store.doc_path("nope") is None


def test_categories_lists_indexed_categories(tmp_path):
    content, store = make(tmp_path)
    build_index(content, store)
    assert store.categories() == ["forms", "policy"]


def test_second_store_instance_survives_reingest_by_other_instance(tmp_path):
    content, store = make(tmp_path)
    build_index(content, store)
    other = Store(tmp_path / "index", embed_fn=fake_embed)
    build_index(content, other)
    assert store.query("annual leave", k=1) and store.categories() and store.doc_path("nope") is None


def test_failed_reingest_keeps_old_index(tmp_path):
    content, store = make(tmp_path)
    build_index(content, store)

    def boom(texts):
        raise RuntimeError("ollama down")

    broken = Store(tmp_path / "index", embed_fn=boom)
    try:
        build_index(content, broken)
    except RuntimeError:
        pass
    assert store.query("annual leave", k=1)


def test_find_files_matches_file_name_and_only_downloadable(tmp_path):
    content, store = make(tmp_path)
    build_index(content, store)
    hits = store.find_files("expense", 5)
    assert [h.rel_path for h in hits] == ["forms/shareable/expense.txt"]
    store.replace_all([])
    assert store.find_files("expense", 5) == []


def test_reindex_only_embeds_changed_files_and_drops_deleted(tmp_path):
    content, store = make(tmp_path)
    build_index(content, store)
    embedded = []
    counting = Store(tmp_path / "index", embed_fn=lambda texts: (embedded.extend(texts), fake_embed(texts))[1])

    assert build_index(content, counting)["changed"] == 0 and embedded == []

    (content / "policy" / "leave.txt").write_text("annual leave is now twelve days per year", encoding="utf-8")
    (content / "forms" / "shareable" / "expense.txt").unlink()
    r = build_index(content, counting)
    assert r["changed"] == 1 and r["indexed"] == 1
    assert all("leave" in t for t in embedded)  # only the edited file was embedded
    assert "twelve" in counting.query("leave", k=1)[0].text
    assert counting.find_files("expense", 5) == [] and counting.doc_path(next(iter(counting.signatures()))) == "policy/leave.txt"


def test_summary_is_made_once_per_new_file_and_used_for_name_search(tmp_path):
    content, store = make(tmp_path)
    seen = []
    def fake_summary(text):
        seen.append(text)
        return "ใบเบิกค่าใช้จ่าย"
    build_index(content, store, summarize=fake_summary)
    assert len(seen) == 2  # every file, so a file switched off keeps its description
    build_index(content, store, summarize=fake_summary)
    assert len(seen) == 2  # unchanged files are not summarized again
    assert "ใบเบิกค่าใช้จ่าย" in store._names.get()["documents"][0]


def test_failed_summary_does_not_stop_indexing(tmp_path):
    content, store = make(tmp_path)
    def boom(text):
        raise RuntimeError("api down")
    assert build_index(content, store, summarize=boom)["indexed"] == 2


def test_find_files_can_be_limited_to_a_topic_folder(tmp_path):
    content, store = make(tmp_path)
    build_index(content, store)
    assert [h.rel_path for h in store.find_files("expense", 5, "forms")] == ["forms/shareable/expense.txt"]
    assert store.find_files("expense", 5, "policy") == []


def test_topics_counts_downloadable_files_per_folder(tmp_path):
    content, store = make(tmp_path)
    build_index(content, store)
    assert store.topics() == {"forms": 1}


def test_summaries_drop_the_inline_keyword_list(tmp_path):
    content = tmp_path / "content"
    (content / "forms" / "shareable").mkdir(parents=True)
    (content / "forms" / "shareable" / "a.txt").write_text("annual leave form " * 10)
    store = Store(tmp_path / "index", embed_fn=fake_embed)
    build_index(content, store, summarize=lambda text: "แบบฟอร์มลา คำค้น: ลา, ใบลา")
    assert list(store.summaries().values()) == ["แบบฟอร์มลา"]


def test_summaries_returns_only_requested_downloadable_files(tmp_path):
    content = tmp_path / "content"
    (content / "forms" / "shareable").mkdir(parents=True)
    (content / "forms" / "shareable" / "a.txt").write_text("annual leave form " * 10)
    store = Store(tmp_path / "index", embed_fn=fake_embed)
    build_index(content, store, summarize=lambda text: "แบบฟอร์มลา\n\nคำค้น: ลา, ใบลา")
    everything = store.summaries()
    (doc_id, summary), = everything.items()
    assert summary == "แบบฟอร์มลา" and store.summaries([doc_id]) == everything
    assert store.summaries([]) == {} and store.summaries(["nope"]) == {}


def test_summary_survives_moving_a_file_in_and_out_of_shareable(tmp_path):
    content = tmp_path / "content"
    (content / "forms" / "shareable").mkdir(parents=True)
    f = content / "forms" / "shareable" / "a.txt"
    f.write_text("annual leave form " * 10)
    store = Store(tmp_path / "index", embed_fn=fake_embed)
    calls = []
    summarize = lambda text: calls.append(1) or "แบบฟอร์มลา"
    build_index(content, store, summarize)
    f.rename(content / "forms" / "a.txt")  # downloadable off: new path, same content
    build_index(content, store, summarize)
    (content / "forms" / "a.txt").rename(f)  # and on again
    build_index(content, store, summarize)
    assert len(calls) == 1 and list(store.summaries().values()) == ["แบบฟอร์มลา"]
    assert store.cached_summary("nope") == ""


def test_xlsx_and_pptx_are_indexed_like_other_documents(tmp_path):
    import openpyxl
    from pptx import Presentation
    content = tmp_path / "content"
    (content / "finance").mkdir(parents=True)
    wb = openpyxl.Workbook()
    wb.active.append(["รายการ", "จำนวนเงิน"])
    wb.active.append(["ค่าเดินทาง", 1500])
    wb.save(content / "finance" / "budget.xlsx")
    prs = Presentation()
    prs.slides.add_slide(prs.slide_layouts[5]).shapes.title.text = "แผนงาน"
    prs.save(content / "finance" / "plan.pptx")
    store = Store(tmp_path / "index", embed_fn=fake_embed)
    result = build_index(content, store)
    assert result["indexed"] == 2 and result["skipped"] == []
    assert {store.doc_path(i) for i in store.signatures()} == {"finance/budget.xlsx", "finance/plan.pptx"}
