import logging
import threading

import streamlit as st

import downloads
import rag
from config import CONTENT_DIR
from store import Store

log = logging.getLogger("chatbot")


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
        msgs.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("กำลังค้นหาข้อมูล..."), lock:
                reply = rag.answer(history, prompt, store)
            log.info("q=%r sources=%s", prompt, reply.sources)
            st.markdown(reply.text)
            show_files(reply.file_doc_ids, store, f"n{len(msgs)}")
        msgs.append({"role": "assistant", "content": reply.text, "files": reply.file_doc_ids})
