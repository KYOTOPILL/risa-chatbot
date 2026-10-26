import json

import rag
from config import HR_CONTACT
from rag import Turn, answer, is_mostly_thai
from store import Hit, NameHit

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

    def topics(self):
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


def test_list_topics_reports_counts():
    llm = FakeLLM(call("list_topics"), say("มีหมวดไหนบ้างค่ะ"))
    r = answer([], "มีเอกสารอะไรบ้าง", FakeStore(topics={"forms": 2, "policy": 1}), llm=llm)
    assert llm.tool_results()[0] == "forms (2 files)\npolicy (1 files)" and r.file_doc_ids == []


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


def test_chat_posts_to_openai_with_json_mode(monkeypatch):
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
    assert rag.chat([{"role": "user", "content": "x"}], json_mode=True) == "ตอบเป็นไทย"
    assert seen["headers"]["Authorization"] == "Bearer k"
    assert seen["json"]["response_format"] == {"type": "json_object"}


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
