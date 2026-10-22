from chunk import chunk_text


def test_chunks_nonempty_and_overlap():
    text = "\n\n".join(f"Paragraph {i} " + "word " * 30 for i in range(10))
    chunks = chunk_text(text, size=200, overlap=40)
    assert len(chunks) > 1
    assert all(c.strip() for c in chunks)
    assert all(len(c) <= 200 for c in chunks)
    assert chunks[0][-20:] in chunks[1]


def test_thai_text_without_spaces_still_splits():
    text = "นโยบายการลาพักร้อน" * 100
    chunks = chunk_text(text, size=200, overlap=20)
    assert len(chunks) > 1
    assert all(0 < len(c) <= 200 for c in chunks)


def test_short_text_single_chunk_and_blank_text_none():
    assert chunk_text("hello", size=200, overlap=20) == ["hello"]
    assert chunk_text("  \n ", size=200, overlap=20) == []
