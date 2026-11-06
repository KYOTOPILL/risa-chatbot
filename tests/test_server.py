import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import rag
import server
import state


class FakeStore:
    def doc_path(self, doc_id):
        return "policy/ใบลา.pdf"

    def summaries(self, ids=None):
        return {"abc": "แบบฟอร์มใบลา"}


@pytest.fixture(autouse=True)
def clean_cache():
    state.cache.clear()
    yield
    state.cache.clear()


@pytest.fixture
def client():
    with patch.object(state, "get_store", return_value=FakeStore()):
        yield TestClient(server.app)


def post(client, message="ลากี่วัน", history=None):
    return client.post("/api/chat", json={"message": message, "history": history or []})


def test_chat_questions_run_in_parallel(client):
    import threading
    import time

    running = peak = 0
    guard = threading.Lock()

    def slow_answer(history, message, store):
        nonlocal running, peak
        with guard:
            running += 1
            peak = max(peak, running)
        time.sleep(0.3)
        with guard:
            running -= 1
        return rag.Reply("ok")

    with patch("rag.answer", slow_answer):
        threads = [threading.Thread(target=post, args=(client, f"q{i}")) for i in range(4)]
        [t.start() for t in threads]
        [t.join() for t in threads]
    assert peak > 1


def test_one_ip_cannot_flood_but_can_keep_asking(client, monkeypatch):
    import threading
    import time

    monkeypatch.setattr("config.MAX_INFLIGHT", 2)
    codes = []

    def slow(history, message, store):
        time.sleep(0.3)
        return rag.Reply("ok")

    with patch("rag.answer", slow):
        ts = [threading.Thread(target=lambda i=i: codes.append(post(client, f"q{i}").status_code)) for i in range(5)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        assert sorted(codes) == [200, 200, 429, 429, 429]  # only 2 at once from one IP
        assert [post(client, f"later{i}").status_code for i in range(5)] == [200] * 5  # one after another is never limited
    assert state._busy == {}


def test_chat_returns_text_and_file_ids(client):
    with patch("rag.answer", return_value=rag.Reply("ลาพักร้อน 10 วัน", ["abc"], ["policy/leave.pdf"])):
        r = post(client)
    assert r.status_code == 200
    assert r.json() == {"text": "ลาพักร้อน 10 วัน", "files": [{"id": "abc", "name": "ใบลา.pdf", "summary": "แบบฟอร์มใบลา", "size": None}]}


def test_file_size_comes_from_the_content_folder(client, tmp_path):
    (tmp_path / "policy").mkdir()
    (tmp_path / "policy" / "ใบลา.pdf").write_bytes(b"x" * 2048)
    with patch("rag.answer", return_value=rag.Reply("ตอบ", ["abc"])), patch.object(server, "CONTENT_DIR", tmp_path):
        assert post(client).json()["files"][0]["size"] == 2048


def test_response_never_contains_sources(client):
    with patch("rag.answer", return_value=rag.Reply("ตอบ", [], ["policy/secret.pdf"])):
        assert "secret" not in post(client).text


def test_history_is_passed_as_turns(client):
    hist = [{"role": "user", "content": "คำถามแรก"}, {"role": "assistant", "content": "ตอบแรก"}]
    with patch("rag.answer", return_value=rag.Reply("ตอบ")) as ans:
        post(client, history=hist)
    assert [(t.role, t.content) for t in ans.call_args.args[0]] == [("user", "คำถามแรก"), ("assistant", "ตอบแรก")]


def test_blank_message_rejected_without_model_call(client):
    with patch("rag.answer") as ans:
        assert post(client, message="   ").status_code == 422
    assert ans.call_count == 0


def test_bad_role_or_oversized_input_rejected(client):
    assert post(client, history=[{"role": "system", "content": "x"}]).status_code == 422
    assert post(client, message="ก" * 2001).status_code == 422
    assert post(client, history=[{"role": "user", "content": "x"}] * 13).status_code == 422


def test_model_error_returns_thai_503(client):
    with patch("rag.answer", side_effect=RuntimeError("ollama down")):
        r = post(client)
    assert r.status_code == 503 and "ขัดข้อง" in r.json()["text"]


def test_download_uses_allow_list(client, tmp_path):
    f = tmp_path / "form.txt"
    f.write_text("hello", encoding="utf-8")
    with patch("downloads.resolve_download", return_value=f):
        ok = client.get("/download/abc")
    assert ok.status_code == 200 and ok.content == b"hello"
    with patch("downloads.resolve_download", return_value=None):
        assert client.get("/download/abc").status_code == 404


def test_download_route_rejects_path_like_ids(client):
    with patch("downloads.resolve_download", return_value=None) as rd:
        client.get("/download/..%2F..%2Fetc%2Fpasswd")
    assert all("/" not in c.args[0] for c in rd.call_args_list)


def test_index_page_served_in_thai(client):
    r = client.get("/chat")
    assert r.status_code == 200 and "RiSA" in r.text and 'lang="th"' in r.text


def test_root_serves_the_home_page(client):
    r = client.get("/")
    assert r.status_code == 200 and 'lang="th"' in r.text and "home.js" in r.text


def test_chat_page_is_public_and_frameable(client):
    r = client.get("/chat")
    assert r.status_code == 200 and "app.js" in r.text
    assert "x-frame-options" not in r.headers  # the researcher drawer embeds this page


def test_track_redirects_to_root_without_a_loop(client):
    r = client.get("/track", follow_redirects=False)
    assert r.status_code in (307, 308) and r.headers["location"] == "/"
    assert client.get("/").status_code == 200


def test_icons_script_served_and_linked(client):
    assert "function fileIcon" in client.get("/static/icons.js").text
    assert "icons.js" in client.get("/chat").text


def test_repeated_question_without_history_is_answered_from_cache(client):
    with patch("rag.answer", return_value=rag.Reply("ตอบ")) as ans:
        a, b = post(client, "ลากี่วัน"), post(client, "  ลากี่วัน ")
    assert a.json() == b.json() and ans.call_count == 1


def test_question_with_history_is_never_cached(client):
    hist = [{"role": "user", "content": "ก"}, {"role": "assistant", "content": "ข"}]
    with patch("rag.answer", return_value=rag.Reply("ตอบ")) as ans:
        post(client, "ต่อ", hist), post(client, "ต่อ", hist)
    assert ans.call_count == 2 and state.cache == {}


def test_failed_answer_is_not_cached(client):
    with patch("rag.answer", side_effect=RuntimeError("boom")):
        assert post(client).status_code == 503
    assert state.cache == {}


@pytest.mark.parametrize("js, html", [("app.js", "index.html"), ("admin.js", "admin.html")])
def test_every_element_id_a_script_looks_up_exists_in_its_page(js, html):
    import re
    from pathlib import Path
    web = Path(server.WEB)
    ids = set(re.findall(r'\$\("([\w-]+)"\)', (web / js).read_text(encoding="utf-8")))
    page = (web / html).read_text(encoding="utf-8")
    assert [i for i in ids if f'id="{i}"' not in page] == []  # a missing id throws at load and the page stays blank


def stream(client, message="ลากี่วัน", history=None):
    r = client.post("/api/chat/stream", json={"message": message, "history": history or []})
    return r, [json.loads(l) for l in r.text.splitlines()]


def test_stream_sends_deltas_then_the_final_text_and_files(client):
    def fake(history, message, store, llm=None, on_delta=None, on_status=None):
        on_status("กำลังค้นหา...")
        on_delta("ลา"), on_delta("พักร้อน")
        return rag.Reply("ลาพักร้อน 10 วัน", [], [])
    with patch("rag.answer", fake):
        r, events = stream(client)
    assert r.headers["content-type"].startswith("application/x-ndjson")
    assert events == [{"status": "กำลังค้นหา..."}, {"delta": "ลา"}, {"delta": "พักร้อน"}, {"done": True, "text": "ลาพักร้อน 10 วัน", "files": []}]


def test_stream_cached_question_skips_the_model_and_errors_are_thai(client):
    with patch("rag.answer", return_value=rag.Reply("ตอบ")) as ans:
        stream(client)
        _, events = stream(client)
    assert ans.call_count == 1 and events == [{"done": True, "text": "ตอบ", "files": []}]
    with patch("rag.answer", side_effect=RuntimeError("boom")):
        _, events = stream(client, "คำถามใหม่")
    assert events == [{"error": server.ERROR_TEXT}]


def test_pages_link_to_each_other(client):
    assert 'href="/" target="_top"' in client.get("/chat").text  # _top: inside the drawer it must leave the iframe
    assert 'href="/chat"' in client.get("/").text
