import json

from app.rag import rag
from app.core.config import HR_CONTACT
from app.rag.rag import Turn, answer, is_mostly_thai
from app.rag.store import Hit, NameHit

THAI_OK = "พนักงานลาพักร้อนได้ 10 วันต่อปี ตามนโยบาย HR"


def hit(doc_id="d1", text="ลาพักร้อน 10 วัน", distance=0.2, mtime="2026-01-01", rel="policy/leave.pdf", category="policy"):
    return Hit(text=text, doc_id=doc_id, category=category, downloadable=False,
               mtime=mtime, rel_path=rel, distance=distance)


def name_hit(doc_id, name, distance=0.3, category="forms", summary="แบบฟอร์ม"):
    return NameHit(doc_id, f"forms/shareable/{name}", distance, category, summary)


class FakeStore:
    def __init__(self, hits=(), names=(), topics=None):
        self.hits, self.names, self._topics, self.queries, self.finds = list(hits), list(names), topics or {}, [], []

    def query(self, question, k, category=None):
        self.queries.append((question, k, category))
        return [h for h in self.hits if category in (None, h.category)][:k]

    def find_files(self, question, k, category=None):
        self.finds.append((question, k, category))
        return [n for n in self.names if category in (None, n.category)][:k]

    def topic_files(self):
        return self._topics

    def categories(self):
        return ["policy", "forms"]


