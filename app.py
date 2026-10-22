import logging
import threading

import streamlit as st

import downloads
import rag
from config import CONTENT_DIR
from store import Store

log = logging.getLogger("chatbot")
if not log.handlers:  # streamlit leaves the root logger unconfigured; answer sources go here
    log.addHandler(logging.StreamHandler())
log.setLevel(logging.INFO)


@st.cache_resource
def shared():
    # one local model serves everyone: the lock makes concurrent questions wait their turn
    return Store(), threading.Lock()


def show_files(doc_ids: list[str], store, key: str) -> None:
    for i, doc_id in enumerate(doc_ids):
        path = downloads.resolve_download(doc_id, store, CONTENT_DIR)
        if path:
            st.download_button("ดาวน์โหลดเอกสาร", path.read_bytes(), file_name=path.name, key=f"{key}-{i}")


st.set_page_config(page_title="ผู้ช่วยสำนักงาน")
st.title("ผู้ช่วยสำนักงาน")
store, lock = shared()
msgs = st.session_state.setdefault("msgs", [])

for n, m in enumerate(msgs):
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
        show_files(m.get("files", []), store, f"h{n}")

if prompt := st.chat_input("พิมพ์คำถามของคุณ"):
    if prompt.strip():
        history = [rag.Turn(m["role"], m["content"]) for m in msgs]
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            try:
                with st.spinner("กำลังค้นหาข้อมูล..."), lock:
                    reply = rag.answer(history, prompt, store)
            except Exception:
                log.exception("answer failed")
                st.error("ขออภัย ระบบขัดข้อง กรุณาลองใหม่อีกครั้งหรือติดต่อผู้ดูแลระบบ")
                st.stop()
            log.info("q=%r sources=%s", prompt, reply.sources)
            st.markdown(reply.text)
            show_files(reply.file_doc_ids, store, f"n{len(msgs) + 1}")
        msgs.append({"role": "user", "content": prompt})
        msgs.append({"role": "assistant", "content": reply.text, "files": reply.file_doc_ids})
