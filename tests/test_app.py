from pathlib import Path
from unittest.mock import patch

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import rag


class FakeStore:
    pass


@pytest.fixture(autouse=True)
def fresh_cache():
    st.cache_resource.clear()


def new_app():
    return AppTest.from_file(str(Path(__file__).resolve().parent.parent / "app.py"), default_timeout=10).run()


def texts(at):
    return [m.markdown[0].value for m in at.chat_message]


def test_empty_input_ignored():
    with patch("store.Store", FakeStore), patch("rag.answer") as ans:
        at = new_app()
        at.chat_input[0].set_value("   ").run()
        assert not at.chat_message and ans.call_count == 0


def test_reply_shown():
    with patch("store.Store", FakeStore), patch("rag.answer", return_value=rag.Reply("ลาพักร้อน 10 วัน", [], ["policy/leave.pdf"])):
        at = new_app()
        at.chat_input[0].set_value("ลากี่วัน").run()
        assert texts(at) == ["ลากี่วัน", "ลาพักร้อน 10 วัน"]


def test_two_sessions_do_not_share_history():
    with patch("store.Store", FakeStore), patch("rag.answer", return_value=rag.Reply("ตอบ")):
        a, b = new_app(), new_app()
        a.chat_input[0].set_value("คำถามของ A").run()
        b.chat_input[0].set_value("คำถามของ B").run()
        assert "คำถามของ B" not in texts(a) and "คำถามของ A" not in texts(b)


def test_history_passed_to_answer_for_followup():
    with patch("store.Store", FakeStore), patch("rag.answer", return_value=rag.Reply("ตอบ")) as ans:
        at = new_app()
        at.chat_input[0].set_value("คำถามแรก").run()
        at.chat_input[0].set_value("แล้วอันที่สองล่ะ").run()
        history = ans.call_args.args[0]
        assert [t.content for t in history] == ["คำถามแรก", "ตอบ"]


def test_download_button_only_for_file_doc_ids(tmp_path):
    f = tmp_path / "form.txt"
    f.write_text("x", encoding="utf-8")
    with patch("store.Store", FakeStore), patch("downloads.resolve_download", return_value=f):
        with patch("rag.answer", return_value=rag.Reply("นี่คือแบบฟอร์ม", ["abc"])):
            at = new_app()
            at.chat_input[0].set_value("ขอแบบฟอร์ม").run()
            assert len(at.get("download_button")) == 1
        with patch("rag.answer", return_value=rag.Reply("ลา 10 วัน", [])):
            at2 = new_app()
            at2.chat_input[0].set_value("ลากี่วัน").run()
            assert len(at2.get("download_button")) == 0


def test_no_file_name_in_rendered_page(tmp_path):
    f = tmp_path / "secret-form.txt"
    f.write_text("x", encoding="utf-8")
    with patch("store.Store", FakeStore), patch("downloads.resolve_download", return_value=f), \
            patch("rag.answer", return_value=rag.Reply("นี่คือแบบฟอร์ม", ["abc"], ["forms/shareable/secret-form.txt"])):
        at = new_app()
        at.chat_input[0].set_value("ขอแบบฟอร์ม").run()
        rendered = " ".join(str(e.value) for e in at.markdown) + " ".join(str(b.proto.label) for b in at.get("download_button"))
        assert "secret-form" not in rendered


def test_source_logging_is_enabled():
    import logging

    with patch("store.Store", FakeStore), patch("rag.answer", return_value=rag.Reply("ตอบ")):
        new_app()
    assert logging.getLogger("chatbot").getEffectiveLevel() <= logging.INFO


def test_ollama_error_shows_thai_message_and_no_dangling_turn():
    with patch("store.Store", FakeStore), patch("rag.answer", side_effect=RuntimeError("ollama down")):
        at = new_app()
        at.chat_input[0].set_value("ลากี่วัน").run()
        assert len(at.error) == 1
        assert at.session_state["msgs"] == []