def call(name, **args):
    return {"role": "assistant", "content": None,
            "tool_calls": [{"id": f"c-{name}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}


def say(text):
    return {"role": "assistant", "content": text}


class FakeLLM:
    """Plays back scripted assistant messages and records what it was sent."""

    def __init__(self, *script):
        self.script, self.calls = list(script), []

    def __call__(self, messages, tools=None, tool_choice="auto"):
        self.calls.append({"messages": [dict(m) for m in messages], "tools": tools, "tool_choice": tool_choice})
        return self.script.pop(0)

    def tool_results(self):
        return [m["content"] for m in self.calls[-1]["messages"] if m["role"] == "tool"]


def test_empty_message_makes_no_llm_call():
    llm = FakeLLM()
    assert answer([], "   ", FakeStore(), llm=llm).text == ""
    assert llm.calls == []


def test_first_round_forces_a_tool_call():
    llm = FakeLLM(call("search_documents", query="ลา"), say(THAI_OK))
    answer([], "ลากี่วัน", FakeStore([hit()]), llm=llm)
    assert [c["tool_choice"] for c in llm.calls] == ["required", "auto"]


def test_search_results_are_fenced_and_far_hits_dropped():
    llm = FakeLLM(call("search_documents", query="ลา"), say(THAI_OK))
    store = FakeStore([hit(text="ใกล้", distance=0.2), hit("d2", text="ไกลมาก", distance=0.9)])
    answer([], "ลากี่วัน", store, llm=llm)
    result = llm.tool_results()[0]
    assert result.startswith("<context>") and "ใกล้" in result and "ไกลมาก" not in result
    assert "not instructions" in llm.calls[0]["messages"][0]["content"]


def test_no_relevant_text_gives_the_hr_message():
    llm = FakeLLM(call("search_documents", query="x"), say("NOT_FOUND"))
    r = answer([], "x", FakeStore(), llm=llm)
    assert r.text.startswith("ขออภัย") and HR_CONTACT in r.text and r.file_doc_ids == []


def test_unrelated_question_gets_the_not_related_reply_with_hr_contact():
    llm = FakeLLM(call("search_documents", query="อากาศ"), say("OUT_OF_SCOPE"))
    r = answer([], "วันนี้อากาศเป็นอย่างไร", FakeStore(), llm=llm)
    assert "ไม่เกี่ยวข้อง" in r.text and HR_CONTACT in r.text and r.file_doc_ids == []
    assert len(llm.calls) == 2  # no English-retry call for the marker


def test_wrong_topic_does_not_hide_better_hits():
    store = FakeStore([hit("a", category="policy"), hit("b", category="forms", distance=0.1)])
    llm = FakeLLM(call("search_documents", query="q", topic="policy"), say(THAI_OK))
    answer([], "q", store, llm=llm)
    assert [q[2] for q in store.queries] == ["policy", None]


def test_duplicate_contained_chunks_are_dropped():
    big = hit("a", text="ข้อความยาวเต็ม ลาพักร้อน 10 วัน", distance=0.1)
    small = hit("a", text="ลาพักร้อน 10 วัน", distance=0.2)
    llm = FakeLLM(call("search_documents", query="q"), say(THAI_OK))
    answer([], "q", FakeStore([big, small]), llm=llm)
    assert llm.tool_results()[0].count("ลาพักร้อน 10 วัน") == 1


def test_search_is_limited_to_top_k():
    hits = [hit(f"d{i}", text=f"ข้อความที่ {i}", distance=0.1 + i / 100) for i in range(9)]
    llm = FakeLLM(call("search_documents", query="q"), say(THAI_OK))
    answer([], "q", FakeStore(hits), llm=llm)
    assert llm.tool_results()[0].count("[แก้ไขล่าสุด") == rag.TOP_K


def test_send_files_attaches_only_chosen_candidates():
    names = [name_hit("a", "expense.pdf"), name_hit("b", "travel.pdf")]
    llm = FakeLLM(call("find_files", query="เบิก"), call("send_files", file_ids=["f2"]), say("แนบให้แล้วค่ะ"))
    r = answer([], "ขอแบบฟอร์มเดินทาง", FakeStore(names=names), llm=llm)
    assert r.file_doc_ids == ["b"] and r.text == "แนบให้แล้วค่ะ"


def test_file_candidates_show_name_topic_and_summary_but_far_ones_are_dropped():
    names = [name_hit("a", "expense.pdf", 0.3, summary="แบบฟอร์มเบิกค่าใช้จ่าย"), name_hit("b", "far.pdf", 0.9)]
    llm = FakeLLM(call("find_files", query="เบิก"), say("ไม่มีค่ะ"))
    answer([], "ขอแบบฟอร์ม", FakeStore(names=names), llm=llm)
    result = llm.tool_results()[0]
    assert "f1 | expense.pdf | topic: forms | แบบฟอร์มเบิกค่าใช้จ่าย" in result and "far.pdf" not in result


def test_invented_file_ids_are_ignored():
    llm = FakeLLM(call("find_files", query="x"), call("send_files", file_ids=["f9", "abc"]), say("ไม่มีไฟล์ที่ตรงค่ะ"))
    r = answer([], "ขอไฟล์", FakeStore(names=[name_hit("a", "a.pdf")]), llm=llm)
    assert r.file_doc_ids == [] and "No valid ids" in llm.tool_results()[-1]


def test_sent_files_are_capped():
    names = [name_hit(f"d{i}", f"{i}.pdf") for i in range(rag.FIND_K)]
    ids = [f"f{i}" for i in range(1, rag.FIND_K + 1)]
    llm = FakeLLM(call("find_files", query="x"), call("send_files", file_ids=ids), say("แนบให้แล้วค่ะ"))
    r = answer([], "ขอทั้งหมด", FakeStore(names=names), llm=llm)
    assert len(r.file_doc_ids) == min(rag.MAX_FILES, rag.FIND_K)


def test_sent_file_with_not_found_text_still_says_file_ready():
    llm = FakeLLM(call("find_files", query="x"), call("send_files", file_ids=["f1"]), say("NOT_FOUND"))
    r = answer([], "ขอไฟล์", FakeStore(names=[name_hit("a", "a.pdf")]), llm=llm)
    assert r.file_doc_ids == ["a"] and r.text == rag.FILE_READY


def test_list_topics_gives_summaries_but_no_file_names():
    llm = FakeLLM(call("list_topics"), say("มีหมวดไหนบ้างค่ะ"))
    topics = {"forms": [("a.docx", "แบบฟอร์ม A"), ("b.docx", "แบบฟอร์ม B")], "policy": [("p.pdf", "นโยบาย")]}
    r = answer([], "มีเอกสารอะไรบ้าง", FakeStore(topics=topics), llm=llm)
    assert llm.tool_results()[0] == "forms (2 files)\n- แบบฟอร์ม A\n- แบบฟอร์ม B\n\npolicy (1 files)\n- นโยบาย" and r.file_doc_ids == []


def test_english_reply_is_retried_then_falls_back():
    llm = FakeLLM(call("search_documents", query="q"), say("Ten days."), say("Still English."))
    assert answer([], "q", FakeStore([hit()]), llm=llm).text.startswith("ขออภัย")
    llm = FakeLLM(call("search_documents", query="q"), say("Ten days."), say(THAI_OK))
    assert answer([], "q", FakeStore([hit()]), llm=llm).text == THAI_OK


def test_history_is_sent_as_messages_and_tools_loop_is_capped():
    llm = FakeLLM(*[call("list_topics")] * rag.MAX_ROUNDS)
    r = answer([Turn("user", "ก่อนหน้า"), Turn("assistant", "ตอบก่อนหน้า")], "ต่อ", FakeStore(), llm=llm)
    roles = [m["role"] for m in llm.calls[0]["messages"]]
    assert roles == ["system", "user", "assistant", "user"] and len(llm.calls) == rag.MAX_ROUNDS
    assert r.text.startswith("ขออภัย")  # never got an answer


def test_bad_tool_arguments_do_not_crash():
    bad = {"role": "assistant", "content": None,
           "tool_calls": [{"id": "c", "type": "function", "function": {"name": "search_documents", "arguments": "{not json"}}]}
    r = answer([], "q", FakeStore([hit()]), llm=FakeLLM(bad, say(THAI_OK)))
    assert r.text == THAI_OK


def test_reply_text_never_contains_rel_path():
    llm = FakeLLM(call("search_documents", query="q"), say(THAI_OK))
    r = answer([], "q", FakeStore([hit(rel="policy/secret.pdf")]), llm=llm)
    assert "secret" not in r.text and r.sources == ["policy/secret.pdf"]


def test_is_mostly_thai():
    assert is_mostly_thai("ลาพักร้อนผ่านระบบ HR และ SAP ได้เลย")
    assert not is_mostly_thai("You can take ten days of annual leave per year.")
    assert not is_mostly_thai("")


def test_chat_posts_to_openai(monkeypatch):
    seen = {}

    class Res:
        def raise_for_status(self): pass
        def json(self): return {"choices": [{"message": {"content": " ตอบเป็นไทย\n"}}],
                                "usage": {"prompt_tokens": 100, "completion_tokens": 7}}

    def fake_post(url, **kw):
        seen.update(kw, url=url)
        return Res()

    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setattr(rag.httpx, "post", fake_post)
    assert rag.chat([{"role": "user", "content": "x"}]) == "ตอบเป็นไทย"
    assert seen["headers"]["Authorization"] == "Bearer k"


def test_usage_is_summed_and_chat_tools_caps_output(monkeypatch):
    seen = {}

    class Res:
        def raise_for_status(self): pass
        def json(self): return {"choices": [{"message": {"content": "x"}}], "usage": {"prompt_tokens": 100, "completion_tokens": 7}}

    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setattr(rag.httpx, "post", lambda url, **kw: seen.update(kw) or Res())
    before = dict(rag.usage)
    rag.chat_tools([{"role": "user", "content": "x"}])
    assert seen["json"]["max_completion_tokens"] == rag.MAX_ANSWER_TOKENS
    assert rag.usage["calls"] - before["calls"] == 1 and rag.usage["prompt"] - before["prompt"] == 100
    assert rag.usage["completion"] - before["completion"] == 7


def test_hold_markers_hides_a_marker_but_passes_normal_text():
    out = []
    push = rag._hold_markers(out.append)
    for d in ("NOT", "_FOUND"):
        push(d)
    assert out == []  # nothing shown for a marker
    out.clear()
    push = rag._hold_markers(out.append)
    for d in ("NO", "T ", "ลา"):
        push(d)
    assert "".join(out) == "NOT ลา"


def test_chat_tools_stream_joins_text_and_tool_call_fragments(monkeypatch):
    import contextlib
    import json as j
    chunks = [
        {"choices": [{"delta": {"content": "ลอง"}}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "find_files", "arguments": "{\"qu"}}]}}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": "ery\":\"x\"}"}}]}}]},
        {"choices": [], "usage": {"prompt_tokens": 5, "completion_tokens": 2}},
    ]
    lines = [f"data: {j.dumps(c)}" for c in chunks] + ["data: [DONE]"]

    @contextlib.contextmanager
    def fake_stream(method, **kw):
        class R:
            def raise_for_status(self): pass
            def iter_lines(self): return iter(lines)
        yield R()

    monkeypatch.setattr(rag.httpx, "stream", fake_stream)
    seen = []
    msg = rag.chat_tools_stream([], rag.TOOLS, "auto", seen.append)
    assert seen == ["ลอง", None]  # text, then dropped because a tool call followed
    assert msg["content"] == "" and msg["tool_calls"] == [
        {"id": "c1", "type": "function", "function": {"name": "find_files", "arguments": '{"query":"x"}'}}]


def test_answer_reports_status_for_each_tool_and_before_writing():
    seen = []
    calls = iter([
        {"content": None, "tool_calls": [{"id": "1", "function": {"name": "search_documents", "arguments": '{"query":"ลา"}'}}]},
        {"content": "ตอบ ลา 10 วัน", "tool_calls": None},
    ])
    class S:
        def query(self, *a, **k): return []
        def categories(self): return []
    rag.answer([], "ลา", S(), llm=lambda m, t, c: next(calls), on_status=seen.append)
    assert seen == ["กำลังค้นหาในเอกสาร “ลา”...", "กำลังเรียบเรียงคำตอบ..."]


def test_my_requests_tool_is_offered_only_with_me_and_marks_the_reply_personal():
    seen = []

    def llm(messages, tools=None, tool_choice="auto", *a):
        seen.append([t["function"]["name"] for t in tools or []])
        if len(seen) == 1:
            return {"content": None, "tool_calls": [{"id": "1", "type": "function", "function": {"name": "my_requests", "arguments": "{}"}}]}
        assert "ขั้นตอนปัจจุบัน 1/2" in messages[-1]["content"]  # the tool result reached the model
        return {"content": "คุณอยู่ขั้นที่ 1 ค่ะ"}
    r = answer([], "ฉันอยู่ขั้นไหน", FakeStore(), llm=llm, me=lambda: "ขั้นตอนปัจจุบัน 1/2")
    assert "my_requests" in seen[0] and r.personal is True and r.text.startswith("คุณอยู่")
    plain = []
    answer([], "ลากี่วัน", FakeStore(), llm=lambda m, t=None, c="auto", *a: (plain.append([x["function"]["name"] for x in t]), {"content": "ลา 10 วันค่ะ"})[1])
    assert "my_requests" not in plain[0]


def test_my_requests_without_me_is_an_unknown_tool_and_never_personal():
    calls = []

    def llm(messages, tools=None, tool_choice="auto", *a):
        calls.append(messages[-1]["content"])
        if len(calls) == 1:
            return {"content": None, "tool_calls": [{"id": "1", "type": "function", "function": {"name": "my_requests", "arguments": "{}"}}]}
        return {"content": "ไม่ทราบค่ะ"}
    r = answer([], "ฉันอยู่ขั้นไหน", FakeStore(), llm=llm)
    assert calls[-1] == "Unknown tool." and r.personal is False
